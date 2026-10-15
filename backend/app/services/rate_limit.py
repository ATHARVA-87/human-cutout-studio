"""Database-backed fixed rolling-window usage policy."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import UsageEvent


def actor_hash(client_host: str) -> str:
    value = f"{settings.rate_limit_salt}:{client_host}".encode()
    return hashlib.sha256(value).hexdigest()


def enforce_rate_limit(session: Session, client_host: str, operation: str) -> None:
    """Reserve one request before expensive inference begins."""
    since = datetime.now(UTC) - timedelta(hours=1)
    identity = actor_hash(client_host)
    used = session.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.actor_hash == identity, UsageEvent.created_at >= since))
    if used >= settings.requests_per_hour:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Hourly prediction limit reached. Try again later.")
    session.add(UsageEvent(actor_hash=identity, operation=operation))
    session.commit()
