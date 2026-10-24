"""Account routes: register, login, logout, current user, demo recharge, delete account."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import Composition, CreditTransaction, Prediction, User
from backend.app.db.session import get_session
from backend.app.schemas import Account, Credentials, PasswordConfirmation
from backend.app.services.auth import check_login, current_user, end_session, hash_password, start_session
from backend.app.services.credits import recharge as recharge_credits
from backend.app.services.jobs import COMPOSE_COST, RECHARGE_AMOUNT
from backend.app.services.rate_limit import check_login_allowed, clear_login_failures, new_bucket, record_login_failure
from backend.app.services.storage import delete_job_folder

router = APIRouter(prefix="/auth", tags=["auth"])
WELCOME_CREDITS = 30


def to_account(user: User) -> Account:
    return Account(email=user.email, credits=user.credits, retention_days=settings.retention_days)


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
    email = body.email.lower()
    check_login_allowed(session, email)  # 429 after too many failures, BEFORE the slow password hash
    user = session.scalar(select(User).where(User.email == email))
    # Same message and same timing for "no such email" and "wrong password".
    # (Registration still reveals taken emails with 409; that is the usual trade-off for a clear sign-up form.)
    if not check_login(user, body.password):
        record_login_failure(session, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    clear_login_failures(session, email)
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


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: PasswordConfirmation,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> None:
    """Permanently delete the account and everything belonging to it ("right to erasure").

    The password is asked again so a stolen session alone cannot delete an account. One DELETE on
    `users` removes the sessions, ledger, rate-limit bucket and history too, because every foreign key
    to users is declared ON DELETE CASCADE. The image files are removed after the commit.
    """
    check_login_allowed(session, user.email)  # the same guessing limit as the login form
    if not check_login(user, body.password):
        record_login_failure(session, user.email)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect.")
    folders = [*session.scalars(select(Prediction.original_path).where(Prediction.user_id == user.id))]
    folders += [*session.scalars(select(Composition.cutout_path).where(Composition.user_id == user.id))]
    session.execute(delete(User).where(User.id == user.id))
    session.commit()
    for path in folders:
        delete_job_folder(path)
    end_session(session, request, response)  # clears the cookie (the session row is already gone)
