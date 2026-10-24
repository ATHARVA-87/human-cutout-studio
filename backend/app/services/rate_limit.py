"""Rate limits stored in PostgreSQL: a per-user token bucket for jobs, plus sign-in and sign-up abuse limits.

Each user has a bucket holding up to `bucket_capacity` tokens (10). Starting a job costs one
token. Tokens drip back continuously: a full bucket refills in `bucket_period_seconds` (30 min),
i.e. one token every 3 minutes. Bursts of up to 10 are allowed, but the long-run rate is capped.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import IpEvent, LoginAttempt, RateLimitBucket, User


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
# Abuse limits: "at most N events in the last W minutes"
#
# - failed logins per EMAIL (5 / 15 min): slows down guessing one account's password
# - failed logins per IP (20 / 15 min): slows down trying one password against many emails ("spraying")
# - sign-ups per IP (3 / day): stops one person creating many accounts for free credits
# They are checked BEFORE the slow password hash, so blocked requests cost almost nothing.
# Emails and IPs are stored only as hashes.
# ---------------------------------------------------------------------------------------------


def email_hash(email: str) -> str:
    """Store a hash, not the email itself: attempts can also be for addresses that have no account."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def ip_hash(ip: str) -> str:
    """Salted (keyed) hash: there are only ~4 billion IPv4 addresses, so a plain hash could be reversed."""
    return hmac.new(settings.ip_hash_salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


def enforce_window(timestamps: list[datetime], limit: int, window: timedelta, message: str) -> None:
    """Raise 429 if `limit` events already happened inside the window (timestamps sorted oldest first)."""
    if len(timestamps) < limit:
        return
    # The oldest event in the window "expires" first; after that one more attempt is allowed.
    wait = max(1, math.ceil((timestamps[0] + window - datetime.now(UTC)).total_seconds()))
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS, f"{message} Try again in {math.ceil(wait / 60)} min.", headers={"Retry-After": str(wait)}
    )


def check_login_allowed(session: Session, email: str, ip: str) -> None:
    window = timedelta(minutes=settings.login_window_minutes)
    since = datetime.now(UTC) - window
    by_email = session.scalars(
        select(LoginAttempt.created_at)
        .where(LoginAttempt.email_hash == email_hash(email), LoginAttempt.created_at >= since)
        .order_by(LoginAttempt.created_at)
    ).all()
    enforce_window(list(by_email), settings.login_max_failures, window, "Too many failed sign-in attempts for this account.")
    by_ip = recent_ip_events(session, ip, "login_failure", since)
    enforce_window(by_ip, settings.login_failures_per_ip, window, "Too many failed sign-in attempts from your network.")


def record_login_failure(session: Session, email: str, ip: str) -> None:
    session.add(LoginAttempt(email_hash=email_hash(email)))
    session.add(IpEvent(ip_hash=ip_hash(ip), kind="login_failure"))
    session.commit()


def clear_login_failures(session: Session, email: str) -> None:
    session.execute(delete(LoginAttempt).where(LoginAttempt.email_hash == email_hash(email)))
    session.commit()


def recent_ip_events(session: Session, ip: str, kind: str, since: datetime) -> list[datetime]:
    return list(
        session.scalars(
            select(IpEvent.created_at)
            .where(IpEvent.ip_hash == ip_hash(ip), IpEvent.kind == kind, IpEvent.created_at >= since)
            .order_by(IpEvent.created_at)
        ).all()
    )


def check_registration_allowed(session: Session, ip: str) -> None:
    window = timedelta(days=1)
    events = recent_ip_events(session, ip, "register", datetime.now(UTC) - window)
    enforce_window(events, settings.registrations_per_ip_per_day, window, "Too many new accounts from your network today.")


def record_registration(session: Session, ip: str) -> None:
    """Added to the caller's transaction (committed together with the new account)."""
    session.add(IpEvent(ip_hash=ip_hash(ip), kind="register"))
