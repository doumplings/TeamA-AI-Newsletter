"""One atomic transaction per source; durable cycle reporting."""
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select, text

from models import (CycleRunRepository, CycleType, NewsItem, NewsItemRepository,
                    Source, SourceRepository)
from .content import canonicalize, feed_items, html_items, json_items
from .http import Client


def collection_window(source, started):
    """Half-open publication window; retain a failed source's previous cutoff."""
    until = started
    until = until.replace(microsecond=0)
    since = source.last_success_at or until - timedelta(seconds=900)
    return since, until


def fetch(source, client, started, stats=None):
    """Search AI terms independently; do not assume Boolean query support."""
    terms = source.config.get('search_terms') if source.config.get('adapter') == 'bluesky' else None
    if not terms:
        return _fetch_single(source, client, started, stats)
    stats = stats if stats is not None else {}
    stats.update(returned_by_source=0, filtered_by_adapter=0, outside_window=0,
                 undated_items=0, eligible_items=0, duplicate_search_hits=0, searches=[])
    items, seen = [], set()
    etag, modified = source.etag, source.last_modified
    for term in terms:
        config = {**source.config, 'params': {**source.config.get('params', {}), 'q': term}}
        config.pop('search_terms', None)
        target = SimpleNamespace(config=config, source_type=source.source_type, url=source.url,
            etag=source.etag, last_modified=source.last_modified, last_success_at=source.last_success_at)
        counts = {}
        found, etag, modified = _fetch_single(target, client, started, counts)
        stats['searches'].append({'query': term, **counts})
        for key in ('returned_by_source', 'filtered_by_adapter', 'outside_window', 'undated_items'):
            stats[key] += counts[key]
        for item in found:
            key = canonicalize(item.url)
            if key in seen:
                stats['duplicate_search_hits'] += 1
                continue
            seen.add(key)
            items.append(item)
    stats['eligible_items'] = len(items)
    return items, etag, modified


def _fetch_single(source, client, started, stats=None):
    stats = stats if stats is not None else {}
    stats.update(returned_by_source=0, filtered_by_adapter=0, outside_window=0, undated_items=0, eligible_items=0)
    config = source.config
    kind = source.source_type.value
    url = source.url
    # Explicit official endpoints override an HTML source; never fall back on
    # access errors or a broken official feed.
    for preferred in ("api", "rss"):
        if config.get(preferred + "_url"):
            kind, url = preferred, config[preferred + "_url"]
            break
    headers = dict(config.get("headers", {}))
    if config.get("bearer_token_env"):
        token = os.environ.get(config["bearer_token_env"])
        if not token:
            raise ValueError("Missing configured API token environment variable")
        headers["Authorization"] = "Bearer " + token
    # Re-read the feed: an unchanged response may contain an item previously
    # outside the publication window. A 304 would hide that item this cycle.
    params = dict(config.get("params", {}))
    since, until = collection_window(source, started)
    if since and config.get("since_param"):
        params[config["since_param"]] = since.isoformat().replace("+00:00", "Z")
    if config.get("adapter") == "bluesky":
        params["until"] = until.isoformat().replace("+00:00", "Z")
    if config.get("adapter") == "nyt":
        # UTC calendar bounds narrow API results; exact window is enforced below.
        params.update(begin_date=since.strftime("%Y%m%d"), end_date=until.strftime("%Y%m%d"), page=0)
    items = []
    nyt_pages = set()
    etag, modified = source.etag, source.last_modified
    for page in range(int(config.get("max_pages", 20))):
        response = client.get(url, config, headers=headers, params=params)
        if response.status_code == 304:
            return [], etag, modified
        if page == 0:
            etag, modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
        if kind == "rss":
            raw = feed_items(response.content)
        elif kind == "html":
            content = client.render(url, config) if config.get("render_js") else response.text
            raw = html_items(content, config)
        elif kind == "api":
            data = response.json()
            if config.get("adapter") == "nyt":
                if data.get("status") != "OK":
                    raise ValueError("NYT API returned an unsuccessful response")
                try:
                    docs = data["response"]["docs"]
                    # Some responses omit meta or encode counts as strings.
                    # Without a total, request pages until the API returns none.
                    meta = data["response"].get("meta") or {}
                    hits = meta.get("hits")
                    if isinstance(hits, str) and hits.isdecimal():
                        hits = int(hits)
                    if hits is not None and (type(hits) is not int or hits < 0):
                        raise ValueError()
                    # NYT can return status OK with docs:null and no metadata
                    # for an empty search. A positive hit count still fails closed.
                    if docs is None and (hits is None or hits == 0):
                        docs = []
                        data["response"]["docs"] = docs
                    if not isinstance(docs, list):
                        raise ValueError()
                    offset = page * 10
                except (KeyError, TypeError, ValueError, AttributeError):
                    payload = data.get("response")
                    def field_type(container, key):
                        if not isinstance(container, dict):
                            return "parent-" + type(container).__name__
                        return type(container[key]).__name__ if key in container else "missing"
                    metadata = payload.get("meta") if isinstance(payload, dict) else None
                    # Only fixed field names and type names: never response values,
                    # request URLs, or arbitrary server text containing credentials.
                    shape = (f"response={type(payload).__name__}, "
                             f"docs={field_type(payload, 'docs')}, meta={field_type(payload, 'meta')}, "
                             f"hits={field_type(metadata, 'hits')}, offset={field_type(metadata, 'offset')}")
                    raise ValueError("NYT response shape: " + shape) from None
                if not docs and hits is not None and offset < hits:
                    raise ValueError("NYT returned an empty page before all results; checkpoint retained")
                if docs:
                    signature = json.dumps(docs, sort_keys=True)
                    if signature in nyt_pages:
                        raise ValueError("NYT repeated a result page; checkpoint retained")
                    nyt_pages.add(signature)
            raw = json_items(data, config)
        else:
            raise ValueError("Unsupported source type")
        raw = list(raw)
        returned = (len(data['posts']) if kind == 'api' and config.get('adapter') == 'bluesky'
                    else len(docs) if kind == 'api' and config.get('adapter') == 'nyt' else len(raw))
        stats['returned_by_source'] += returned
        stats['filtered_by_adapter'] += returned - len(raw)
        # A malformed item fails the source rather than silently losing it and
        # advancing the checkpoint. All inserted rows roll back together.
        for item in raw:
            item.normalized(url)
            if item.published_at is not None and since <= item.published_at < until:
                items.append(item)
                stats['eligible_items'] += 1
            elif item.published_at is None:
                stats['undated_items'] += 1
            else:
                stats['outside_window'] += 1
        if kind != "api":
            break
        if config.get("adapter") == "nyt":
            if not docs or (hits is not None and offset + len(docs) >= hits):
                break
            if page + 1 >= min(100, int(config.get("max_pages", 20))):
                raise ValueError("NYT pagination limit reached; checkpoint retained")
            params["page"] = page + 1
            continue
        from .content import path
        next_path = config.get("next_token_path")
        try:
            token = path(data, next_path) if next_path else None
        except KeyError:
            token = None
        if not token:
            break
        if page + 1 == int(config.get("max_pages", 20)):
            raise ValueError("Pagination limit reached; checkpoint retained")
        params[config.get("page_token_param", "next_token")] = token
        headers.pop("If-None-Match", None)
        headers.pop("If-Modified-Since", None)
    else:
        raise ValueError("max_pages must be positive")
    return items, etag, modified


