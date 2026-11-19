"""Channel adapters (UC-14). UT-26 to UT-28 from Report 2: contact formats, the message, and how replies are read."""
from types import SimpleNamespace

import httpx
import pytest

from app import adapters
from app.adapters import DiscordAdapter, EmailAdapter, Message, TelegramAdapter
from models import ImportanceLevel

HOOK = "https://discord.com/api/webhooks/123456789/abcDEF_-xyz"
STORY = SimpleNamespace(title="Acme launches Nova", summary="A new   model\nfor everyone.", body=None,
                        url="https://acme.example/nova", importance_level=ImportanceLevel.high)


def reply(status, json=None, headers=None):
    return httpx.Response(status, json=json if json is not None else {}, headers=headers or {})


@pytest.fixture()
def post(monkeypatch):
    """Replace the HTTP call; the test sets ``post.reply`` and reads ``post.calls``."""
    def fake(url, **kwargs):
        fake.calls.append((url, kwargs))
        return fake.reply
    fake.calls, fake.reply = [], reply(200)
    monkeypatch.setattr(adapters.httpx, "post", fake)
    return fake


def test_ut26_each_adapter_accepts_only_its_own_contact_format():
    assert DiscordAdapter().validate_contact(HOOK) is None
    assert DiscordAdapter().validate_contact("https://example.com/api/webhooks/1/abc")
    assert EmailAdapter().validate_contact("seng@example.com") is None
    assert EmailAdapter().validate_contact(HOOK)


@pytest.mark.parametrize("adapter", [TelegramAdapter(), DiscordAdapter(), EmailAdapter()])
def test_ut27_message_has_source_headline_level_summary_and_link(adapter):
    message = adapter.format_message(STORY, "Acme Blog")
    assert message.subject == "Acme launches Nova"          # the email subject is the headline
    assert "High importance" in message.text and "Acme Blog" in message.text
    assert "A new model for everyone." in message.text and message.link == STORY.url


def test_a_long_summary_is_shortened_and_a_missing_one_is_left_out():
    long = SimpleNamespace(**{**vars(STORY), "summary": "word " * 200})
    assert len(DiscordAdapter().format_message(long, "Acme Blog").text) < 360
    bare = SimpleNamespace(**{**vars(STORY), "summary": None})
    assert DiscordAdapter().format_message(bare, "Acme Blog").text == "High importance · Acme Blog"


def test_ut28_discord_reads_200_429_and_404(post):
    message = Message("Acme launches Nova", "High importance · Acme Blog", STORY.url)
    post.reply = reply(204)
    assert DiscordAdapter().send(HOOK, message).ok
    content = post.calls[0][1]["json"]
    assert "Acme launches Nova" in content["content"] and STORY.url in content["content"]
    assert content["allowed_mentions"] == {"parse": []}

    post.reply = reply(429, {"retry_after": 12.5})
    limited = DiscordAdapter().send(HOOK, message)
    assert (limited.ok, limited.permanent, limited.retry_after) == (False, False, 12.5)

    post.reply = reply(404)
    gone = DiscordAdapter().send(HOOK, message)
    assert (gone.ok, gone.permanent) == (False, True)

    post.reply = reply(502)
    assert DiscordAdapter().send(HOOK, message).permanent is False


def test_ut28_telegram_reads_200_429_and_403(post, monkeypatch):
    monkeypatch.setattr(adapters.config, "TELEGRAM_BOT_TOKEN", "123:test")
    message = Message("Acme launches Nova", "High importance · Acme Blog", STORY.url)
    assert TelegramAdapter().send("42", message).ok
    assert post.calls[0][1]["json"]["chat_id"] == "42"

    post.reply = reply(429, {"ok": False, "parameters": {"retry_after": 30}})
    limited = TelegramAdapter().send("42", message)
    assert (limited.permanent, limited.retry_after) == (False, 30.0)

    post.reply = reply(403, {"ok": False, "description": "Forbidden: bot was blocked by the user"})
    assert TelegramAdapter().send("42", message).permanent is True


def test_a_network_error_is_retried_and_never_stores_the_address(post, monkeypatch):
    def down(url, **kwargs):
        raise httpx.ConnectError(f"cannot reach {url}")
    monkeypatch.setattr(adapters.httpx, "post", down)
    result = DiscordAdapter().send(HOOK, Message("s", "t"))
    assert (result.ok, result.permanent) == (False, False) and "webhooks" not in result.error
