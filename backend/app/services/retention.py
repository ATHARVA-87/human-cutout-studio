"""Data retention: automatically delete old user data so the free database and disk never fill up.

Policy (also stated on the Privacy page):
- uploads, results and their history rows: deleted `retention_days` (5) days after creation
- expired login sessions: deleted
- failed-login and per-IP records: deleted after 1 day
- credit ledger rows: deleted after 30 days
Accounts themselves stay until the user deletes them.

The job runs at every server start and then every `cleanup_interval_minutes` (60) while the
server is awake. On the free tier the server sleeps when idle, but no new data is created while it
sleeps, and the job runs again as soon as it wakes, so nothing outlives the retention period by much.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, text

from backend.app.core.config import settings
from backend.app.db.models import Composition, CreditTransaction, IpEvent, LoginAttempt, Prediction, SessionToken
from backend.app.db.session import SessionLocal, rows_affected

logger = logging.getLogger("human_cutout.retention")

LOGIN_ATTEMPT_DAYS = 1
LEDGER_DAYS = 30
# Any fixed number works: it names the lock that lets only ONE server instance clean at a time.
CLEANUP_LOCK_ID = 2026_10_24


def expiry_of(created_at: datetime) -> datetime:
    """When an upload/result created at `created_at` will be deleted (shown in the History page)."""
    return created_at + timedelta(days=settings.retention_days)


@dataclass(frozen=True)
class CleanupReport:
    predictions: int
    compositions: int
    sessions: int
    login_attempts: int
    ip_events: int
    ledger_rows: int
    folders: int


def run_cleanup(now: datetime | None = None) -> CleanupReport | None:
    """Delete everything past its retention period. Returns None if another instance is already cleaning."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.retention_days)
    with SessionLocal() as session:
        # A transaction-level advisory lock: if two copies of the app run this at the same moment,
        # only one gets the lock; it is released automatically at COMMIT.
        if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": CLEANUP_LOCK_ID}):
            return None
        login_cutoff = now - timedelta(days=LOGIN_ATTEMPT_DAYS)
        counts = {
            "predictions": rows_affected(session.execute(delete(Prediction).where(Prediction.created_at < cutoff))),
            "compositions": rows_affected(session.execute(delete(Composition).where(Composition.created_at < cutoff))),
            "sessions": rows_affected(session.execute(delete(SessionToken).where(SessionToken.expires_at < now))),
            "login_attempts": rows_affected(session.execute(delete(LoginAttempt).where(LoginAttempt.created_at < login_cutoff))),
            "ip_events": rows_affected(session.execute(delete(IpEvent).where(IpEvent.created_at < login_cutoff))),
            "ledger_rows": rows_affected(
                session.execute(delete(CreditTransaction).where(CreditTransaction.created_at < now - timedelta(days=LEDGER_DAYS)))
            ),
        }
        session.commit()
    return CleanupReport(**counts, folders=delete_old_folders(cutoff))


def delete_old_folders(cutoff: datetime) -> int:
    """Each job writes one uploads/<uuid>/ folder; delete folders last modified before the cutoff.

    Going by the files' age (not by database rows) also removes leftovers whose database row was
    never written, e.g. if the server crashed mid-job.
    """
    root = settings.storage_dir
    if not root.is_dir():
        return 0
    deleted = 0
    for folder in root.iterdir():
        if folder.is_dir() and datetime.fromtimestamp(folder.stat().st_mtime, UTC) < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
            deleted += 1
    return deleted


async def cleanup_forever() -> None:
    """Background task started with the app: clean now, then every `cleanup_interval_minutes`."""
    while True:
        try:
            report = await run_in_threadpool(run_cleanup)
            if report is not None:
                logger.info("cleanup done: %s", report)
        except Exception:  # a failed run (e.g. database briefly unreachable) must not stop future runs
            logger.exception("cleanup failed")
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)
