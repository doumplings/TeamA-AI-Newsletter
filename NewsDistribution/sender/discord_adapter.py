"""Discord channel adapter: posts to a Discord webhook URL.

No bot or token is needed; the webhook URL itself is the credential
(stored encrypted in channel_connection.contact_address, REQ-18).
Never log the full URL.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from .base import ChannelAdapter, Message, SendResult

log = logging.getLogger(__name__)

WEBHOOK_RE = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/"
    r"\d{15,25}/[\w-]{20,}/?$"
)

MAX_CONTENT = 2000          # Discord's hard limit for message content
TIMEOUT_SECONDS = 10


def _level_name(level) -> str:
    """Accepts 'high', 'High', or an enum with .value / .name."""
    raw = getattr(level, "value", level)
    return str(raw or "low").lower()


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _mask(url: str) -> str:
    """Keep the webhook ID, hide the secret token, for safe logging."""
    return re.sub(r"(/webhooks/\d+/).+", r"\1***", url)


class DiscordAdapter(ChannelAdapter):
    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()

    # ---- contact check (used by POST /channels, UC-2 / UC-4) ----
    def validate_contact(self, contact: str) -> bool:
        return bool(contact and WEBHOOK_RE.match(contact.strip()))

    # ---- same five elements as every channel: source, headline,
    #      importance, one-line summary, link (Report 2, UC-14) ----
    def format_message(self, item) -> Message:
        level = _level_name(getattr(item, "importance_level", None))
        source = getattr(item, "source_name", None) or getattr(
            getattr(item, "source", None), "name", "Unknown source"
        )
        url = item.url
        header = f"**[{level.upper()}]** {source}"
        title = f"**{_truncate(item.title, 300)}**"
        # leave room for the header, title, link and newlines
        room = MAX_CONTENT - len(header) - len(title) - len(url) - 10
        summary = _truncate(getattr(item, "summary", ""), max(room, 0))
        parts = [header, title]
        if summary:
            parts.append(summary)
        parts.append(url)
        return Message(text="\n".join(parts), link=url)

    # ---- one HTTP attempt; retries are the RetryHandler's job ----
    def send(self, contact: str, message: Message) -> SendResult:
        if not self.validate_contact(contact):
            return SendResult(ok=False, permanent=True, error="Invalid Discord webhook URL")

        payload = {
            "content": _truncate(message.text, MAX_CONTENT),
            # stop headlines containing @everyone / @here from pinging people
            "allowed_mentions": {"parse": []},
        }
        try:
            resp = self._session.post(contact.strip(), json=payload, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            log.warning("Discord network error for %s: %s", _mask(contact), exc)
            return SendResult(ok=False, error=f"Network error: {exc.__class__.__name__}")

        if resp.status_code in (200, 204):
            return SendResult(ok=True)

        if resp.status_code == 429:
            return SendResult(ok=False, error="Rate limited by Discord",
                              retry_after=self._retry_after(resp))

        error = f"Discord returned HTTP {resp.status_code}"
        log.warning("%s for %s", error, _mask(contact))

        # 401/403/404: webhook deleted, token changed, or no access -> never recovers
        if resp.status_code in (401, 403, 404):
            return SendResult(ok=False, permanent=True, error=error)
        # 5xx and anything else: Discord side or our payload; worth another try
        return SendResult(ok=False, error=error)

    def send_test(self, contact: str, code: str) -> SendResult:
        text = (
            "**AI Newsletter: verify this channel**\n"
            f"Your verification code is **{code}**. Enter it in the app to finish setup."
        )
        return self.send(contact, Message(text=text, link=""))

    @staticmethod
    def _retry_after(resp: requests.Response) -> Optional[float]:
        try:
            return float(resp.json()["retry_after"])      # seconds, may be fractional
        except (ValueError, KeyError, TypeError):
            pass
        try:
            return float(resp.headers["Retry-After"])
        except (KeyError, ValueError):
            return None
