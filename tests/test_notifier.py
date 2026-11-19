"""Dispatcher and RetryHandler (UC-13, UC-14, UC-15). UT-15 to UT-18 and IT-05/IT-06 from Report 2."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app.adapters import ChannelAdapter, SendResult
from models import (ChannelConnection, ChannelType, Delivery, DeliveryStatus, FollowedSource,
                    ImportanceLevel, NewsItem)
from notifier import Dispatcher, RetryHandler

MINUTE = timedelta(minutes=1)
SLACK = timedelta(seconds=5)  # retry times are set by the database clock, the test reads its own


class FakeChannel(ChannelAdapter):
    """Stands in for Telegram, Discord and email: records messages, replies as scripted."""

    def __init__(self):
        self.sent = []       # (contact, Message)
        self.replies = {}    # contact -> list of SendResult, used in order; default is OK

    def send(self, contact, message):
        queue = self.replies.get(contact)
        result = queue.pop(0) if queue else SendResult(True)
        if result.ok:
            self.sent.append((contact, message))
        return result


def dispatcher(factory, fake, **options):
    return Dispatcher(factory, adapter_for=lambda _type: fake, decrypt=lambda data: bytes(data).decode(), **options)


def classified(make, source_id, title, level=ImportanceLevel.high, **extra):
    score = {ImportanceLevel.high: 80, ImportanceLevel.medium: 50, ImportanceLevel.low: 20}[level]
    return make.item(source_id, title, importance_score=Decimal(score), importance_level=level,
                     classified_at=datetime.now(timezone.utc), **extra)


def deliveries(factory):
    with factory() as db:
        return list(db.scalars(select(Delivery).order_by(Delivery.delivery_id)))


def contact_of(factory, channel_id):
    with factory() as db:
        return bytes(db.get(ChannelConnection, channel_id).contact_encrypted).decode()


def make_due(factory):
    """Move every retry time into the past, as if the wait had gone by."""
    with factory.begin() as db:
        db.execute(update(Delivery).values(next_attempt_at=datetime.now(timezone.utc) - MINUTE))


# ---------- RetryHandler ----------
def test_ut15_wait_doubles_and_a_longer_wait_asked_by_the_channel_wins():
    retry = RetryHandler()
    assert [retry.next_wait(n) for n in (1, 2, 3, 4)] == [1 * MINUTE, 2 * MINUTE, 4 * MINUTE, 8 * MINUTE]
    assert retry.next_wait(1, retry_after=600) == 10 * MINUTE
    assert retry.next_wait(4, retry_after=30) == 8 * MINUTE


def test_ut16_fifth_failed_try_and_a_permanent_error_both_give_up(factory, make):
    source = make.source()
    user = make.subscriber()
    flaky, gone = make.channel(user), make.channel(user, ChannelType.email)
    classified(make, source, "Acme launches Nova")
    fake = FakeChannel()
    fake.replies = {contact_of(factory, flaky): [SendResult(False, False, "HTTP 500")] * 5,
                    contact_of(factory, gone): [SendResult(False, True, "webhook removed")]}
    d = dispatcher(factory, fake)
    d.dispatch_pending()

    for expected_attempts in range(1, 6):
        d.send_due()
        rows = {r.channel_id: r for r in deliveries(factory)}
        assert rows[flaky].attempts == expected_attempts
        make_due(factory)

    rows = {r.channel_id: r for r in deliveries(factory)}
    assert rows[flaky].status == DeliveryStatus.permanent_failure and rows[flaky].last_error == "HTTP 500"
    # The permanent error gave up on the first try and was never retried.
    assert rows[gone].status == DeliveryStatus.permanent_failure and rows[gone].attempts == 1
    assert fake.sent == []


def test_it06_retry_times_follow_the_table_and_nothing_is_sent_twice(factory, make):
    source, user = make.source(), make.subscriber()
    channel = make.channel(user)
    classified(make, source, "Acme launches Nova")
    fake = FakeChannel()
    fake.replies = {contact_of(factory, channel): [SendResult(False, False, "Rate limited", retry_after=600), SendResult(False, False, "HTTP 500")]}
    d = dispatcher(factory, fake)
    d.dispatch_pending()

    assert d.send_due()["failed_will_retry"] == 1
    row = deliveries(factory)[0]
    wait = row.next_attempt_at - datetime.now(timezone.utc)
    assert 9 * MINUTE < wait <= 10 * MINUTE + SLACK   # the channel asked for 10 minutes
    assert d.send_due() == {"sent": 0, "failed_will_retry": 0, "permanent_failures": 0, "cancelled": 0}  # not due yet

    make_due(factory)
    d.send_due()                                       # second try fails: wait 2 minutes
    row = deliveries(factory)[0]
    assert row.attempts == 2 and MINUTE < row.next_attempt_at - datetime.now(timezone.utc) <= 2 * MINUTE + SLACK

    make_due(factory)
    assert d.send_due()["sent"] == 1                   # third try goes through
    make_due(factory)
    assert d.send_due()["sent"] == 0 and len(fake.sent) == 1
    row = deliveries(factory)[0]
    assert row.status == DeliveryStatus.sent and row.attempts == 3 and row.sent_at is not None


# ---------- Dispatcher ----------
def test_ut17_one_delivery_per_matching_channel_and_a_second_run_adds_none(factory, make):
    source = make.source()
    user = make.subscriber()
    for channel_type in ChannelType:
        make.channel(user, channel_type)
    item = classified(make, source, "Acme launches Nova")
    d = dispatcher(factory, FakeChannel())

    assert d.dispatch_pending() == {"items_dispatched": 1, "deliveries_queued": 3, "stale_items_skipped": 0}
    with factory() as db:
        assert db.get(NewsItem, item).dispatched_at is not None
    assert d.dispatch_pending()["items_dispatched"] == 0
    assert [r.status for r in deliveries(factory)] == [DeliveryStatus.queued] * 3


def test_it02_only_channels_the_three_rules_allow_receive_the_story(factory, make):
    followed, other = make.source("Followed"), make.source("Other")
    everything = make.subscriber(ImportanceLevel.low)
    high_only = make.subscriber(ImportanceLevel.high)
    picky = make.subscriber(ImportanceLevel.low, follows_all=False)
    with factory.begin() as db:
        db.add(FollowedSource(user_id=picky, source_id=followed))
    wanted = {
        "everything": make.channel(everything),
        "own_level": make.channel(high_only, ChannelType.email, min_importance=ImportanceLevel.medium),
        "picky": make.channel(picky),
    }
    make.channel(high_only)                                   # default High: a Medium story is below it
    make.channel(everything, ChannelType.email, verified=False)
    make.channel(everything, ChannelType.telegram, enabled=False)
    medium = classified(make, followed, "Acme changes pricing", ImportanceLevel.medium)
    elsewhere = classified(make, other, "Beta changes pricing", ImportanceLevel.medium)
    repeat = classified(make, other, "Acme changes its pricing", ImportanceLevel.medium, duplicate_of=medium)

    dispatcher(factory, FakeChannel()).dispatch_pending()
    rows = deliveries(factory)
    assert {r.channel_id for r in rows if r.item_id == medium} == set(wanted.values())
    assert {r.channel_id for r in rows if r.item_id == elsewhere} == {wanted["everything"], wanted["own_level"]}
    assert not [r for r in rows if r.item_id == repeat]       # a repeat is never delivered
    with factory() as db:
        assert db.get(NewsItem, repeat).dispatched_at is not None


def test_ut18_ok_is_marked_sent_and_an_error_goes_to_the_retry_handler(factory, make):
    source = make.source("Acme Blog")
    user = make.subscriber()
    good, bad = make.channel(user), make.channel(user, ChannelType.email)
    classified(make, source, "Acme launches Nova", summary="A new   model for everyone.")
    fake = FakeChannel()
    fake.replies = {contact_of(factory, bad): [SendResult(False, False, "HTTP 503")]}

    summary = dispatcher(factory, fake).run_cycle()
    assert (summary["deliveries_queued"], summary["sent"], summary["failed_will_retry"], summary["failures"]) == (2, 1, 1, 1)
    rows = {r.channel_id: r for r in deliveries(factory)}
    assert rows[good].status == DeliveryStatus.sent and rows[good].attempts == 1
    assert rows[bad].status == DeliveryStatus.failed and rows[bad].last_error == "HTTP 503"

    # IT-05: the message carries source, headline, level, summary and link.
    _, message = fake.sent[0]
    assert message.subject == "Acme launches Nova" and message.link.startswith("https://news.example/")
    assert "High importance" in message.text and "Acme Blog" in message.text and "A new model for everyone." in message.text


def test_backlog_items_are_marked_dispatched_without_notifying_anyone(factory, make):
    source, user = make.source(), make.subscriber()
    make.channel(user)
    old = classified(make, source, "Acme launched Nova last week", collected_at=datetime.now(timezone.utc) - timedelta(days=3))
    fake = FakeChannel()
    summary = dispatcher(factory, fake).run_cycle()
    assert summary["stale_items_skipped"] == 1 and summary["deliveries_queued"] == 0 and fake.sent == []
    with factory() as db:
        assert db.get(NewsItem, old).dispatched_at is not None


def test_a_disabled_channel_cancels_its_queued_deliveries(factory, make):
    source, user = make.source(), make.subscriber()
    channel = make.channel(user)
    classified(make, source, "Acme launches Nova")
    fake = FakeChannel()
    d = dispatcher(factory, fake)
    d.dispatch_pending()
    with factory.begin() as db:
        db.execute(update(ChannelConnection).values(is_enabled=False))
    assert d.send_due()["cancelled"] == 1 and fake.sent == []
    assert deliveries(factory)[0].status == DeliveryStatus.permanent_failure


def test_st11_two_dispatchers_at_once_send_each_delivery_exactly_once(factory, make):
    from concurrent.futures import ThreadPoolExecutor
    source = make.source()
    for _ in range(12):
        make.channel(make.subscriber())
    classified(make, source, "Acme launches Nova")
    fake = FakeChannel()
    first, second = dispatcher(factory, fake), dispatcher(factory, fake)
    first.dispatch_pending()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda d: d.send_due(), (first, second)))
    assert sum(r["sent"] for r in results) == 12 == len(fake.sent)
    assert len({contact for contact, _ in fake.sent}) == 12
