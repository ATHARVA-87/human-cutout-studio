"""Password hashing and database-backed login sessions (one active session per user)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import EmailToken, SessionToken, User
from backend.app.db.session import get_session

COOKIE_NAME = "human_cutout_session"
SESSION_DAYS = 7
PBKDF2_ROUNDS = 600_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Slow, salted hash (PBKDF2-HMAC-SHA256). Stored as 'pbkdf2_sha256$<salt>$<digest>'."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, _ = stored.split("$", 2)
    # compare_digest takes the same time whether the first or last character differs (no timing leak).
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


# Checked against when the email does not exist, so "unknown email" takes as long as "wrong password"
# and response time does not reveal which emails have accounts.
_DUMMY_HASH = hash_password("not-a-real-password")


def check_login(user: User | None, password: str) -> bool:
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, user.password_hash)


def hash_token(token: str) -> str:
    """Only a SHA-256 of the session token is stored, so a leaked database cannot be used to log in."""
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(session: Session, response: Response, user: User) -> None:
    """Create or replace the user's single session and send its token as an HTTP-only cookie.

    INSERT ... ON CONFLICT (user_id) DO UPDATE: if the user is already logged in somewhere,
    that old session row is overwritten, so the newest login wins and the old browser is signed out.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    statement = insert(SessionToken).values(user_id=user.id, token_hash=hash_token(token), expires_at=expires_at)
    statement = statement.on_conflict_do_update(
        index_elements=[SessionToken.user_id],
        set_={"token_hash": statement.excluded.token_hash, "expires_at": statement.excluded.expires_at},
    )
    session.execute(statement)
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,  # JavaScript cannot read it, which limits damage from XSS
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


def end_session(session: Session, request: Request, response: Response) -> None:
    """Delete the session row for this cookie (if any) and clear the cookie. Works even if already expired."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session.execute(delete(SessionToken).where(SessionToken.token_hash == hash_token(token)))
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


def user_from_cookie(session: Session, request: Request) -> User | None:
    """The user whose valid session cookie came with this request, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    entry = session.scalar(
        select(SessionToken).where(SessionToken.token_hash == hash_token(token), SessionToken.expires_at > datetime.now(UTC))
    )
    return session.get(User, entry.user_id) if entry else None


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """FastAPI dependency: the logged-in user, or HTTP 401."""
    if not request.cookies.get(COOKIE_NAME):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    user = user_from_cookie(session, request)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Your session ended (it expired or you signed in elsewhere). Please sign in again."
        )
    return user


def verified_user(user: User = Depends(current_user)) -> User:
    """FastAPI dependency for paid jobs: signed in AND email confirmed, or HTTP 403."""
    if not user.email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Confirm your email address first. Check your inbox for the link, or send a new one."
        )
    return user


# ---------------------------------------------------------------------------------------------
# One-time email links (verify email / reset password)
# ---------------------------------------------------------------------------------------------


def create_email_token(session: Session, user: User, purpose: str, lifetime: timedelta) -> str:
    """Make a random single-use token, store only its hash, and return the raw token for the email link.

    Older unused links of the same purpose are expired (not deleted), so only the newest link works while
    the old rows still count towards the sending limit. Does NOT commit: the caller commits.
    """
    session.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .values(expires_at=datetime.now(UTC))
    )
    token = secrets.token_urlsafe(32)
    session.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token), expires_at=datetime.now(UTC) + lifetime))
    return token


def use_email_token(session: Session, token: str, purpose: str) -> User:
    """Check a token from an email link and mark it used. Wrong, expired or reused -> HTTP 400.

    SELECT ... FOR UPDATE locks the token row, so two simultaneous clicks can't both use it.
    """
    entry = session.scalar(
        select(EmailToken)
        .where(EmailToken.token_hash == hash_token(token), EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .with_for_update()
    )
    if entry is None or entry.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link is invalid or has expired. Request a new one.")
    entry.used_at = datetime.now(UTC)
    user = session.get(User, entry.user_id)
    assert user is not None  # the token row is deleted together with the user (ON DELETE CASCADE)
    return user


def tokens_sent_recently(session: Session, user: User, purpose: str, within: timedelta) -> int:
    """How many links of this kind were created for the user recently (used to limit email sending)."""
    since = datetime.now(UTC) - within
    rows = session.scalars(
        select(EmailToken.id).where(EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.created_at >= since)
    ).all()
    return len(rows)


def end_all_sessions(session: Session, user: User) -> None:
    """Sign the user out everywhere (after a password reset). Does not commit."""
    session.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
