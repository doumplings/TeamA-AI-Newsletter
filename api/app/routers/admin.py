"""SourceAdminController: administrators manage the monitored sources (UC-9),
plus a read-only view of the pipeline (cycle runs and queue sizes) for the admin dashboard.

The API never starts a cycle: the worker (``python -m scheduler``) runs them, and the
two processes only share the database (Section 5.4).
"""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import (
    ChannelConnection,
    CycleRun,
    Delivery,
    DeliveryStatus,
    ImportanceLevel,
    NewsItem,
    Source,
    User,
    UserRole,
)
from ..schemas import (
    AdminSourceRequest,
    AdminSourceUpdate,
    AdminSourceView,
    CycleRunView,
    PipelineCounts,
    PipelineStatusView,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
RECENT_RUNS = 30
DEFAULT_MIN_INTERVAL_SECONDS = 5


def _view(source: Source, item_count: int) -> AdminSourceView:
    return AdminSourceView(
        source_id=source.source_id,
        name=source.name,
        source_type=source.source_type,
        url=source.url,
        base_weight=source.base_weight,
        is_active=source.is_active,
        terms_url=source.config.get("terms_url"),
        config=source.config,
        last_checked_at=source.last_checked_at,
        last_success_at=source.last_success_at,
        consecutive_failures=source.consecutive_failures,
        last_error=source.last_error,
        item_count=item_count,
    )


def _item_count(db: Session, source_id: int) -> int:
    return db.scalar(select(func.count()).select_from(NewsItem).where(NewsItem.source_id == source_id)) or 0


def _is_web_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password


def _check_urls(url: str | None, terms_url: str | None) -> None:
    fields = {}
    if url is not None and not _is_web_url(url):
        fields["url"] = "Should be a web address starting with https://"
    if terms_url is not None and not _is_web_url(terms_url):
        fields["termsUrl"] = "Should be a web address starting with https://"
    if fields:
        raise HTTPException(422, {"message": "Please check the highlighted fields.", "fields": fields})


def _config(extra: dict | None, terms_url: str) -> dict:
    # The collector only fetches sources whose terms were reviewed (REQ-20): it fails
    # closed unless terms_status is "allowed" and terms_url is set.
    config = {"min_interval_seconds": DEFAULT_MIN_INTERVAL_SECONDS, **(extra or {})}
    config.update(terms_status="allowed", terms_url=terms_url)
    return config


def _url_taken() -> HTTPException:
    return HTTPException(409, {"message": "A source with this URL already exists.", "fields": {"url": "Already registered."}})


def _my_source(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Source not found.")
    return source


@router.get("/sources", response_model=list[AdminSourceView])
def list_sources(db: Session = Depends(get_db)):
    """Every source, active or not."""
    counts = dict(db.execute(select(NewsItem.source_id, func.count()).group_by(NewsItem.source_id)).all())
    return [_view(s, counts.get(s.source_id, 0)) for s in db.scalars(select(Source).order_by(Source.source_id))]


@router.post("/sources", response_model=AdminSourceView, status_code=201)
def add_source(req: AdminSourceRequest, db: Session = Depends(get_db)):
    url, terms_url = req.url.strip(), req.terms_url.strip()
    _check_urls(url, terms_url)
    if db.scalar(select(Source.source_id).where(Source.url == url)):
        raise _url_taken()
    source = Source(
        name=req.name.strip(),
        source_type=req.source_type,
        url=url,
        base_weight=req.base_weight,
        is_active=req.is_active,
        config=_config(req.config, terms_url),
    )
    db.add(source)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _url_taken() from None
    return _view(source, 0)


@router.patch("/sources/{source_id}", response_model=AdminSourceView)
def update_source(source_id: int, req: AdminSourceUpdate, db: Session = Depends(get_db)):
    source = _my_source(db, source_id)
    changes = req.model_dump(exclude_unset=True)
    url = changes["url"].strip() if changes.get("url") else None
    terms_url = changes["terms_url"].strip() if changes.get("terms_url") else None
    _check_urls(url, terms_url)

    if changes.get("is_active") and source.config.get("retired"):
        raise HTTPException(409, "This source has been retired. Use its replacement instead.")
    if url and url != source.url:
        if db.scalar(select(Source.source_id).where(Source.url == url, Source.source_id != source_id)):
            raise _url_taken()
        # The saved validators belong to the old address.
        source.url, source.etag, source.last_modified = url, None, None
    if changes.get("name"):
        source.name = changes["name"].strip()
    if changes.get("source_type"):
        source.source_type = changes["source_type"]
    if changes.get("base_weight") is not None:
        source.base_weight = changes["base_weight"]
    if changes.get("is_active") is not None:
        source.is_active = changes["is_active"]
    if "config" in changes or terms_url:
        base = changes["config"] if changes.get("config") is not None else source.config
        terms = terms_url or source.config.get("terms_url")
        # Reassigned, not mutated in place, so SQLAlchemy sees the JSON column change.
        source.config = _config(base, terms) if terms else dict(base)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _url_taken() from None
    return _view(source, _item_count(db, source_id))


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = _my_source(db, source_id)
    # Collected news keeps pointing at its source (and at subscribers' history), so
    # a source with items can only be switched off.
    if _item_count(db, source_id):
        raise HTTPException(409, "This source has collected news, so it cannot be removed. Switch it off instead.")
    db.delete(source)
    db.commit()


@router.get("/pipeline", response_model=PipelineStatusView)
def pipeline_status(db: Session = Depends(get_db)):
    """Queue sizes and the latest cycle runs, as the worker recorded them."""

    def count(table, *where) -> int:
        return db.scalar(select(func.count()).select_from(table).where(*where)) or 0

    levels = dict(db.execute(
        select(NewsItem.importance_level, func.count()).where(NewsItem.importance_level.is_not(None)).group_by(NewsItem.importance_level)
    ).all())
    statuses = dict(db.execute(select(Delivery.status, func.count()).group_by(Delivery.status)).all())
    counts = PipelineCounts(
        sources=count(Source),
        active_sources=count(Source, Source.is_active),
        news_items=count(NewsItem),
        unclassified=count(NewsItem, NewsItem.classified_at.is_(None)),
        undispatched=count(NewsItem, NewsItem.classified_at.is_not(None), NewsItem.dispatched_at.is_(None)),
        duplicates=count(NewsItem, NewsItem.duplicate_of.is_not(None)),
        high=levels.get(ImportanceLevel.high, 0),
        medium=levels.get(ImportanceLevel.medium, 0),
        low=levels.get(ImportanceLevel.low, 0),
        deliveries_queued=statuses.get(DeliveryStatus.queued, 0),
        deliveries_sent=statuses.get(DeliveryStatus.sent, 0),
        deliveries_failed=statuses.get(DeliveryStatus.failed, 0),
        deliveries_permanent_failure=statuses.get(DeliveryStatus.permanent_failure, 0),
        subscribers=count(User, User.role == UserRole.subscriber),
        verified_channels=count(ChannelConnection, ChannelConnection.is_verified),
    )
    runs = db.scalars(select(CycleRun).order_by(CycleRun.started_at.desc(), CycleRun.run_id.desc()).limit(RECENT_RUNS))
    return PipelineStatusView(counts=counts, runs=[CycleRunView.model_validate(r) for r in runs])
