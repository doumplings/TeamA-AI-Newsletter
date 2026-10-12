"""Channel adapters: how a message actually reaches Telegram, Discord, or email.

Mirrors ChannelAdapter / TelegramAdapter / DiscordAdapter / EmailAdapter from
Section 8 (Notification package). The web API uses them for test messages and
the "send me a sample" button; the worker's Dispatcher can reuse the same ones.

Adapters are looked up in a dictionary by channel type (Table 9-3), so adding
a new channel later means writing one class and adding one entry.
"""
from __future__ import annotations

import html
import logging
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from . import config
from .models import ChannelType

log = logging.getLogger("ainews.adapters")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
DISCORD_WEBHOOK_RE = re.compile(
    r"^https://(?:ptb\.|canary\.)?(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$"
)


@dataclass
class Message:
    subject: str
    text: str
    link: str | None = None


@dataclass
class SendResult:
    ok: bool
    permanent: bool = False  # True when retrying cannot help (e.g. deleted webhook)
    error: str | None = None


class ChannelAdapter:
    channel_type: ChannelType

    def validate_contact(self, contact: str) -> str | None:
        """Return an error message, or None if the contact looks right."""
        return None

    def mask(self, contact: str) -> str:
        return "•••" + contact[-3:]

    def send(self, contact: str, message: Message) -> SendResult:
        raise NotImplementedError


class TelegramAdapter(ChannelAdapter):
    channel_type = ChannelType.telegram

    def mask(self, contact: str) -> str:
        return f"Telegram chat •••{contact[-3:]}"

    def send(self, contact: str, message: Message) -> SendResult:
        if not config.TELEGRAM_BOT_TOKEN:
            return SendResult(False, True, "Telegram bot is not configured on the server.")
        text = f"<b>{html.escape(message.subject)}</b>\n\n{html.escape(message.text)}"
        if message.link:
            text += f'\n\n<a href="{html.escape(message.link)}">Read more</a>'
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": contact, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
                timeout=15,
            )
        except httpx.HTTPError as e:
            return SendResult(False, False, f"Network error: {e}")
        if r.status_code == 200:
            return SendResult(True)
        # 400/403: chat not found or the user blocked the bot -> retrying will not help
        return SendResult(False, r.status_code in (400, 403), f"Telegram said {r.status_code}: {r.text[:200]}")


class DiscordAdapter(ChannelAdapter):
    channel_type = ChannelType.discord

    def validate_contact(self, contact: str) -> str | None:
        if not DISCORD_WEBHOOK_RE.match(contact):
            return "Should look like https://discord.com/api/webhooks/123.../abc..."
        return None

    def mask(self, contact: str) -> str:
        hook_id = contact.split("/webhooks/")[1].split("/")[0] if "/webhooks/" in contact else ""
        return f"Webhook •••{hook_id[-4:]}"

    def send(self, contact: str, message: Message) -> SendResult:
        content = f"**{message.subject}**\n{message.text}"
        if message.link:
            content += f"\n{message.link}"
        try:
            r = httpx.post(contact, json={"content": content[:2000], "username": "AI Newsletter"}, timeout=15)
        except httpx.HTTPError as e:
            return SendResult(False, False, f"Network error: {e}")
        if r.status_code in (200, 204):
            return SendResult(True)
        if r.status_code in (401, 403, 404):
            return SendResult(False, True, "This Discord webhook no longer exists. Create a new one.")
        return SendResult(False, False, f"Discord said {r.status_code}")


class EmailAdapter(ChannelAdapter):
    channel_type = ChannelType.email

    def validate_contact(self, contact: str) -> str | None:
        if not EMAIL_RE.match(contact):
            return "That does not look like an email address."
        return None

    def mask(self, contact: str) -> str:
        name, _, domain = contact.partition("@")
        return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"

    def send(self, contact: str, message: Message) -> SendResult:
        body = message.text + (f"\n\nRead more: {message.link}" if message.link else "")
        if not config.SMTP_HOST:
            # Dev fallback: no mail server configured, so print the email instead.
            log.warning("SMTP not configured. Email to %s:\n  Subject: %s\n  %s", contact, message.subject, body)
            print(f"\n=== EMAIL (console mode) to {contact} ===\nSubject: {message.subject}\n{body}\n", flush=True)
            return SendResult(True)
        msg = EmailMessage()
        msg["From"] = config.SMTP_FROM
        msg["To"] = contact
        msg["Subject"] = message.subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                s.starttls()
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
            return SendResult(True)
        except smtplib.SMTPRecipientsRefused:
            return SendResult(False, True, "The mail server refused this address.")
        except (smtplib.SMTPException, OSError) as e:
            return SendResult(False, False, f"Email error: {e}")


# Channel type -> adapter (ChannelAdapter.forType)
REGISTRY: dict[ChannelType, ChannelAdapter] = {
    ChannelType.telegram: TelegramAdapter(),
    ChannelType.discord: DiscordAdapter(),
    ChannelType.email: EmailAdapter(),
}


def for_type(channel_type: ChannelType) -> ChannelAdapter:
    return REGISTRY[channel_type]
