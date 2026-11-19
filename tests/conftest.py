"""Shared fixtures for the pipeline tests (classifier, deduplicator, dispatcher, scheduler).

Database tests run against a throwaway PostgreSQL database built from schema.sql,
found through the usual libpq settings (PGHOST, PGPORT, PGUSER), like the API tests.
Tests that need no database still run when PostgreSQL is not available.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text

# No real Telegram or SMTP, and a fixed key for the contact cipher.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["SMTP_HOST"] = ""

import notifier  # noqa: E402,F401  (puts api/ on the import path, for app.adapters)
from models import (ChannelConnection, ChannelType, ImportanceLevel, NewsItem, Source, SourceType,  # noqa: E402
                    SubscriberProfile, User, make_engine, make_session_factory)

TEST_DB = os.environ.get("PIPELINE_TEST_DATABASE_NAME", "ainews_pipeline_test")
SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


@pytest.fixture(scope="session")
def engine():
    try:
        with psycopg.connect("dbname=postgres", autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"needs a local PostgreSQL server: {e}")
    with psycopg.connect(f"dbname={TEST_DB}", autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    engine = make_engine(f"postgresql+psycopg:///{TEST_DB}")
    yield engine
    engine.dispose()


@pytest.fixture()
def factory(engine):
    """A session factory on an empty database."""
    with engine.begin() as conn:
        tables = conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    return make_session_factory(engine)


class Make:
    """Small builders for the rows a test needs."""

    def __init__(self, factory):
        self.factory = factory
        self._n = 0

    def source(self, name="Official Blog", weight=30, **extra):
        self._n += 1
        with self.factory.begin() as db:
            source = Source(name=name, source_type=SourceType.rss, url=f"https://source{self._n}.example/feed.xml",
                            base_weight=weight, config={}, **extra)
            db.add(source)
            db.flush()
            return source.source_id

    def item(self, source_id, title, summary=None, published_at=None, **extra):
        self._n += 1
        with self.factory.begin() as db:
            url = f"https://news.example/story-{self._n}"
            item = NewsItem(source_id=source_id, title=title, summary=summary, url=url, canonical_url=url,
                            published_at=published_at or datetime.now(timezone.utc) - timedelta(minutes=5), **extra)
            db.add(item)
            db.flush()
            return item.item_id

    def subscriber(self, threshold=ImportanceLevel.high, follows_all=True):
        self._n += 1
        with self.factory.begin() as db:
            user = User(email=f"user{self._n}@example.com", password_hash="x")
            user.profile = SubscriberProfile(default_threshold=threshold, follows_all=follows_all)
            db.add(user)
            db.flush()
            return user.user_id

    def channel(self, user_id, channel_type=ChannelType.discord, verified=True, enabled=True, min_importance=None):
        self._n += 1
        contact = f"contact-{self._n}"
        with self.factory.begin() as db:
            channel = ChannelConnection(
                user_id=user_id, channel_type=channel_type, contact_encrypted=contact.encode(),
                contact_hash=f"{self._n:064d}", is_enabled=enabled, is_verified=verified,
                verified_at=datetime.now(timezone.utc) if verified else None, min_importance=min_importance)
            db.add(channel)
            db.flush()
            return channel.channel_id


@pytest.fixture()
def make(factory):
    return Make(factory)
