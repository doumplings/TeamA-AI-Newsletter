"""AuthController: register, log in, log out (UC-2, UC-3)."""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..adapters import EMAIL_RE
from ..db import get_db
from ..deps import COOKIE_NAME, current_user
from ..models import SubscriberProfile, User, UserSession
from ..schemas import AccountView, LoginRequest, RegisterRequest
from ..security import hash_password, new_session_token, session_expiry, sha256, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _account(user: User) -> AccountView:
    return AccountView(user_id=user.user_id, email=user.email, role=user.role)


def _start_session(db: Session, user: User, response: Response) -> None:
    token = new_session_token()
    db.add(UserSession(user_id=user.user_id, token_hash=sha256(token), expires_at=session_expiry()))
    user.last_login_at = func.now()
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=config.SESSION_DAYS * 24 * 3600,
        httponly=True,  # JavaScript cannot read it
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


@router.post("/register", response_model=AccountView, status_code=201)
def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, {"message": "Please check your email.", "fields": {"email": "That does not look like an email address."}})
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, {"message": "An account with this email already exists.", "fields": {"email": "Already registered. Try logging in."}})

    # New accounts: default level High, following every source (follows_all, C8).
    user = User(email=email, password_hash=hash_password(req.password))
    user.profile = SubscriberProfile(follows_all=True)
    db.add(user)
    db.flush()

    _start_session(db, user, response)
    return _account(user)


@router.post("/login", response_model=AccountView)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == req.email.strip().lower()))
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    _start_session(db, user, response)
    return _account(user)


@router.post("/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), token: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == sha256(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=AccountView)
def me(user: User = Depends(current_user)):
    return _account(user)
