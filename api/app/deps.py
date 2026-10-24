"""Shared request helpers: who is signed in (Authenticator.currentAccount)."""
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, UserSession
from .security import sha256

COOKIE_NAME = "ainews_session"


def current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    if not token:
        raise HTTPException(401, "Please log in.")
    row = db.scalar(select(UserSession).where(UserSession.token_hash == sha256(token)))
    if not row:
        raise HTTPException(401, "Please log in.")
    if row.expires_at < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        raise HTTPException(401, "Your session expired. Please log in again.")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Please log in.")
    return user
