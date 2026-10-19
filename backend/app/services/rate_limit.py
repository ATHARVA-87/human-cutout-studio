"""Per-user token bucket rate limit, stored in PostgreSQL.

Each user has a bucket holding up to `bucket_capacity` tokens (10). Starting a job costs one
token. Tokens drip back continuously: a full bucket refills in `bucket_period_seconds` (30 min),
i.e. one token every 3 minutes. Bursts of up to 10 are allowed, but the long-run rate is capped.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import RateLimitBucket, User


def refill(tokens: float, elapsed_seconds: float, capacity: int, period_seconds: int) -> float:
    """Pure math, no database: add the tokens earned since the last update, never above capacity."""
    rate = capacity / period_seconds  # tokens per second
    return min(float(capacity), tokens + max(0.0, elapsed_seconds) * rate)


def seconds_until_next_token(tokens: float, capacity: int, period_seconds: int) -> int:
    rate = capacity / period_seconds
    return max(1, math.ceil((1 - tokens) / rate))


def new_bucket(user: User) -> RateLimitBucket:
    return RateLimitBucket(user_id=user.id, tokens=float(settings.bucket_capacity), updated_at=datetime.now(UTC))


def take_token(session: Session, user: User) -> None:
    """Spend one token or raise HTTP 429. Does NOT commit: the caller commits together with the credit charge.

    SELECT ... FOR UPDATE locks this user's bucket row until the transaction ends, so two
    simultaneous requests from the same user are processed one after the other and cannot
    both spend the last token.
    """
    capacity, period = settings.bucket_capacity, settings.bucket_period_seconds
    bucket = session.scalar(select(RateLimitBucket).where(RateLimitBucket.user_id == user.id).with_for_update())
    if bucket is None:
        bucket = new_bucket(user)
        session.add(bucket)
    now = datetime.now(UTC)
    bucket.tokens = refill(bucket.tokens, (now - bucket.updated_at).total_seconds(), capacity, period)
    bucket.updated_at = now
    if bucket.tokens < 1:
        wait = seconds_until_next_token(bucket.tokens, capacity, period)
        session.commit()  # save the refilled value and release the row lock
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many requests. You can start {capacity} jobs per {period // 60} minutes; try again in {math.ceil(wait / 60)} min.",
            headers={"Retry-After": str(wait)},
        )
    bucket.tokens -= 1
