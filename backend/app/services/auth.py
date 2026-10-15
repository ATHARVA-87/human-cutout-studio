"""Password hashing and opaque, database-backed browser sessions."""
from __future__ import annotations
import hashlib, hmac, secrets
from datetime import UTC, datetime, timedelta
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db.models import SessionToken, User
from backend.app.db.session import get_session

COOKIE_NAME = "human_cutout_session"

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$", 2)
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)

def create_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(SessionToken(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(days=7)))
    session.commit()
    return token

def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    entry = session.scalar(select(SessionToken).where(SessionToken.token_hash == hashlib.sha256(token.encode()).hexdigest(), SessionToken.expires_at > datetime.now(UTC)))
    user = session.get(User, entry.user_id) if entry else None
    if not user: raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return user
