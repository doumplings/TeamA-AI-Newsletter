"""Queue deliveries for newly classified items, then send the ones that are due
(UC-13 and UC-14, Report 2 Sections 9.1.4 and 9.1.5).

``deliveries`` is the queue: it survives a crash, and the unique (item, channel)
rule means a story is never sent twice to the same channel.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update

from models import (CycleRunRepository, CycleType, DeliveryRepository, DeliveryStatus,
                    NewsItem, NewsItemRepository)
from .retry import RetryHandler

log = logging.getLogger("ainews.notifier")

BATCH_SIZE = 100   # most items queued, and most deliveries sent, per cycle
SEND_CHUNK = 10    # deliveries sent per transaction, so row locks are held briefly
# An item still waiting this long after collection is backlog (the worker was down,
# or the data predates the pipeline). It is marked dispatched without notifying anyone:
# day-old news arriving in a burst is the noise the customer asked not to get.
MAX_ITEM_AGE = timedelta(hours=24)


class Dispatcher:
    def __init__(self, factory, batch_size=BATCH_SIZE, retry=None, adapter_for=None, decrypt=None,
                 max_item_age=MAX_ITEM_AGE):
        self.factory = factory
        self.batch_size = batch_size
        self.retry = retry or RetryHandler()
        self.max_item_age = max_item_age
        if adapter_for is None or decrypt is None:
            # Imported here, not at module level: app.config needs SECRET_KEY in the environment.
            from app import adapters, security
            adapter_for = adapter_for or adapters.for_type
            decrypt = decrypt or security.decrypt_contact
        self.adapter_for = adapter_for
        self.decrypt = decrypt

    def dispatch_pending(self):
        """For each undispatched item, queue one Delivery per recipient channel (UC-13).

        Recipients are chosen by one SQL query (``DeliveryRepository.enqueue_for_item``):
        enabled and verified, level high enough, source followed. Queuing and marking the
        item dispatched happen in the same transaction.
        """
        dispatched = queued = stale = 0
        cutoff = datetime.now(timezone.utc) - self.max_item_age
        with self.factory.begin() as db:
            deliveries = DeliveryRepository(db)
            for item in NewsItemRepository(db).undispatched(self.batch_size):
                if item.collected_at < cutoff:
                    db.execute(update(NewsItem).where(NewsItem.item_id == item.item_id).values(dispatched_at=func.now()))
                    stale += 1
                else:
                    queued += deliveries.enqueue_for_item(item.item_id)
                dispatched += 1
        return {"items_dispatched": dispatched, "deliveries_queued": queued, "stale_items_skipped": stale}

    def send_due(self):
        """Send every due delivery through its channel's adapter (UC-14), oldest first.

        Rows are locked as they are read (FOR UPDATE SKIP LOCKED), so a second
        sender running at the same time skips them instead of sending them twice.
        """
        sent = failed = permanent = 0
        with self.factory.begin() as db:
            cancelled = DeliveryRepository(db).cancel_undeliverable()
        remaining = self.batch_size
        while remaining > 0:
            with self.factory.begin() as db:
                due = DeliveryRepository(db).due(min(SEND_CHUNK, remaining))
                for delivery in due:
                    status = self._send(db, delivery)
                    if status == DeliveryStatus.sent:
                        sent += 1
                    elif status == DeliveryStatus.permanent_failure:
                        permanent += 1
                    else:
                        failed += 1
            remaining -= len(due)
            if len(due) < SEND_CHUNK:
                break
        return {"sent": sent, "failed_will_retry": failed, "permanent_failures": permanent, "cancelled": cancelled}

    def _send(self, db, delivery):
        """Format and send one delivery; hand failures to the RetryHandler."""
        from app.adapters import SendResult
        channel, item = delivery.channel, delivery.item
        try:
            adapter = self.adapter_for(channel.channel_type)
            result = adapter.send(self.decrypt(channel.contact_encrypted), adapter.format_message(item, item.source.name))
        except Exception as exc:
            # Type only: exception text can carry a webhook URL or bot token.
            result = SendResult(False, False, f"Send error: {type(exc).__name__}")
        if result.ok:
            DeliveryRepository(db).mark_sent(delivery.delivery_id)
            return DeliveryStatus.sent
        return self.retry.record_failure(db, delivery, result)

    def run_cycle(self):
        """One dispatch cycle: queue, then send, and record the cycle summary."""
        with self.factory.begin() as db:
            run_id = CycleRunRepository(db).start(CycleType.dispatch)
        summary, errors = {}, []
        try:
            summary.update(self.dispatch_pending())
            summary.update(self.send_due())
        except Exception as exc:
            errors.append(type(exc).__name__)
            log.error("Dispatch cycle failed (%s); queued deliveries wait for the next cycle", type(exc).__name__)
        finally:
            failures = summary.get("failed_will_retry", 0) + summary.get("permanent_failures", 0) + len(errors)
            with self.factory.begin() as db:
                CycleRunRepository(db).finish(run_id, summary.get("sent", 0), failures,
                                              json.dumps({**summary, "errors": errors}))
        return {"run_id": run_id, **summary, "failures": failures}
