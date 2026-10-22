"""The API's data classes come from the shared root ``models.py`` (schema.sql).

Re-exported here so the routers keep importing from ``.models``. Tables are
created by ``psql -f schema.sql``, never by the API.
"""
from models import (  # noqa: F401
    ChannelConnection,
    ChannelType,
    Delivery,
    DeliveryStatus,
    FollowedSource,
    ImportanceLevel,
    NewsItem,
    Source,
    SourceType,
    SubscriberProfile,
    User,
    UserRole,
    UserSession,
)
