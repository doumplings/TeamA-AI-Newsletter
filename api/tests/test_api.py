"""API tests for sign-up, channel setup + code check, and the dashboard."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import ChannelConnection, ChannelType, NewsItem
from app.security import decrypt_contact, make_telegram_token, read_telegram_token
from app import telegram_bot
from collector.sources import default_sources

HOOK = "https://discord.com/api/webhooks/123456789/abcDEF_-xyz"


# ---------- auth ----------
def test_register_login_logout(client):
    r = client.post("/auth/register", json={"email": "A@Example.com", "password": "password123"})
    assert r.status_code == 201 and r.json()["email"] == "a@example.com"
    assert client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 200


def test_register_rejects_duplicate_and_short_password(client):
    client.post("/auth/register", json={"email": "x@example.com", "password": "password123"})
    client.post("/auth/logout")
    dup = client.post("/auth/register", json={"email": "x@example.com", "password": "password123"})
    assert dup.status_code == 409 and dup.json()["detail"]["fields"]["email"]
    assert client.post("/auth/register", json={"email": "y@example.com", "password": "short"}).status_code == 422


def test_channels_need_login(client):
    assert client.get("/channels").status_code == 401


# ---------- channel setup + code check ----------
def test_email_channel_verify_happy_path(signed_in, fakes):
    ch = signed_in.post("/channels", json={"channelType": "email", "contact": "seng@example.com"}).json()
    assert ch["isVerified"] is False and "•" in ch["maskedContact"]
    assert signed_in.post(f"/channels/{ch['channelId']}/test").json() == {"sent": True}
    code = fakes[ChannelType.email].last_code()
    r = signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": code}).json()
    assert r["ok"] is True and r["channel"]["isVerified"] is True


def test_wrong_codes_three_tries_then_new_code_needed(signed_in, fakes):
    ch = signed_in.post("/channels", json={"channelType": "discord", "contact": HOOK}).json()
    signed_in.post(f"/channels/{ch['channelId']}/test")
    real = fakes[ChannelType.discord].last_code()
    wrong = "000000" if real != "000000" else "111111"
    left = [signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": wrong}).json()["attemptsLeft"] for _ in range(3)]
    assert left == [2, 1, 0]
    # even the right code no longer works
    assert signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": real}).status_code == 410
    # a new code resets the tries
    signed_in.post(f"/channels/{ch['channelId']}/test")
    new = fakes[ChannelType.discord].last_code()
    assert signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": new}).json()["ok"] is True


def test_expired_code_rejected(signed_in, fakes):
    ch = signed_in.post("/channels", json={"channelType": "email", "contact": "seng@example.com"}).json()
    signed_in.post(f"/channels/{ch['channelId']}/test")
    code = fakes[ChannelType.email].last_code()
    with SessionLocal() as db:
        row = db.get(ChannelConnection, ch["channelId"])
        row.code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": code}).status_code == 410


def test_bad_contacts_rejected(signed_in):
    r = signed_in.post("/channels", json={"channelType": "discord", "contact": "https://evil.com/hook"})
    assert r.status_code == 422 and "contact" in r.json()["detail"]["fields"]
    assert signed_in.post("/channels", json={"channelType": "email", "contact": "nope"}).status_code == 422
    assert signed_in.post("/channels", json={"channelType": "telegram", "contact": "@me"}).status_code == 400


def test_send_failure_reported(signed_in, fakes):
    ch = signed_in.post("/channels", json={"channelType": "discord", "contact": HOOK}).json()
    fakes[ChannelType.discord].fail_next = True
    r = signed_in.post(f"/channels/{ch['channelId']}/test")
    assert r.status_code == 502 and "webhook" in r.json()["detail"]


def test_cannot_touch_someone_elses_channel(signed_in, client):
    ch = signed_in.post("/channels", json={"channelType": "email", "contact": "seng@example.com"}).json()
    client.post("/auth/logout")
    client.post("/auth/register", json={"email": "other@example.com", "password": "password123"})
    assert client.post(f"/channels/{ch['channelId']}/test").status_code == 404


def test_update_and_delete_channel(signed_in, fakes):
    ch = signed_in.post("/channels", json={"channelType": "email", "contact": "seng@example.com"}).json()
    r = signed_in.patch(f"/channels/{ch['channelId']}", json={"isEnabled": False, "minImportance": "low"}).json()
    assert r["isEnabled"] is False and r["minImportance"] == "low"
    assert signed_in.delete(f"/channels/{ch['channelId']}").status_code == 204
    assert signed_in.get("/channels").json() == []


# ---------- telegram link ----------
def test_telegram_token_roundtrip_and_tamper():
    tok = make_telegram_token(42)
    assert len(tok) <= 64 and read_telegram_token(tok) == 42
    assert read_telegram_token(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None
    assert read_telegram_token("garbage") is None


def test_telegram_start_links_verified_channel(signed_in, monkeypatch):
    monkeypatch.setattr(telegram_bot, "_reply", lambda *a, **k: None)
    me = signed_in.get("/auth/me").json()
    tok = make_telegram_token(me["userId"])
    telegram_bot.handle_update({"message": {"text": f"/start {tok}", "chat": {"id": 987654321}}})
    chans = signed_in.get("/channels").json()
    assert chans[0]["channelType"] == "telegram" and chans[0]["isVerified"] and chans[0]["maskedContact"].endswith("321")


def test_telegram_link_endpoint_without_bot(signed_in):
    assert signed_in.post("/channels/telegram/link").status_code == 503


# ---------- dashboard ----------
def test_profile_threshold_and_sources(signed_in):
    p = signed_in.get("/profile").json()
    everything = list(range(1, len(default_sources()) + 1))
    assert p["defaultThreshold"] == "high" and p["followedSourceIds"] == everything
    assert signed_in.put("/profile/threshold", json={"level": "medium"}).json()["defaultThreshold"] == "medium"
    assert signed_in.put("/profile/sources", json={"sourceIds": [1, 3]}).json()["followedSourceIds"] == [1, 3]
    assert signed_in.put("/profile/sources", json={"sourceIds": [999]}).status_code == 422
    # picking every source goes back to "follow all"
    assert signed_in.put("/profile/sources", json={"sourceIds": everything}).json()["followedSourceIds"] == everything


def test_sample_news_goes_to_history(signed_in, fakes):
    assert signed_in.post("/deliveries/sample").json() == {"delivered": 0, "failed": 0}
    ch = signed_in.post("/channels", json={"channelType": "email", "contact": "seng@example.com"}).json()
    signed_in.post(f"/channels/{ch['channelId']}/test")
    signed_in.post(f"/channels/{ch['channelId']}/verify", json={"code": fakes[ChannelType.email].last_code()})
    assert signed_in.post("/deliveries/sample").json() == {"delivered": 1, "failed": 0}
    h = signed_in.get("/history").json()
    assert h["totalPages"] == 1 and h["items"][0]["status"] == "sent" and h["items"][0]["title"].startswith("[Sample]")


def test_contact_is_encrypted_and_unique_per_account(signed_in, client):
    ch = signed_in.post("/channels", json={"channelType": "discord", "contact": HOOK}).json()
    with SessionLocal() as db:
        row = db.get(ChannelConnection, ch["channelId"])
        assert HOOK.encode() not in bytes(row.contact_encrypted) and decrypt_contact(row.contact_encrypted) == HOOK
    signed_in.post(f"/channels/{ch['channelId']}/test")
    # an unverified attempt does not block another account...
    client.post("/auth/logout")
    client.post("/auth/register", json={"email": "other@example.com", "password": "password123"})
    other = client.post("/channels", json={"channelType": "discord", "contact": HOOK})
    assert other.status_code == 201
    # ...but a verified channel does
    from app.adapters import REGISTRY  # the fakes
    client.post(f"/channels/{other.json()['channelId']}/test")
    client.post(f"/channels/{other.json()['channelId']}/verify", json={"code": REGISTRY[ChannelType.discord].last_code()})
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "seng@example.com", "password": "password123"})
    assert client.post("/channels", json={"channelType": "discord", "contact": HOOK}).status_code == 409


def test_latest_news_shows_collected_items_from_followed_sources(signed_in):
    with SessionLocal() as db:
        db.add_all([
            NewsItem(source_id=1, title="Collected from source 1", url="https://a.example/1", canonical_url="https://a.example/1"),
            NewsItem(source_id=2, title="Collected from source 2", url="https://b.example/2", canonical_url="https://b.example/2"),
        ])
        db.commit()
    signed_in.post("/deliveries/sample")  # samples never count as news
    titles = [n["title"] for n in signed_in.get("/news").json()]
    assert sorted(titles) == ["Collected from source 1", "Collected from source 2"]
    signed_in.put("/profile/sources", json={"sourceIds": [2]})
    news = signed_in.get("/news").json()
    assert [n["title"] for n in news] == ["Collected from source 2"] and news[0]["importanceLevel"] is None
