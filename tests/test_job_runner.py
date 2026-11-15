"""JobRunner: the Scheduler (Report 2 Sections 8.2 and 9.3)."""
import threading
import time

from scheduler import JobRunner


class Stage:
    """A fake pipeline stage that counts its runs and how many ran at the same time."""

    def __init__(self, summary=None, takes=0.0, fails=False):
        self.summary, self.takes, self.fails = summary or {}, takes, fails
        self.calls = self.running = self.most_at_once = 0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
            self.running += 1
            self.most_at_once = max(self.most_at_once, self.running)
        try:
            time.sleep(self.takes)
            if self.fails:
                raise RuntimeError("boom")
            return self.summary
        finally:
            with self._lock:
                self.running -= 1

    # The classifier and dispatcher are objects with one cycle method each.
    classify_pending = run_cycle = __call__


def runner(scrape, classify, dispatch, intervals=(1000, 1000, 1000)):
    return JobRunner(None, *intervals, scrape=scrape, classifier=classify, dispatcher=dispatch, report=lambda *_: None)


def wait_for(condition, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def stop(jobs):
    jobs.stop()
    jobs.join(timeout=5)
    assert not any(job.thread.is_alive() for job in jobs.jobs.values())


def test_every_job_runs_at_start_and_then_on_its_own_interval():
    scrape, classify, dispatch = Stage(), Stage(), Stage()
    jobs = runner(scrape, classify, dispatch, intervals=(1000, 0.05, 1000))
    jobs.start()
    try:
        assert wait_for(lambda: classify.calls >= 4)
        assert scrape.calls == 1 and dispatch.calls == 1   # their long intervals have not come round
    finally:
        stop(jobs)


def test_a_slow_job_is_never_started_again_while_it_is_still_running():
    scrape = Stage(takes=0.2)
    jobs = runner(scrape, Stage(), Stage(), intervals=(0.02, 1000, 1000))
    jobs.start()
    try:
        assert wait_for(lambda: scrape.calls >= 3)
        assert scrape.most_at_once == 1
    finally:
        stop(jobs)


def test_new_items_wake_the_classifier_and_scored_items_wake_the_dispatcher():
    scrape = Stage({"items_added": 3}, takes=0.1)
    classify, dispatch = Stage({"items_classified": 3}, takes=0.05), Stage()
    jobs = runner(scrape, classify, dispatch)
    jobs.start()
    try:
        # Intervals are 1,000 seconds, so second runs can only come from the wake-ups.
        assert wait_for(lambda: classify.calls >= 2 and dispatch.calls >= 2)
        assert scrape.calls == 1
    finally:
        stop(jobs)


def test_nothing_new_wakes_nobody():
    scrape, classify, dispatch = Stage({"items_added": 0}), Stage({"items_classified": 0}), Stage()
    jobs = runner(scrape, classify, dispatch)
    jobs.start()
    try:
        assert wait_for(lambda: scrape.calls == classify.calls == dispatch.calls == 1)
        time.sleep(0.2)
        assert (scrape.calls, classify.calls, dispatch.calls) == (1, 1, 1)
    finally:
        stop(jobs)


def test_a_failing_cycle_is_logged_and_the_job_keeps_its_timetable():
    scrape = Stage(fails=True)
    jobs = runner(scrape, Stage(), Stage(), intervals=(0.03, 1000, 1000))
    jobs.start()
    try:
        assert wait_for(lambda: scrape.calls >= 3)
    finally:
        stop(jobs)


def test_run_once_runs_scrape_then_classify_then_dispatch():
    order = []

    class Named(Stage):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def __call__(self):
            order.append(self.name)
            return {}

        classify_pending = run_cycle = __call__

    result = runner(Named("scrape"), Named("classify"), Named("dispatch")).run_once()
    assert order == ["scrape", "classify", "dispatch"] and set(result) == {"scrape", "classify", "dispatch"}
