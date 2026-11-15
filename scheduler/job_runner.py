"""JobRunner: the Scheduler actor realized in software (Report 2 Sections 5.1, 8.2 and 9.3).

Each job runs on its own thread, on its own interval, and is never started again
while its last run is still going. The three pipeline stages do not call one
another: each reads and writes the database, and the scheduler decides when each runs.
"""
import json
import logging
import threading
import time

from classifier import ImportanceClassifier
from collector.service import run_cycle as run_scrape
from notifier import Dispatcher

log = logging.getLogger("ainews.scheduler")

# Planned intervals (Section 9.3): scrape every 15 minutes, classify and dispatch every 2.
SCRAPE_INTERVAL = 900
CLASSIFY_INTERVAL = 120
DISPATCH_INTERVAL = 120


class Job:
    def __init__(self, name, interval, run):
        self.name = name
        self.interval = interval
        self.run = run
        self.wake = threading.Event()
        self.thread = None
        self.runs = 0


class JobRunner:
    def __init__(self, factory, scrape_interval=SCRAPE_INTERVAL, classify_interval=CLASSIFY_INTERVAL,
                 dispatch_interval=DISPATCH_INTERVAL, scrape=None, classifier=None, dispatcher=None,
                 clock=time.monotonic, report=None):
        self.factory = factory
        self._scrape = scrape or (lambda: run_scrape(factory))
        self._classifier = classifier or ImportanceClassifier(factory)
        self._dispatcher = dispatcher or Dispatcher(factory)
        self._clock = clock
        self._report = report or (lambda name, summary: print(json.dumps({"cycle": name, **summary}, default=str), flush=True))
        self._stop = threading.Event()
        self.jobs = {
            "scrape": Job("scrape", scrape_interval, self._run_scrape_cycle),
            "classify": Job("classify", classify_interval, self._run_classify_cycle),
            "dispatch": Job("dispatch", dispatch_interval, self._run_dispatch_cycle),
        }

    # ---- the three cycles ----
    def _run_scrape_cycle(self):
        """Collector cycle (UC-10, UC-11). New items mean the classifier has work now."""
        summary = self._scrape()
        if summary.get("items_added"):
            self.jobs["classify"].wake.set()
        return summary

    def _run_classify_cycle(self):
        """ImportanceClassifier.classify_pending (UC-12). Scored items mean the dispatcher has work now."""
        summary = self._classifier.classify_pending()
        if summary.get("items_classified"):
            self.jobs["dispatch"].wake.set()
        return summary

    def _run_dispatch_cycle(self):
        """Dispatcher.dispatch_pending and Dispatcher.send_due (UC-13, UC-14, UC-15)."""
        return self._dispatcher.run_cycle()

    def run_once(self):
        """One scrape, classify and dispatch cycle in order, on the calling thread."""
        return {name: self._run(self.jobs[name]) for name in ("scrape", "classify", "dispatch")}

    # ---- timers ----
    def start(self):
        """Begin the timers: one thread per job, first run immediately."""
        for job in self.jobs.values():
            job.thread = threading.Thread(target=self._loop, args=(job,), name=f"job-{job.name}", daemon=True)
            job.thread.start()

    def stop(self):
        """Ask every job to finish its current cycle and stop."""
        self._stop.set()
        for job in self.jobs.values():
            job.wake.set()

    def join(self, timeout=None):
        for job in self.jobs.values():
            if job.thread is not None:
                job.thread.join(timeout)

    def _run(self, job):
        try:
            summary = job.run()
            self._report(job.name, summary)
            return summary
        except Exception as exc:
            # Type only: database exception strings can contain credentials.
            log.error("%s cycle failed (%s); retry at the next scheduled tick", job.name, type(exc).__name__)
            return {"error": type(exc).__name__}
        finally:
            job.runs += 1

    def _loop(self, job):
        """Serial start-to-start cadence. A slow cycle skips the ticks it missed, so a job
        never overlaps itself; an early wake-up runs the job now without moving its timetable."""
        next_run = self._clock()
        while not self._stop.is_set():
            job.wake.clear()
            self._run(job)
            now = self._clock()
            if now >= next_run:
                next_run += (int((now - next_run) // job.interval) + 1) * job.interval
            job.wake.wait(max(0, next_run - self._clock()))
