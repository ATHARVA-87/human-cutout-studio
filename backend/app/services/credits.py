"""Credit balance changes. Every change also writes a row to the credit_transactions ledger.

After each commit we call `session.expire(user, ["credits"])` instead of `session.refresh(user)`:
refresh would immediately start a new transaction and keep a database connection busy while the
model runs; expire just marks the cached balance as stale, and it is re-read when next needed.
"""

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.db.models import CreditTransaction, User


def charge(session: Session, user: User, amount: int, reason: str) -> None:
    """Atomically subtract credits, then commit (together with any pending rate-limit token).

    The WHERE clause `credits >= amount` makes check-and-subtract ONE SQL statement, so two
    parallel requests can never both spend the same credits. 0 rows updated = not enough credits.
    """
    result = session.execute(update(User).where(User.id == user.id, User.credits >= amount).values(credits=User.credits - amount))
    if result.rowcount == 0:
        session.rollback()  # also undoes the rate-limit token taken in this transaction
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Not enough credits. Recharge to continue.")
    session.add(CreditTransaction(user_id=user.id, amount=-amount, reason=reason))
    session.commit()
    session.expire(user, ["credits"])


def refund(session: Session, user: User, amount: int, reason: str) -> None:
    """Give credits back when a paid job fails after charging."""
    session.execute(update(User).where(User.id == user.id).values(credits=User.credits + amount))
    session.add(CreditTransaction(user_id=user.id, amount=amount, reason=reason))
    session.commit()
    session.expire(user, ["credits"])


def recharge(session: Session, user: User, minimum: int, amount: int) -> None:
    """Demo top-up of `amount` credits, allowed only when the balance is below `minimum`
    (the cost of the most expensive job). Adding a fixed amount keeps the ledger row exact."""
    result = session.execute(update(User).where(User.id == user.id, User.credits < minimum).values(credits=User.credits + amount))
    if result.rowcount == 0:
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Recharge is available when you have fewer than {minimum} credits.")
    session.add(CreditTransaction(user_id=user.id, amount=amount, reason="demo_recharge"))
    session.commit()
    session.expire(user, ["credits"])
