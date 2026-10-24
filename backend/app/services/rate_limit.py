"""Rate limits stored in PostgreSQL: a per-user token bucket for jobs, and a login attempt limit.

Each user has a bucket holding up to `bucket_capacity` tokens (10). Starting a job costs one
token. Tokens drip back continuously: a full bucket refills in `bucket_period_seconds` (30 min),
i.e. one token every 3 minutes. Bursts of up to 10 are allowed, but the long-run rate is capped.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import LoginAttempt, RateLimitBucket, User


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


# ---------------------------------------------------------------------------------------------
# Login attempt limit (brute-force protection)
#
# Every FAILED login stores one row (with a hash of the email). Before checking a password we count
# the failures for that email in the last `login_window_minutes`; at `login_max_failures` the login
# is refused with 429 *before* running the slow password hash, so guessing is slow and cheap for us.
# ---------------------------------------------------------------------------------------------


def email_hash(email: str) -> str:
    """Store a hash, not the email itself: attempts can also be for addresses that have no account."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def check_login_allowed(session: Session, email: str) -> None:
    since = datetime.now(UTC) - timedelta(minutes=settings.login_window_minutes)
    key = email_hash(email)
    failures = session.scalars(
        select(LoginAttempt.created_at).where(LoginAttempt.email_hash == key, LoginAttempt.created_at >= since).order_by(LoginAttempt.created_at)
    ).all()
    if len(failures) >= settings.login_max_failures:
        # The oldest failure in the window "expires" first; after that one more attempt is allowed.
        wait = max(1, math.ceil((failures[0] + timedelta(minutes=settings.login_window_minutes) - datetime.now(UTC)).total_seconds()))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts. Try again in {math.ceil(wait / 60)} min.",
            headers={"Retry-After": str(wait)},
        )


def record_login_failure(session: Session, email: str) -> None:
    session.add(LoginAttempt(email_hash=email_hash(email)))
    session.commit()


def clear_login_failures(session: Session, email: str) -> None:
    session.execute(delete(LoginAttempt).where(LoginAttempt.email_hash == email_hash(email)))
    session.commit()
