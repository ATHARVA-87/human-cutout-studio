"""The one path every paid job (segmentation or composition) goes through."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app.db.models import User
from backend.app.services.credits import charge, refund
from backend.app.services.rate_limit import take_token

SEGMENT_COST = 1
COMPOSE_COST = 2
RECHARGE_AMOUNT = 30

T = TypeVar("T")


async def run_paid_job(session: Session, user: User, cost: int, reason: str, work: Callable[[], T]) -> T:
    """1) take a rate-limit token and 2) charge credits in ONE transaction, then 3) run the work.

    The work (model inference + saving files) is slow and CPU-bound, so it runs in a worker thread:
    the async server stays free to answer other users meanwhile. If the work fails, credits are refunded.
    """
    take_token(session, user)  # raises 429 when the bucket is empty
    charge(session, user, cost, reason)  # raises 402 (and undoes the token) when credits are short; commits otherwise
    try:
        return await run_in_threadpool(work)
    except Exception as error:
        refund(session, user, cost, f"refund_{reason}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Processing failed. Your credits were refunded.") from error
