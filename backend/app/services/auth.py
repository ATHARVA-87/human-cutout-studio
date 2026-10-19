"""Password hashing and database-backed login sessions (one active session per user)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import SessionToken, User
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


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """FastAPI dependency: the logged-in user, or HTTP 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    entry = session.scalar(
        select(SessionToken).where(SessionToken.token_hash == hash_token(token), SessionToken.expires_at > datetime.now(UTC))
    )
    user = session.get(User, entry.user_id) if entry else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session ended (it expired or you signed in elsewhere). Please sign in again.")
    return user
