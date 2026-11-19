"""The stages joined through the database, as they run (IT-03 to IT-05 in Report 2):
collect two feeds -> link the repeated story -> score -> queue and send."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace

from sqlalchemy import select

from classifier import ImportanceClassifier, seed_rules
from collector.service import run_cycle
from models import CycleRun, CycleType, Delivery, DeliveryStatus, ImportanceLevel, NewsItem, Source
from notifier import Dispatcher
from test_notifier import FakeChannel


def feed(*entries):
    """An RSS document; each entry is (title, link, minutes ago)."""
    now = datetime.now(timezone.utc)
    items = "".join(
        f"<item><title>{title}</title><link>{link}</link><description>{title}.</description>"
        f"<pubDate>{format_datetime(now - timedelta(minutes=ago))}</pubDate></item>"
        for title, link, ago in entries)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'.encode()


class FakeWeb:
    """Serves saved feeds instead of the internet; records what was requested."""

    def __init__(self, pages):
        self.pages, self.requested = pages, []

    def get(self, url, config, headers=None, params=None):
        self.requested.append(url)
        return SimpleNamespace(status_code=200, headers={}, content=self.pages[url])

    def close(self):
        pass


def test_collected_stories_are_linked_scored_and_delivered_once(factory, make):
    seed_rules(factory)
    official = make.source("Acme Blog", weight=30)
    news_site = make.source("Tech Daily", weight=20)
    with factory() as db:
        urls = dict(db.execute(select(Source.source_id, Source.url)).all())
    web = FakeWeb({
        urls[official]: feed(("Acme releases Nova, its most capable model", "https://acme.example/nova?utm_source=rss", 10),
                             ("Join us at the Acme developer meetup", "https://acme.example/meetup", 8),
                             ("Old post", "https://acme.example/old", 60 * 24 * 30)),
        urls[news_site]: feed(("Acme launches Nova model", "https://techdaily.example/acme-nova", 5)),
    })
    reader = make.subscriber(ImportanceLevel.high)
    channel = make.channel(reader)

    # --- scrape (UC-10, UC-11) ---
    scrape = run_cycle(factory, client=web)
    assert (scrape["items_added"], scrape["linked_to_original"], scrape["failures"]) == (3, 1, 0)
    with factory() as db:
        items = {i.title: i for i in db.scalars(select(NewsItem))}
        original, repeat = items["Acme releases Nova, its most capable model"], items["Acme launches Nova model"]
        assert original.canonical_url == "https://acme.example/nova"          # tracking parameter removed
        assert repeat.duplicate_of == original.item_id and original.corroboration_count == 2
        assert "Old post" not in items                                         # outside the collection window

    # A second cycle finds nothing new: the same feeds add no rows.
    again = run_cycle(factory, client=web)
    assert again["items_added"] == 0

    # --- classify (UC-12) ---
    classify = ImportanceClassifier(factory).classify_pending()
    assert classify["items_classified"] == 3
    with factory() as db:
        scores = {i.title: (int(i.importance_score), i.importance_level) for i in db.scalars(select(NewsItem))}
    assert scores["Acme releases Nova, its most capable model"] == (75, ImportanceLevel.high)   # 30 + 40 + 5
    assert scores["Join us at the Acme developer meetup"] == (10, ImportanceLevel.low)          # 30 - 20

    # --- dispatch and send (UC-13, UC-14) ---
    fake = FakeChannel()
    dispatcher = Dispatcher(factory, adapter_for=lambda _type: fake, decrypt=lambda data: bytes(data).decode())
    summary = dispatcher.run_cycle()
    assert (summary["items_dispatched"], summary["deliveries_queued"], summary["sent"]) == (3, 1, 1)
    assert [m.subject for _, m in fake.sent] == ["Acme releases Nova, its most capable model"]
    assert dispatcher.run_cycle()["sent"] == 0 and len(fake.sent) == 1          # never twice

    with factory() as db:
        delivery = db.scalars(select(Delivery)).one()
        assert (delivery.channel_id, delivery.status, delivery.attempts) == (channel, DeliveryStatus.sent, 1)
        # Every cycle left a record (REQ-17).
        runs = [r.cycle_type for r in db.scalars(select(CycleRun).order_by(CycleRun.run_id))]
        assert runs == [CycleType.scrape, CycleType.scrape, CycleType.classify, CycleType.dispatch, CycleType.dispatch]
        assert all(r.finished_at is not None for r in db.scalars(select(CycleRun)))
