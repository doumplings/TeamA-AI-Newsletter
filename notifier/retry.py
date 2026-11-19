"""What happens after a failed send (UC-15, Report 2 Sections 6.3.4 and 9.1.5).

The wait doubles each time: 1, 2, 4, then 8 minutes, up to 5 tries in total,
unless the channel's rate limit asks for longer. With a dispatch cycle every
2 minutes the last try is at most 25 minutes after the first (REQ-15).
"""
import logging
from datetime import timedelta

from models import MAX_DELIVERY_ATTEMPTS, DeliveryRepository, DeliveryStatus

log = logging.getLogger("ainews.notifier")


class RetryHandler:
    def __init__(self, first_wait=timedelta(minutes=1), max_tries=MAX_DELIVERY_ATTEMPTS):
        self.first_wait = first_wait
        self.max_tries = max_tries

    def next_wait(self, attempts, retry_after=None):
        """Wait before the next try, given how many tries have been made (1 to 4)."""
        wait = self.first_wait * 2 ** (attempts - 1)
        if retry_after is not None:
            wait = max(wait, timedelta(seconds=retry_after))
        return wait

    def record_failure(self, db, delivery, result):
        """Mark the delivery failed with a later retry time, or permanently failed
        after the last try or an error retrying cannot fix. Returns the new status."""
        repository = DeliveryRepository(db)
        error = (result.error or "send failed")[:500]
        tries = delivery.attempts + 1
        if result.permanent:
            repository.mark_permanent_failure(delivery.delivery_id, error)
            status = DeliveryStatus.permanent_failure
        else:
            # mark_failed turns the 5th failed try into a permanent failure itself.
            status = repository.mark_failed(delivery.delivery_id, error, self.next_wait(tries, result.retry_after))
        if status == DeliveryStatus.permanent_failure:
            log.error("Delivery %s gave up after %s tries: %s", delivery.delivery_id, tries, error)
        else:
            log.warning("Delivery %s failed (try %s of %s): %s", delivery.delivery_id, tries, self.max_tries, error)
        return status
