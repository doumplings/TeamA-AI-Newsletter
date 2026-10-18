"""Serial polling on a fixed cadence, without overlapping or accumulating drift."""
import logging
import time


def run_schedule(cycle, stop, interval=900, clock=time.monotonic):
    next_run = clock()
    while not stop.is_set():
        try:
            cycle()
        except Exception as exc:
            # Log the type only: database exception strings can contain credentials.
            logging.error('Collector cycle failed (%s); retry at next scheduled tick', type(exc).__name__)
        next_run += interval
        now = clock()
        if now > next_run:
            # Skip ticks missed during a slow cycle rather than starting overlaps.
            next_run += (int((now - next_run) // interval) + 1) * interval
        if stop.wait(max(0, next_run - clock())):
            break
