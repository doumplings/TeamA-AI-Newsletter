"""SourceAdminController (UC-9) and the pipeline status view. UT-25 and the admin part of IT-07."""
from sqlalchemy import update

from app.db import SessionLocal
from app.models import CycleRun, CycleType, NewsItem, Source, User, UserRole
from collector.sources import default_sources

NEW = {"name": "Example Lab", "sourceType": "rss", "url": "https://lab.example.com/feed.xml",
       "baseWeight": 20, "isActive": True, "termsUrl": "https://lab.example.com/terms"}


def _admin(signed_in):
    with SessionLocal() as db:
        db.execute(update(User).values(role=UserRole.admin))
        db.commit()
    return signed_in


def test_ut25_a_subscriber_cannot_manage_sources(signed_in, client):
    for call in (signed_in.get("/admin/sources"), signed_in.post("/admin/sources", json=NEW),
                 signed_in.patch("/admin/sources/1", json={"isActive": False}),
                 signed_in.delete("/admin/sources/1"), signed_in.get("/admin/pipeline")):
        assert call.status_code == 403
    client.post("/auth/logout")
    assert client.get("/admin/sources").status_code == 401


def test_admin_lists_every_source_active_or_not(signed_in):
    admin = _admin(signed_in)
    with SessionLocal() as db:
        db.execute(update(Source).where(Source.source_id == 1).values(is_active=False))
        db.commit()
    rows = admin.get("/admin/sources").json()
    assert len(rows) == len(default_sources()) and rows[0]["isActive"] is False
    assert rows[0]["termsUrl"] and rows[0]["itemCount"] == 0
    # ...while subscribers only see the active ones
    assert len(admin.get("/sources").json()) == len(default_sources()) - 1


def test_admin_adds_edits_switches_off_and_removes_a_source(signed_in):
    admin = _admin(signed_in)
    made = admin.post("/admin/sources", json={**NEW, "config": {"min_interval_seconds": 10}})
    assert made.status_code == 201
    source = made.json()
    # The collector fails closed without reviewed terms, so they are written into the config.
    assert source["config"] == {"min_interval_seconds": 10, "terms_status": "allowed", "terms_url": NEW["termsUrl"]}
    assert source["termsUrl"] == NEW["termsUrl"] and source["baseWeight"] == 20

    sid = source["sourceId"]
    off = admin.patch(f"/admin/sources/{sid}", json={"isActive": False, "baseWeight": 30, "name": "Example Lab News"}).json()
    assert (off["isActive"], off["baseWeight"], off["name"]) == (False, 30, "Example Lab News")
    assert off["config"] == source["config"]                       # untouched fields stay as they were
    moved = admin.patch(f"/admin/sources/{sid}", json={"url": "https://lab.example.com/rss", "termsUrl": "https://lab.example.com/tos"}).json()
    assert moved["url"].endswith("/rss") and moved["config"]["terms_url"].endswith("/tos")

    assert admin.delete(f"/admin/sources/{sid}").status_code == 204
    assert admin.patch(f"/admin/sources/{sid}", json={"isActive": True}).status_code == 404


def test_bad_source_details_are_refused(signed_in):
    admin = _admin(signed_in)
    assert admin.post("/admin/sources", json=NEW).status_code == 201
    dup = admin.post("/admin/sources", json=NEW)
    assert dup.status_code == 409 and "url" in dup.json()["detail"]["fields"]
    bad = admin.post("/admin/sources", json={**NEW, "url": "ftp://lab.example.com/feed", "termsUrl": "not a link"})
    assert bad.status_code == 422 and set(bad.json()["detail"]["fields"]) == {"url", "termsUrl"}
    assert admin.post("/admin/sources", json={**NEW, "url": "https://x.example/f", "baseWeight": 31}).status_code == 422
    assert admin.post("/admin/sources", json={k: v for k, v in NEW.items() if k != "termsUrl"}).status_code == 422
    assert admin.patch("/admin/sources/1", json={"url": NEW["url"]}).status_code == 409


def test_a_source_with_collected_news_can_only_be_switched_off(signed_in):
    admin = _admin(signed_in)
    with SessionLocal() as db:
        db.add(NewsItem(source_id=1, title="Story", url="https://x.example/a", canonical_url="https://x.example/a"))
        db.commit()
    r = admin.delete("/admin/sources/1")
    assert r.status_code == 409 and "Switch it off" in r.json()["detail"]
    assert admin.patch("/admin/sources/1", json={"isActive": False}).json()["itemCount"] == 1


def test_pipeline_status_counts_rows_and_lists_recent_cycles(signed_in):
    admin = _admin(signed_in)
    with SessionLocal() as db:
        db.add(NewsItem(source_id=1, title="Waiting", url="https://x.example/a", canonical_url="https://x.example/a"))
        db.add(CycleRun(cycle_type=CycleType.scrape, items_processed=1, failures=0, notes='{"duplicates": 0}'))
        db.commit()
        db.add(CycleRun(cycle_type=CycleType.classify))
        db.commit()
    status = admin.get("/admin/pipeline").json()
    counts = status["counts"]
    assert counts["sources"] == counts["activeSources"] == len(default_sources())
    assert (counts["newsItems"], counts["unclassified"], counts["undispatched"]) == (1, 1, 0)
    assert counts["subscribers"] == 0 and counts["verifiedChannels"] == 0   # the only account is the admin
    assert [r["cycleType"] for r in status["runs"]] == ["classify", "scrape"]   # newest first
    assert status["runs"][1]["itemsProcessed"] == 1 and status["runs"][0]["finishedAt"] is None
