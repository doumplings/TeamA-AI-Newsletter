"""Telegram side of the "Open Telegram" link (TelegramWebhookController.receiveUpdate).

When the subscriber presses Start, Telegram sends our bot "/start <token>".
We check the signed token, and create the channel already verified with the
chat id, because the message itself proves the chat belongs to that user.

Two ways to receive updates:
  - polling (default): a background thread asks Telegram for new messages.
    Works on your laptop with no public URL.
  - webhook: Telegram calls POST /telegram/webhook. Use this when deployed.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache

import httpx
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import delete, select

from . import config
from .db import SessionLocal
from .models import ChannelConnection, ChannelType, User
from .security import contact_hash, encrypt_contact, read_telegram_token

log = logging.getLogger("ainews.telegram")
router = APIRouter(tags=["telegram"])


def _api(method: str, **payload):
    r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=payload, timeout=35)
    r.raise_for_status()
    return r.json()["result"]


@lru_cache(maxsize=1)
def _lookup_username() -> str | None:
    try:
        return _api("getMe")["username"]
    except Exception as e:  # noqa: BLE001
        log.error("Could not reach Telegram getMe: %s", e)
        return None


def bot_username() -> str | None:
    if not config.TELEGRAM_BOT_TOKEN:
        return None
    return config.TELEGRAM_BOT_USERNAME or _lookup_username()


def _reply(chat_id: int, text: str) -> None:
    try:
        _api("sendMessage", chat_id=chat_id, text=text)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not reply to chat %s: %s", chat_id, e)


def link_chat(user_id: int, chat_id: int) -> bool:
    """Create (or replace) the user's Telegram channel, already verified."""
    hashed = contact_hash(str(chat_id))
    with SessionLocal() as db:
        if not db.get(User, user_id):
            return False
        # The chat belongs to whoever pressed Start, so it moves off any other account (C5).
        db.execute(
            delete(ChannelConnection).where(
                ChannelConnection.channel_type == ChannelType.telegram,
                ChannelConnection.contact_hash == hashed,
                ChannelConnection.user_id != user_id,
            )
        )
        ch = db.scalar(select(ChannelConnection).where(ChannelConnection.user_id == user_id, ChannelConnection.channel_type == ChannelType.telegram))
        if ch is None:
            ch = ChannelConnection(user_id=user_id, channel_type=ChannelType.telegram)
            db.add(ch)
        # Updated in place, so reconnecting keeps this channel's delivery history.
        ch.contact_encrypted = encrypt_contact(str(chat_id))
        ch.contact_hash = hashed
        ch.is_verified = True
        ch.verified_at = datetime.now(timezone.utc)
        ch.verification_code_hash = ch.code_expires_at = None
        ch.failed_attempts = 0
        db.commit()
    return True


def handle_update(update: dict) -> None:
    msg = update.get("message") or {}
    text: str = msg.get("text") or ""
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id or not text.startswith("/start"):
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        _reply(chat_id, "Hi! To get AI news here, sign up on the AI Newsletter website and press \"Open Telegram\".")
        return
    user_id = read_telegram_token(parts[1].strip())
    if user_id is None:
        _reply(chat_id, "This link has expired. Go back to the website and press \"Open Telegram\" again.")
        return
    if link_chat(user_id, chat_id):
        _reply(chat_id, "✅ Connected! Important AI news will arrive in this chat. You can go back to the website now.")
        log.info("Linked Telegram chat %s to user %s", chat_id, user_id)


# ---------- webhook mode ----------
@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if config.TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "Bad secret")
    handle_update(await request.json())
    return {"ok": True}


# ---------- polling mode ----------
_stop = threading.Event()


def _poll_forever() -> None:
    offset = 0
    try:
        _api("deleteWebhook")  # getUpdates does not work while a webhook is set
    except Exception as e:  # noqa: BLE001
        log.warning("deleteWebhook failed: %s", e)
    log.info("Telegram polling started for @%s", bot_username())
    while not _stop.is_set():
        try:
            updates = _api("getUpdates", offset=offset, timeout=25, allowed_updates=["message"])
            for u in updates:
                offset = u["update_id"] + 1
                handle_update(u)
        except Exception as e:  # noqa: BLE001
            log.warning("Telegram polling error: %s (retrying in 5 s)", e)
            _stop.wait(5)


def start_polling() -> None:
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_MODE != "polling":
        return
    threading.Thread(target=_poll_forever, name="telegram-poller", daemon=True).start()


def stop_polling() -> None:
    _stop.set()
