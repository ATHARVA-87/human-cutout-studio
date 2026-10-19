"""Account routes: register, login, logout, current user, demo recharge."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import CreditTransaction, User
from backend.app.db.session import get_session
from backend.app.schemas import Account, Credentials
from backend.app.services.auth import current_user, end_session, hash_password, start_session, verify_password
from backend.app.services.credits import recharge as recharge_credits
from backend.app.services.jobs import COMPOSE_COST, RECHARGE_AMOUNT
from backend.app.services.rate_limit import new_bucket

router = APIRouter(prefix="/auth", tags=["auth"])
WELCOME_CREDITS = 30


def to_account(user: User) -> Account:
    return Account(email=user.email, credits=user.credits)


@router.post("/register", response_model=Account, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, session: Session = Depends(get_session)) -> Account:
    email = body.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(email=email, password_hash=hash_password(body.password), credits=WELCOME_CREDITS)
    session.add(user)
    try:
        session.flush()  # sends the INSERT so user.id exists for the rows below
    except IntegrityError:  # two sign-ups with the same email at the same moment
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    session.add(CreditTransaction(user_id=user.id, amount=WELCOME_CREDITS, reason="welcome_credits"))
    session.add(new_bucket(user))
    session.commit()
    start_session(session, response, user)
    return to_account(user)


@router.post("/login", response_model=Account)
def login(body: Credentials, response: Response, session: Session = Depends(get_session)) -> Account:
    user = session.scalar(select(User).where(User.email == body.email.lower()))
    # Same message for "no such email" and "wrong password", so attackers cannot discover accounts.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    start_session(session, response, user)  # replaces any session on another device
    return to_account(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> None:
    end_session(session, request, response)


@router.get("/me", response_model=Account)
def me(user: User = Depends(current_user)) -> Account:
    return to_account(user)


@router.post("/recharge", response_model=Account)
def recharge(session: Session = Depends(get_session), user: User = Depends(current_user)) -> Account:
    recharge_credits(session, user, minimum=COMPOSE_COST, amount=RECHARGE_AMOUNT)
    return to_account(user)
