"""Tables used by the web API.

This is a trimmed-down version of the schema in Report 2, Section 6.2: only the
tables the web app needs for sign-up, channels, profile, and history. When the
team's schema.sql / migrations are merged, these models should be pointed at
those tables instead.
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportanceLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]


class ChannelType(str, Enum):
    telegram = "telegram"
    email = "email"
    discord = "discord"


class DeliveryStatus(str, Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"
    permanent_failure = "permanent_failure"


class SourceType(str, Enum):
    rss = "rss"
    html = "html"
    api = "api"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="subscriber")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    channels: Mapped[list["Channel"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """Only the SHA-256 of the session token is stored, never the token itself."""
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_threshold: Mapped[ImportanceLevel] = mapped_column(SAEnum(ImportanceLevel), default=ImportanceLevel.high)
    user: Mapped[User] = relationship(back_populates="profile")
    followed: Mapped[list["FollowedSource"]] = relationship(cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType))
    url: Mapped[str] = mapped_column(String(500))
    base_weight: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FollowedSource(Base):
    __tablename__ = "followed_sources"
    user_id: Mapped[int] = mapped_column(ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel_type: Mapped[ChannelType] = mapped_column(SAEnum(ChannelType))
    # TODO (REQ-18): encrypt with ContactCipher before storing.
    contact: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    min_importance: Mapped[ImportanceLevel | None] = mapped_column(SAEnum(ImportanceLevel), nullable=True)
    # Verification state (UC-5). Only the hash of the code is stored.
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="channels")


class NewsItem(Base):
    __tablename__ = "news_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(1000))
    importance_level: Mapped[ImportanceLevel] = mapped_column(SAEnum(ImportanceLevel))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[Source] = relationship()


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("item_id", "channel_id", name="uq_delivery_item_channel"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    channel_type: Mapped[ChannelType] = mapped_column(SAEnum(ChannelType))  # kept so history survives channel removal
    status: Mapped[DeliveryStatus] = mapped_column(SAEnum(DeliveryStatus), default=DeliveryStatus.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    item: Mapped[NewsItem] = relationship()
