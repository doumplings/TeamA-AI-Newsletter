"""JSON shapes of the API (Table 8-4 in Report 2). Field names are camelCase on the wire."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .models import ChannelType, DeliveryStatus, ImportanceLevel, SourceType


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# ----- requests -----
class RegisterRequest(CamelModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(CamelModel):
    email: str
    password: str


class AddChannelRequest(CamelModel):
    channel_type: ChannelType
    contact: str = Field(max_length=500)


class VerifyRequest(CamelModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UpdateChannelRequest(CamelModel):
    is_enabled: bool
    min_importance: ImportanceLevel | None = None


class ThresholdRequest(CamelModel):
    level: ImportanceLevel


class SourcesRequest(CamelModel):
    source_ids: list[int]


# ----- views -----
class AccountView(CamelModel):
    user_id: int
    email: str
    role: str


class ChannelView(CamelModel):
    channel_id: int
    channel_type: ChannelType
    masked_contact: str
    is_enabled: bool
    is_verified: bool
    min_importance: ImportanceLevel | None


class SendTestResult(CamelModel):
    sent: bool


class VerifyResult(CamelModel):
    ok: bool
    attempts_left: int
    channel: ChannelView | None = None


class TelegramLinkView(CamelModel):
    url: str
    expires_in_seconds: int


class ProfileView(CamelModel):
    default_threshold: ImportanceLevel
    followed_source_ids: list[int]


class SourceView(CamelModel):
    source_id: int
    name: str
    source_type: SourceType
    url: str
    base_weight: int
    is_active: bool


class DeliveryView(CamelModel):
    delivery_id: int
    title: str
    link: str
    source_name: str
    importance_level: ImportanceLevel
    channel_type: ChannelType
    status: DeliveryStatus
    sent_at: datetime | None


class NewsView(CamelModel):
    item_id: int
    title: str
    link: str
    source_name: str
    summary: str | None
    importance_level: ImportanceLevel | None  # None until the classifier has scored it
    published_at: datetime


class HistoryPageView(CamelModel):
    items: list[DeliveryView]
    page: int
    total_pages: int


class SampleResult(CamelModel):
    delivered: int
    failed: int
