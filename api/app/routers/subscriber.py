"""SubscriberController: profile, followed sources, history, latest news (UC-6, UC-7, UC-8),
plus a "send me a sample" endpoint so the dashboard can prove delivery works
before the classifier and dispatcher are merged.
"""
import math
import random
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import adapters
from ..adapters import Message
from ..db import get_db
from ..deps import current_user
from ..models import (
    ChannelConnection,
    Delivery,
    DeliveryStatus,
    FollowedSource,
    ImportanceLevel,
    NewsItem,
    Source,
    SubscriberProfile,
    User,
)
from ..schemas import (
    DeliveryView,
    HistoryPageView,
    NewsView,
    ProfileView,
    SampleResult,
    SourcesRequest,
    SourceView,
    ThresholdRequest,
)
from ..security import decrypt_contact

router = APIRouter(tags=["subscriber"])
PAGE_SIZE = 10

# Sample items get a unique fake URL with this marker, so they never show up as real news.
SAMPLE_URL_MARK = "#ainews-sample-"


def _active_source_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Source.source_id).where(Source.is_active).order_by(Source.source_id)))


def _followed_ids(db: Session, profile: SubscriberProfile) -> list[int]:
    # follows_all (C8): the subscriber gets every source, including ones added later.
    if profile.follows_all:
        return _active_source_ids(db)
    return sorted(db.scalars(select(FollowedSource.source_id).where(FollowedSource.user_id == profile.user_id)))


def _profile_view(db: Session, user: User) -> ProfileView:
    profile = db.get(SubscriberProfile, user.user_id)
    return ProfileView(default_threshold=profile.default_threshold, followed_source_ids=_followed_ids(db, profile))


@router.get("/profile", response_model=ProfileView)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _profile_view(db, user)


