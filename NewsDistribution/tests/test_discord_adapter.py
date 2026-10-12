from types import SimpleNamespace
from unittest.mock import MagicMock

import requests

from sender import DiscordAdapter

URL = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz_-0123"


def make(status, json_body=None, headers=None):
    resp = MagicMock(status_code=status, headers=headers or {})
    if json_body is None:
        resp.json.side_effect = ValueError
    else:
        resp.json.return_value = json_body
    session = MagicMock()
    session.post.return_value = resp
    return DiscordAdapter(session), session


def item(**kw):
    base = dict(title="OpenAI ships new model", summary="A short summary.",
                url="https://example.com/a", source_name="TechCrunch",
                importance_level="high")
    base.update(kw)
    return SimpleNamespace(**base)


def test_validate_contact():
    a = DiscordAdapter()
    assert a.validate_contact(URL)
    assert not a.validate_contact("https://example.com/api/webhooks/1/x")
    assert not a.validate_contact("http://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz")
    assert not a.validate_contact("")


def test_format_has_five_elements():
    m = DiscordAdapter().format_message(item())
    for part in ("TechCrunch", "OpenAI ships new model", "HIGH", "A short summary.", "https://example.com/a"):
        assert part in m.text
    assert m.link == "https://example.com/a"


def test_format_truncates_long_summary():
    m = DiscordAdapter().format_message(item(summary="x" * 5000))
    assert len(m.text) <= 2000 and m.text.endswith("https://example.com/a")


def test_send_ok_and_blocks_mentions():
    a, s = make(204)
    r = a.send(URL, a.format_message(item(title="@everyone hi")))
    assert r.ok
    assert s.post.call_args.kwargs["json"]["allowed_mentions"] == {"parse": []}


def test_rate_limit_returns_retry_after():
    a, _ = make(429, {"retry_after": 1.5})
    r = a.send(URL, a.format_message(item()))
    assert not r.ok and not r.permanent and r.retry_after == 1.5


def test_deleted_webhook_is_permanent():
    a, _ = make(404, {"code": 10015})
    r = a.send(URL, a.format_message(item()))
    assert not r.ok and r.permanent


def test_server_error_is_retryable():
    a, _ = make(503)
    r = a.send(URL, a.format_message(item()))
    assert not r.ok and not r.permanent


def test_network_error_is_retryable():
    a, s = make(204)
    s.post.side_effect = requests.ConnectionError("boom")
    r = a.send(URL, a.format_message(item()))
    assert not r.ok and not r.permanent


def test_invalid_url_is_permanent_without_http_call():
    a, s = make(204)
    r = a.send("not a url", a.format_message(item()))
    assert r.permanent and not s.post.called


def test_send_test_contains_code():
    a, s = make(204)
    assert a.send_test(URL, "123456").ok
    assert "123456" in s.post.call_args.kwargs["json"]["content"]
