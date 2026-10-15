from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db.models import CreditTransaction, SessionToken, User
from backend.app.db.session import get_session
from backend.app.services.auth import COOKIE_NAME, create_session, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
class Credentials(BaseModel): email: EmailStr; password: str = Field(min_length=8, max_length=128)
class Account(BaseModel): email: str; credits: int
def account(user: User) -> Account: return Account(email=user.email, credits=user.credits)
def sign_in(response: Response, session: Session, user: User) -> Account:
    response.set_cookie(COOKIE_NAME, create_session(session, user), httponly=True, samesite="lax", secure=False, max_age=604800, path="/")
    return account(user)
@router.post("/register", response_model=Account, status_code=201)
def register(body: Credentials, response: Response, session: Session = Depends(get_session)) -> Account:
    if session.scalar(select(User).where(User.email == body.email.lower())): raise HTTPException(409, "An account with that email already exists.")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password)); session.add(user); session.flush(); session.add(CreditTransaction(user_id=user.id, amount=30, reason="welcome_credits")); session.commit(); session.refresh(user)
    return sign_in(response, session, user)
@router.post("/login", response_model=Account)
def login(body: Credentials, response: Response, session: Session = Depends(get_session)) -> Account:
    user = session.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash): raise HTTPException(401, "Invalid email or password.")
    return sign_in(response, session, user)
@router.post("/logout", status_code=204)
def logout(response: Response, session: Session = Depends(get_session), user: User = Depends(current_user)) -> Response:
    session.execute(SessionToken.__table__.delete().where(SessionToken.user_id == user.id)); session.commit(); response.delete_cookie(COOKIE_NAME, path="/"); return response
@router.get("/me", response_model=Account)
def me(user: User = Depends(current_user)) -> Account: return account(user)
@router.post("/recharge", response_model=Account)
def recharge(session: Session = Depends(get_session), user: User = Depends(current_user)) -> Account:
    user.credits = 30; session.add(CreditTransaction(user_id=user.id, amount=30, reason="demo_recharge_reset")); session.commit(); session.refresh(user); return account(user)