@router.put("/profile/threshold", response_model=ProfileView)
def set_threshold(req: ThresholdRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.get(SubscriberProfile, user.user_id)
    profile.default_threshold = req.level
    profile.updated_at = func.now()
    db.commit()
    return _profile_view(db, user)


@router.put("/profile/sources", response_model=ProfileView)
def set_followed_sources(req: SourcesRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    wanted = set(req.source_ids)
    known = set(db.scalars(select(Source.source_id).where(Source.source_id.in_(wanted))))
    if unknown := wanted - known:
        raise HTTPException(422, f"Unknown source ids: {sorted(unknown)}")
    profile = db.get(SubscriberProfile, user.user_id)
    db.execute(delete(FollowedSource).where(FollowedSource.user_id == user.user_id))
    # Picking every source means "follow all", so sources added later are included too.
    profile.follows_all = wanted >= set(_active_source_ids(db))
    if not profile.follows_all:
        db.add_all(FollowedSource(user_id=user.user_id, source_id=sid) for sid in wanted)
    profile.updated_at = func.now()
    db.commit()
    return _profile_view(db, user)


@router.get("/sources", response_model=list[SourceView])
def list_sources(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Source).where(Source.is_active).order_by(Source.source_id))
    return [
        SourceView(source_id=s.source_id, name=s.name, source_type=s.source_type, url=s.url, base_weight=s.base_weight, is_active=s.is_active)
        for s in rows
    ]


@router.get("/news", response_model=list[NewsView])
def latest_news(limit: int = Query(10, ge=1, le=50), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Newest items the collector stored from the sources this subscriber follows."""
    profile = db.get(SubscriberProfile, user.user_id)
    stmt = (
        select(NewsItem, Source.name)
        .join(Source)
        .where(NewsItem.duplicate_of.is_(None), ~NewsItem.canonical_url.contains(SAMPLE_URL_MARK))
        .order_by(func.coalesce(NewsItem.published_at, NewsItem.collected_at).desc(), NewsItem.item_id.desc())
        .limit(limit)
    )
    if not profile.follows_all:
        stmt = stmt.where(NewsItem.source_id.in_(select(FollowedSource.source_id).where(FollowedSource.user_id == user.user_id)))
    return [
        NewsView(
            item_id=item.item_id,
            title=item.title,
            link=item.url,
            source_name=name,
            summary=item.summary,
            importance_level=item.importance_level,
            published_at=item.published_at or item.collected_at,
        )
        for item, name in db.execute(stmt)
    ]


@router.get("/history", response_model=HistoryPageView)
def get_history(page: int = Query(1, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Deliveries reach the subscriber through their channels. A removed channel
    # keeps its deliveries (channel_id becomes NULL, C2) but they leave this list.
    mine = select(Delivery, ChannelConnection.channel_type).join(ChannelConnection).where(ChannelConnection.user_id == user.user_id)
    total = db.scalar(select(func.count()).select_from(mine.subquery())) or 0
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    rows = db.execute(
        mine.order_by(Delivery.created_at.desc(), Delivery.delivery_id.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    ).all()
    items = [
        DeliveryView(
            delivery_id=d.delivery_id,
            title=d.item.title,
            link=d.item.url,
            source_name=d.item.source.name,
            importance_level=d.item.importance_level,
            channel_type=channel_type,
            status=d.status,
            sent_at=d.sent_at,
        )
        for d, channel_type in rows
    ]
    return HistoryPageView(items=items, page=page, total_pages=total_pages)


SAMPLE_NEWS = [
    ("New open-weight model released for developers", ImportanceLevel.high),
    ("Older API model versions to be retired next quarter", ImportanceLevel.high),
    ("New pricing announced for embedding models", ImportanceLevel.medium),
    ("AI startup raises new funding round", ImportanceLevel.medium),
    ("Research post: evaluating tool use in language models", ImportanceLevel.low),
]
# A score inside each level's band (Section 6.3.2), since the schema stores both.
SAMPLE_SCORE = {ImportanceLevel.high: Decimal(80), ImportanceLevel.medium: Decimal(50), ImportanceLevel.low: Decimal(20)}


@router.post("/deliveries/sample", response_model=SampleResult)
def send_sample(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Send one sample item to every verified, enabled channel and record it in history."""
    channels = db.scalars(
        select(ChannelConnection).where(ChannelConnection.user_id == user.user_id, ChannelConnection.is_verified, ChannelConnection.is_enabled)
    ).all()
    if not channels:
        return SampleResult(delivered=0, failed=0)

    source = db.scalars(select(Source).where(Source.is_active).order_by(Source.source_id)).first()
    if source is None:
        raise HTTPException(503, "No news sources yet. Start the API once so it can add them.")
    title, level = random.choice(SAMPLE_NEWS)
    now = datetime.now(timezone.utc)
    # Already classified and dispatched, so the real pipeline never picks it up again.
    item = NewsItem(
        source_id=source.source_id,
        title=f"[Sample] {title}",
        url=source.url,
        canonical_url=f"{source.url}{SAMPLE_URL_MARK}{secrets.token_hex(8)}",
        importance_score=SAMPLE_SCORE[level],
        importance_level=level,
        classified_at=now,
        dispatched_at=now,
    )
    db.add(item)
    db.flush()

    delivered = failed = 0
    for ch in channels:
        result = adapters.for_type(ch.channel_type).send(
            decrypt_contact(ch.contact_encrypted),
            Message(
                subject=f"[{level.value.upper()}] {item.title}",
                text=f"From {source.name}. This is a sample notification from AI Newsletter.",
                link=item.url,
            ),
        )
        d = Delivery(item_id=item.item_id, channel_id=ch.channel_id, attempts=1)
        if result.ok:
            d.status, d.sent_at = DeliveryStatus.sent, datetime.now(timezone.utc)
            delivered += 1
        else:
            d.status = DeliveryStatus.permanent_failure if result.permanent else DeliveryStatus.failed
            d.last_error = result.error
            failed += 1
        db.add(d)
    db.commit()
    return SampleResult(delivered=delivered, failed=failed)
