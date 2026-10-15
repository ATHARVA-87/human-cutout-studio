from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from backend.app.db.models import CreditTransaction, User

def charge(session: Session, user: User, amount: int, reason: str) -> None:
    result = session.execute(update(User).where(User.id == user.id, User.credits >= amount).values(credits=User.credits - amount).returning(User.credits))
    if result.scalar_one_or_none() is None:
        session.rollback(); raise HTTPException(status_code=402, detail="Not enough credits. Recharge to continue.")
    session.add(CreditTransaction(user_id=user.id, amount=-amount, reason=reason)); session.commit(); session.refresh(user)