def run_cycle(factory, client=None, source_id=None):
    own_client = client is None
    client = client or Client()
    added = failures = duplicates = 0
    details = []
    results = []
    cycle_started = datetime.now(timezone.utc).replace(microsecond=0)
    # A session-level advisory lock prevents overlapping cron/worker runs.
    # Keep its connection checked out so the lock cannot leak into the pool.
    with factory() as lock_db:
        connection = lock_db.connection()
        if connection.dialect.name != "postgresql":
            raise ValueError("Collector requires the canonical PostgreSQL schema.sql database")
        locked = connection.scalar(text("SELECT pg_try_advisory_lock(4412026)"))
        if not locked:
            if own_client:
                client.close()
            return {"skipped": "another scrape cycle is running"}
        try:
            with factory.begin() as db:
                run_id = CycleRunRepository(db).start(CycleType.scrape)
                source_ids = [s.source_id for s in SourceRepository(db).active()
                              if source_id is None or s.source_id == source_id]
            try:
                for source_id in source_ids:
                    started = cycle_started
                    count = skipped = 0
                    try:
                        with factory.begin() as db:
                            source = db.get(Source, source_id)
                            if not source or not source.is_active:
                                continue
                            window_start, window_end = collection_window(source, started)
                            stats = {}
                            items, etag, modified = fetch(source, client, started, stats=stats)
                            repository = NewsItemRepository(db)
                            for item in items:
                                canonical = canonicalize(item.url)
                                # Exact normalized title + summary/body detects
                                # reposts at different URLs without fuzzy merging.
                                content = item.body or item.summary
                                same = None
                                if content:
                                    same = db.scalar(select(NewsItem.item_id).where(
                                        NewsItem.title == item.title,
                                        (NewsItem.body == content) | (NewsItem.summary == content),
                                    ).limit(1))
                                if same is not None:
                                    skipped += 1
                                    continue
                                inserted = repository.insert_if_new(source_id, item.title, item.url,
                                    canonical, item.summary, item.body, item.published_at)
                                if inserted is None:
                                    skipped += 1
                                else:
                                    count += 1
                            SourceRepository(db).record_success(source_id, etag, modified)
                            source.last_success_at = window_end
                        added += count
                        duplicates += skipped
                        results.append({"source_id": source_id, "name": source.name, "items_added": count, "duplicates": skipped, "ok": True,
                                        "window_start": window_start.isoformat(), "window_end": window_end.isoformat(), "diagnostics": stats})
                    except Exception as exc:
                        failures += 1
                        # Avoid HTTP exception strings which may expose query credentials.
                        error = type(exc).__name__
                        if isinstance(exc, (ValueError, RuntimeError)):
                            error += ": " + str(exc)[:300]
                        with factory.begin() as db:
                            SourceRepository(db).record_failure(source_id, error)
                        details.append({"source_id": source_id, "error": error})
                        results.append({"source_id": source_id, "ok": False, "error": error})
            finally:
                with factory.begin() as db:
                    CycleRunRepository(db).finish(run_id, added, failures,
                        json.dumps({"duplicates": duplicates, "errors": details}))
            return {"run_id": run_id, "items_added": added, "duplicates": duplicates, "failures": failures, "sources": results}
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(4412026)"))
            if own_client:
                client.close()
