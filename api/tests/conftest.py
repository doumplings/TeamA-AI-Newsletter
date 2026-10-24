import os
import re
from pathlib import Path

import psycopg
import pytest

# A throwaway PostgreSQL database built from schema.sql, and no real Telegram/SMTP.
TEST_DB = os.environ.get("TEST_DATABASE_NAME", "ainews_test")
os.environ["DATABASE_URL"] = f"postgresql+psycopg:///{TEST_DB}"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["SECRET_KEY"] = "test-secret"

SCHEMA = Path(__file__).resolve().parents[2] / "schema.sql"


def _create_test_database() -> None:
    try:
        with psycopg.connect("dbname=postgres", autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError as e:
        pytest.exit(f"Tests need a local PostgreSQL server: {e}", returncode=2)
    with psycopg.connect(f"dbname={TEST_DB}", autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())


_create_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import adapters  # noqa: E402
from app.adapters import ChannelAdapter, SendResult  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


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
    with engine.begin() as conn:
        tables = conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    with TestClient(app) as c:  # startup seeds the collector's sources
        yield c


@pytest.fixture()
def signed_in(client):
    r = client.post("/auth/register", json={"email": "seng@example.com", "password": "password123"})
    assert r.status_code == 201
    return client
