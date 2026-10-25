"""Account routes: register, guest sessions, login, logout, current user, demo recharge, delete account,
email verification and password reset."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import client_ip
from backend.app.core.config import settings
from backend.app.db.models import CreditTransaction, User
from backend.app.db.session import get_session, rows_affected
from backend.app.schemas import Account, Credentials, EmailOnly, NewPassword, PasswordConfirmation, TokenBody
from backend.app.services.accounts import delete_users
from backend.app.services.auth import (
    check_login,
    create_email_token,
    current_user,
    end_all_sessions,
    end_session,
    hash_password,
    start_session,
    tokens_sent_recently,
    use_email_token,
    user_from_cookie,
)
from backend.app.services.credits import recharge as recharge_credits
from backend.app.services.email import reset_email, send_email, verification_email
from backend.app.services.jobs import COMPOSE_COST, RECHARGE_AMOUNT
from backend.app.services.rate_limit import (
    check_guest_allowed,
    check_login_allowed,
    check_registration_allowed,
    check_reset_request_allowed,
    clear_login_failures,
    new_bucket,
    record_guest,
    record_login_failure,
    record_registration,
    record_reset_request,
)

router = APIRouter(prefix="/auth", tags=["auth"])
WELCOME_CREDITS = 30
MAX_EMAILS_PER_HOUR = 3  # per user and kind of link, so nobody can flood an inbox


def to_account(user: User) -> Account:
    return Account(
        email=user.email,
        credits=user.credits,
        email_verified=user.email_verified,
        is_guest=user.is_guest,
        retention_days=settings.retention_days,
        guest_hours=settings.guest_hours,
    )


def confirm_email(session: Session, user: User) -> None:
    """Mark the email confirmed and give the welcome credits, exactly once.

    One conditional UPDATE (`WHERE email_verified = false`) does both, so even two simultaneous clicks
    can't grant the credits twice. Does not commit.
    """
    result = session.execute(
        update(User)
        .where(User.id == user.id, User.email_verified.is_(False))
        .values(email_verified=True, credits=User.credits + WELCOME_CREDITS)
    )
    if rows_affected(result):
        session.add(CreditTransaction(user_id=user.id, amount=WELCOME_CREDITS, reason="welcome_credits"))


def email_link(path: str, token: str) -> str:
    # The token goes in the URL fragment (after #): browsers never send fragments to servers,
    # so tokens don't end up in server or proxy logs. Built from the configured public_url, never the Host header.
    return f"{settings.public_url.rstrip('/')}/#/{path}?token={token}"


@router.post("/register", response_model=Account, status_code=status.HTTP_201_CREATED)
def register(
    body: Credentials, request: Request, response: Response, background: BackgroundTasks, session: Session = Depends(get_session)
) -> Account:
    check_registration_allowed(session, client_ip(request))  # max sign-ups per IP per day
    email = body.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(email=email, password_hash=hash_password(body.password), credits=0)  # credits come with email confirmation
    session.add(user)
    try:
        session.flush()  # sends the INSERT so user.id exists for the rows below
    except IntegrityError as error:  # two sign-ups with the same email at the same moment
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.") from error
    session.add(new_bucket(user))
    record_registration(session, client_ip(request))
    token = create_email_token(session, user, "verify", timedelta(hours=settings.verify_token_hours))
    session.commit()
    start_session(session, response, user)
    # Sent after the response, so sign-up doesn't wait for the email server.
    background.add_task(send_email, verification_email(user.email, email_link("verify", token)))
    return to_account(user)


@router.post("/login", response_model=Account)
def login(body: Credentials, request: Request, response: Response, session: Session = Depends(get_session)) -> Account:
    email, ip = body.email.lower(), client_ip(request)
    check_login_allowed(session, email, ip)  # 429 after too many failures, BEFORE the slow password hash
    user = session.scalar(select(User).where(User.email == email))
    # Same message and same timing for "no such email" and "wrong password".
    # (Registration still reveals taken emails with 409; that is the usual trade-off for a clear sign-up form.)
    if not check_login(user, body.password):
        record_login_failure(session, email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    assert user is not None  # check_login() is only True for an existing user; tells the type checker too
    clear_login_failures(session, email)
    start_session(session, response, user)  # replaces any session on another device
    return to_account(user)


@router.post("/guest", response_model=Account, status_code=status.HTTP_201_CREATED)
def start_guest(request: Request, response: Response, session: Session = Depends(get_session)) -> Account:
    """ "Try it without an account": a temporary, already-confirmed account with no email and no password.

    The placeholder address uses the reserved `.invalid` domain, which can never receive mail, so the app
    never tries to email it. It is deleted on logout, or by the cleanup job after `guest_hours`.
    """
    ip = client_ip(request)
    check_guest_allowed(session, ip)
    user = User(
        email=f"guest-{secrets.token_hex(8)}@guest.invalid",
        password_hash=hash_password(secrets.token_urlsafe(32)),  # random and never shown: nobody can sign in with a password
        credits=settings.guest_credits,
        email_verified=True,
        is_guest=True,
    )
    session.add(user)
    session.flush()
    session.add(CreditTransaction(user_id=user.id, amount=settings.guest_credits, reason="guest_credits"))
    session.add(new_bucket(user))
    record_guest(session, ip)
    session.commit()
    start_session(session, response, user)
    return to_account(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> None:
    user = user_from_cookie(session, request)
    if user is not None and user.is_guest:
        delete_users(session, [user.id])  # a guest can't sign back in, so ending the session deletes everything now
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
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
    body: PasswordConfirmation | None = None,  # guests send no body (they have no password)
) -> None:
    """Permanently delete the account and everything belonging to it ("right to erasure").

    The password is asked again so a stolen session alone cannot delete an account. One DELETE on
    `users` removes the sessions, ledger, rate-limit bucket and history too, because every foreign key
    to users is declared ON DELETE CASCADE. The image files are removed after the commit.
    """
    if not user.is_guest:  # guests have no password to confirm with
        check_login_allowed(session, user.email, client_ip(request))  # the same guessing limits as the login form
        if body is None or not check_login(user, body.password):
            record_login_failure(session, user.email, client_ip(request))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect.")
    delete_users(session, [user.id])
    end_session(session, request, response)  # clears the cookie (the session row is already gone)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(body: TokenBody, session: Session = Depends(get_session)) -> None:
    """The link in the verification email. Works without being signed in: having the link proves the inbox."""
    user = use_email_token(session, body.token, "verify")
    confirm_email(session, user)
    session.commit()


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(background: BackgroundTasks, session: Session = Depends(get_session), user: User = Depends(current_user)) -> None:
    if user.email_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your email address is already confirmed.")
    if tokens_sent_recently(session, user, "verify", timedelta(hours=1)) >= MAX_EMAILS_PER_HOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "We've sent several emails already. Check your inbox and spam folder, or try again in an hour.",
        )
    token = create_email_token(session, user, "verify", timedelta(hours=settings.verify_token_hours))
    session.commit()
    background.add_task(send_email, verification_email(user.email, email_link("verify", token)))


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: EmailOnly, request: Request, background: BackgroundTasks, session: Session = Depends(get_session)
) -> dict[str, str]:
    """Always answers the same way, whether or not the email has an account (no account discovery)."""
    ip = client_ip(request)
    check_reset_request_allowed(session, ip)
    record_reset_request(session, ip)
    user = session.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None and not user.is_guest and tokens_sent_recently(session, user, "reset", timedelta(hours=1)) < MAX_EMAILS_PER_HOUR:
        token = create_email_token(session, user, "reset", timedelta(minutes=settings.reset_token_minutes))
        background.add_task(send_email, reset_email(user.email, email_link("reset", token)))
    session.commit()
    return {"detail": "If an account exists for that email, a link to reset the password is on its way."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: NewPassword, session: Session = Depends(get_session)) -> None:
    """Set a new password from a reset link, and sign the account out on every device."""
    user = use_email_token(session, body.token, "reset")
    user.password_hash = hash_password(body.password)
    confirm_email(session, user)  # opening the emailed link proves they own the inbox
    end_all_sessions(session, user)
    session.commit()
    clear_login_failures(session, user.email)
