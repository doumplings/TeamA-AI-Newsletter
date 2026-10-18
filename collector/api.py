"""Local testing API for the canonical PostgreSQL collector database."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from models import NewsItem, Source, SourceType, make_engine, make_session_factory
from .service import run_cycle, fetch
from .http import Client
from .sources import FEED_URL, seed_source
from .config import load_settings



class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_id: int
    name: str
    source_type: str
    url: str
    is_active: bool
    last_checked_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    last_error: str | None


class ItemView(BaseModel):
    item_id: int
    source_id: int
    source_name: str
    title: str
    url: str
    canonical_url: str
    summary: str | None
    body: str | None
    published_at: datetime | None
    collected_at: datetime


class ItemsPage(BaseModel):
    items: list[ItemView]
    total: int
    limit: int
    offset: int



class SourceUpdate(BaseModel):
    is_active: bool


def create_app(factory=None):
    @asynccontextmanager
    async def lifespan(app):
        load_settings()
        engine = None
        if factory is None:
            url = os.environ.get("COLLECTOR_DATABASE_URL")
            if not url:
                raise RuntimeError("Set COLLECTOR_DATABASE_URL to the collector PostgreSQL database; see docs/POSTMAN.md")
            engine = make_engine(url)
            if engine.dialect.name != "postgresql":
                engine.dispose()
                raise RuntimeError("COLLECTOR_DATABASE_URL must use PostgreSQL and schema.sql")
        try:
            app.state.factory = factory if factory is not None else make_session_factory(engine)
            seed_source(app.state.factory)
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="AI News Collector Testing API", lifespan=lifespan)

    @app.get("/health")
    def health():
        try:
            with app.state.factory() as db:
                db.execute(text("SELECT 1"))
            return {"ok": True, "database": "postgresql"}
        except SQLAlchemyError:
            raise HTTPException(503, "Collector database unavailable") from None

    @app.get("/collector/sources", response_model=list[SourceView])
    def sources():
        with app.state.factory() as db:
            return [SourceView.model_validate(s) for s in db.scalars(select(Source).order_by(Source.source_id))]

    @app.patch("/collector/sources/{source_id}", response_model=SourceView)
    def update_source(source_id: int, request: SourceUpdate):
        with app.state.factory.begin() as db:
            source = db.get(Source, source_id)
            if source is None:
                raise HTTPException(404, "Source not found")
            if request.is_active and source.config.get('retired'):
                raise HTTPException(409, "Source has been retired; use the replacement source")
            source.is_active = request.is_active
            db.flush()
            return SourceView.model_validate(source)

    @app.post("/collector/run")
    def collect(source_id: int | None = Query(None, ge=1)):
        if source_id is not None:
            with app.state.factory() as db:
                source = db.get(Source, source_id)
                if source is None:
                    raise HTTPException(404, "Source not found")
                if not source.is_active:
                    raise HTTPException(409, "Source is disabled; enable it before collecting")
        # Synchronous route runs in FastAPI's thread pool. The collector's
        # PostgreSQL advisory lock prevents concurrent runs across processes.
        try:
            return run_cycle(app.state.factory) if source_id is None else run_cycle(app.state.factory, source_id=source_id)
        except SQLAlchemyError:
            raise HTTPException(503, "Collector database unavailable or schema not initialized") from None

    @app.get("/collector/preview")
    def preview(source_id: int = Query(..., ge=1),
                lookback_hours: int = Query(24, ge=1, le=168),
                limit: int = Query(20, ge=1, le=100)):
        with app.state.factory() as db:
            source = db.get(Source, source_id)
            if source is None:
                raise HTTPException(404, "Source not found")
            if not source.is_active:
                raise HTTPException(409, "Source is disabled")
            until = datetime.now(timezone.utc).replace(microsecond=0)
            since = until - timedelta(hours=lookback_hours)
            # Copy fetch settings: never change the mapped source's checkpoint.
            target = SimpleNamespace(config=dict(source.config), source_type=source.source_type,
                url=source.url, etag=None, last_modified=None, last_success_at=since)
            name = source.name
        client = Client()
        stats = {}
        try:
            articles, _, _ = fetch(target, client, until, stats=stats)
        except Exception as exc:
            # Only expose messages generated by our own policy/API code.
            detail = str(exc)[:300] if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            raise HTTPException(502, detail) from None
        finally:
            client.close()
        return {"source_id": source_id, "source_name": name, "preview_only": True,
                "window_start": since, "window_end": until, "diagnostics": stats,
                "total": len(articles), "items": [asdict(item) for item in articles[:limit]]}

    @app.get("/collector/items", response_model=ItemsPage)
    def items(source_id: int | None = Query(None, ge=1),
              limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        with app.state.factory() as db:
            query = select(NewsItem, Source.name).join(Source)
            count = select(func.count()).select_from(NewsItem)
            if source_id is not None:
                if db.get(Source, source_id) is None:
                    raise HTTPException(404, "Source not found")
                query = query.where(NewsItem.source_id == source_id)
                count = count.where(NewsItem.source_id == source_id)
            rows = db.execute(query.order_by(NewsItem.collected_at.desc(), NewsItem.item_id.desc())
                              .offset(offset).limit(limit))
            return ItemsPage(items=[ItemView(
                **{key: getattr(item, key) for key in ItemView.model_fields if key != "source_name"},
                source_name=name) for item, name in rows],
                total=db.scalar(count), limit=limit, offset=offset)

    return app


app = create_app()
