"""Shared request helpers: who is signed in (Authenticator.currentAccount)."""
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, User
from .security import sha256

COOKIE_NAME = "ainews_session"


def current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    if not token:
        raise HTTPException(401, "Please log in.")
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == sha256(token)))
    if not row:
        raise HTTPException(401, "Please log in.")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        raise HTTPException(401, "Your session expired. Please log in again.")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Please log in.")
    return user
