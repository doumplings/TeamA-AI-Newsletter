"""SubscriberController: profile, followed sources, history (UC-6, UC-7, UC-8),
plus a "send me a sample" endpoint so the dashboard can prove delivery works
before the real scraper and dispatcher are merged.
"""
import math
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import adapters
from ..adapters import Message
from ..db import get_db
from ..deps import current_user
from ..models import Channel, Delivery, DeliveryStatus, FollowedSource, ImportanceLevel, NewsItem, Profile, Source, User
from ..schemas import (
    DeliveryView,
    HistoryPageView,
    ProfileView,
    SampleResult,
    SourcesRequest,
    SourceView,
    ThresholdRequest,
)

router = APIRouter(tags=["subscriber"])
PAGE_SIZE = 10


def _profile_view(db: Session, user: User) -> ProfileView:
    profile = db.get(Profile, user.id)
    ids = list(db.scalars(select(FollowedSource.source_id).where(FollowedSource.user_id == user.id)))
    return ProfileView(default_threshold=profile.default_threshold, followed_source_ids=sorted(ids))


@router.get("/profile", response_model=ProfileView)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _profile_view(db, user)


@router.put("/profile/threshold", response_model=ProfileView)
def set_threshold(req: ThresholdRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.get(Profile, user.id).default_threshold = req.level
    db.commit()
    return _profile_view(db, user)


@router.put("/profile/sources", response_model=ProfileView)
def set_followed_sources(req: SourcesRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    wanted = set(req.source_ids)
    known = set(db.scalars(select(Source.id).where(Source.id.in_(wanted))))
    if unknown := wanted - known:
        raise HTTPException(422, f"Unknown source ids: {sorted(unknown)}")
    db.execute(delete(FollowedSource).where(FollowedSource.user_id == user.id))
    db.add_all(FollowedSource(user_id=user.id, source_id=sid) for sid in wanted)
    db.commit()
    return _profile_view(db, user)


@router.get("/sources", response_model=list[SourceView])
def list_sources(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Source).where(Source.is_active).order_by(Source.id))
    return [
        SourceView(source_id=s.id, name=s.name, source_type=s.source_type, url=s.url, base_weight=s.base_weight, is_active=s.is_active)
        for s in rows
    ]


@router.get("/history", response_model=HistoryPageView)
def get_history(page: int = Query(1, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Delivery).where(Delivery.user_id == user.id)) or 0
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    rows = db.scalars(
        select(Delivery)
        .where(Delivery.user_id == user.id)
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    items = [
        DeliveryView(
            delivery_id=d.id,
            title=d.item.title,
            link=d.item.link,
            source_name=d.item.source.name,
            importance_level=d.item.importance_level,
            channel_type=d.channel_type,
            status=d.status,
            sent_at=d.sent_at,
        )
        for d in rows
    ]
    return HistoryPageView(items=items, page=page, total_pages=total_pages)


SAMPLE_NEWS = [
    ("New open-weight model released for developers", ImportanceLevel.high),
    ("Older API model versions to be retired next quarter", ImportanceLevel.high),
    ("New pricing announced for embedding models", ImportanceLevel.medium),
    ("AI startup raises new funding round", ImportanceLevel.medium),
    ("Research post: evaluating tool use in language models", ImportanceLevel.low),
]


@router.post("/deliveries/sample", response_model=SampleResult)
def send_sample(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Send one sample item to every verified, enabled channel and record it in history."""
    channels = db.scalars(select(Channel).where(Channel.user_id == user.id, Channel.is_verified, Channel.is_enabled)).all()
    if not channels:
        return SampleResult(delivered=0, failed=0)

    source = db.scalars(select(Source).order_by(Source.id)).first()
    title, level = random.choice(SAMPLE_NEWS)
    item = NewsItem(source_id=source.id, title=f"[Sample] {title}", link=source.url, importance_level=level)
    db.add(item)
    db.flush()

    delivered = failed = 0
    for ch in channels:
        result = adapters.for_type(ch.channel_type).send(
            ch.contact,
            Message(
                subject=f"[{level.value.upper()}] {item.title}",
                text=f"From {source.name}. This is a sample notification from AI Newsletter.",
                link=item.link,
            ),
        )
        d = Delivery(user_id=user.id, item_id=item.id, channel_id=ch.id, channel_type=ch.channel_type, attempts=1)
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
