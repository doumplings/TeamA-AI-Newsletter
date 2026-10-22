"""ChannelController: a subscriber's notification channels (UC-4, UC-5).

Verification (ChannelVerifier in Section 8):
  - a random 6-digit code is sent through the channel itself, so a correct code
    proves the channel really reaches the subscriber
  - only the SHA-256 of the code is stored
  - the code is valid for 10 minutes and allows 3 wrong tries
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import adapters, config, telegram_bot
from ..adapters import Message
from ..db import get_db
from ..deps import current_user
from ..models import ChannelConnection, ChannelType, User
from ..schemas import (
    AddChannelRequest,
    ChannelView,
    SendTestResult,
    TelegramLinkView,
    UpdateChannelRequest,
    VerifyRequest,
    VerifyResult,
)
from ..security import contact_hash, decrypt_contact, encrypt_contact, generate_code, make_telegram_token, sha256

router = APIRouter(prefix="/channels", tags=["channels"])


def to_view(ch: ChannelConnection) -> ChannelView:
    return ChannelView(
        channel_id=ch.channel_id,
        channel_type=ch.channel_type,
        masked_contact=adapters.for_type(ch.channel_type).mask(decrypt_contact(ch.contact_encrypted)),
        is_enabled=ch.is_enabled,
        is_verified=ch.is_verified,
        min_importance=ch.min_importance,
    )


def _my_channel(db: Session, user: User, channel_id: int) -> ChannelConnection:
    ch = db.get(ChannelConnection, channel_id)
    if not ch or ch.user_id != user.user_id:
        raise HTTPException(404, "Channel not found.")
    return ch


@router.get("", response_model=list[ChannelView])
def list_channels(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ChannelConnection).where(ChannelConnection.user_id == user.user_id).order_by(ChannelConnection.channel_id))
    return [to_view(c) for c in rows]


@router.post("", response_model=ChannelView, status_code=201)
def add_channel(req: AddChannelRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if req.channel_type == ChannelType.telegram:
        raise HTTPException(400, 'Telegram is connected with the "Open Telegram" button.')
    contact = req.contact.strip()
    err = adapters.for_type(req.channel_type).validate_contact(contact)
    if err:
        raise HTTPException(422, {"message": err, "fields": {"contact": err}})

    same_type = db.scalars(select(ChannelConnection).where(ChannelConnection.user_id == user.user_id, ChannelConnection.channel_type == req.channel_type)).all()
    if any(c.is_verified for c in same_type):
        raise HTTPException(409, "This channel type is already connected. Remove it first to use a different one.")
    for c in same_type:  # replace an old unverified attempt instead of piling up duplicates
        db.delete(c)

    # One contact belongs to one account (C5). An unverified attempt by someone else proves nothing, so it is replaced.
    hashed = contact_hash(contact)
    taken = db.scalar(select(ChannelConnection).where(ChannelConnection.channel_type == req.channel_type, ChannelConnection.contact_hash == hashed))
    if taken and taken.is_verified:
        raise HTTPException(409, {"message": "This contact is already connected to another account.", "fields": {"contact": "Already used by another account."}})
    if taken:
        db.delete(taken)
    db.flush()  # deletes first, so the unique rules do not see the old rows

    ch = ChannelConnection(user_id=user.user_id, channel_type=req.channel_type, contact_encrypted=encrypt_contact(contact), contact_hash=hashed)
    db.add(ch)
    db.commit()
    return to_view(ch)


@router.post("/{channel_id}/test", response_model=SendTestResult)
def send_test(channel_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = _my_channel(db, user, channel_id)
    code = generate_code()
    msg = Message(
        subject=f"Your AI Newsletter code: {code}",
        text=f"Your verification code is {code}. Type it on the AI Newsletter website. It is valid for {config.CODE_LIFETIME_MINUTES} minutes.",
    )
    result = adapters.for_type(ch.channel_type).send(decrypt_contact(ch.contact_encrypted), msg)
    if not result.ok:
        raise HTTPException(502, result.error or "Could not send the test message.")

    ch.verification_code_hash = sha256(code)
    ch.code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.CODE_LIFETIME_MINUTES)
    ch.failed_attempts = 0
    db.commit()
    return SendTestResult(sent=True)


@router.post("/{channel_id}/verify", response_model=VerifyResult)
def confirm_code(channel_id: int, req: VerifyRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = _my_channel(db, user, channel_id)
    if ch.is_verified:
        return VerifyResult(ok=True, attempts_left=config.MAX_FAILED_ATTEMPTS - ch.failed_attempts, channel=to_view(ch))
    expired = ch.code_expires_at is None or ch.code_expires_at < datetime.now(timezone.utc)
    if not ch.verification_code_hash or expired or ch.failed_attempts >= config.MAX_FAILED_ATTEMPTS:
        raise HTTPException(410, "This code has expired. Send a new one.")

    if sha256(req.code) != ch.verification_code_hash:
        ch.failed_attempts += 1
        if ch.failed_attempts >= config.MAX_FAILED_ATTEMPTS:
            ch.verification_code_hash = ch.code_expires_at = None  # force a new code
        db.commit()
        return VerifyResult(ok=False, attempts_left=config.MAX_FAILED_ATTEMPTS - ch.failed_attempts)

    ch.is_verified = True
    ch.verified_at = datetime.now(timezone.utc)
    ch.verification_code_hash = None
    ch.code_expires_at = None
    db.commit()
    return VerifyResult(ok=True, attempts_left=config.MAX_FAILED_ATTEMPTS - ch.failed_attempts, channel=to_view(ch))


@router.patch("/{channel_id}", response_model=ChannelView)
def update_channel(channel_id: int, req: UpdateChannelRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = _my_channel(db, user, channel_id)
    ch.is_enabled = req.is_enabled
    ch.min_importance = req.min_importance
    db.commit()
    return to_view(ch)


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = _my_channel(db, user, channel_id)
    db.delete(ch)
    db.commit()


@router.post("/telegram/link", response_model=TelegramLinkView)
def start_telegram_link(user: User = Depends(current_user)):
    """Section 10.2, Change 1: returns a t.me start link with a signed one-time token."""
    username = telegram_bot.bot_username()
    if not username:
        raise HTTPException(503, "Telegram is not set up on the server yet (missing TELEGRAM_BOT_TOKEN).")
    token = make_telegram_token(user.user_id)
    return TelegramLinkView(url=f"https://t.me/{username}?start={token}", expires_in_seconds=config.TELEGRAM_LINK_MINUTES * 60)
