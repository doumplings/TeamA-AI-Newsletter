import os
import re
import tempfile

import pytest

# Use a throwaway database and no real Telegram/SMTP for tests.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app import adapters  # noqa: E402
from app.adapters import ChannelAdapter, SendResult  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app, init_db  # noqa: E402


class FakeAdapter(ChannelAdapter):
    """Records messages instead of sending them (the fakes from Section 11)."""

    def __init__(self, real: ChannelAdapter):
        self.real = real
        self.channel_type = real.channel_type
        self.sent: list[tuple[str, str]] = []
        self.fail_next = False

    def validate_contact(self, contact):
        return self.real.validate_contact(contact)

    def mask(self, contact):
        return self.real.mask(contact)

    def send(self, contact, message):
        if self.fail_next:
            self.fail_next = False
            return SendResult(False, True, "webhook gone")
        self.sent.append((contact, message.subject + " " + message.text))
        return SendResult(True)

    def last_code(self) -> str:
        return re.search(r"\b(\d{6})\b", self.sent[-1][1]).group(1)


@pytest.fixture()
def fakes(monkeypatch):
    f = {t: FakeAdapter(a) for t, a in adapters.REGISTRY.items()}
    monkeypatch.setattr(adapters, "REGISTRY", f)
    return f


@pytest.fixture()
def client(fakes):
    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def signed_in(client):
    r = client.post("/auth/register", json={"email": "seng@example.com", "password": "password123"})
    assert r.status_code == 201
    return client
