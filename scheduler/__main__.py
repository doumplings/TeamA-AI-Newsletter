"""Run the worker: scrape, classify and dispatch cycles on their intervals.

    python -m scheduler                 # every 15 min / 2 min / 2 min (Report 2, Section 9.3)
    python -m scheduler --once          # one scrape, classify and dispatch cycle, then exit
    python -m scheduler --scrape-interval 60 --classify-interval 20 --dispatch-interval 20   # demo pace
"""
import argparse
import json
import logging
import math
import os
import signal
from datetime import datetime, timedelta, timezone
from threading import Event

from sqlalchemy import update

from classifier import seed_rules
from collector.config import load_settings
from collector.sources import seed_source
from models import Source, SourceType, make_engine, make_session_factory
from .job_runner import CLASSIFY_INTERVAL, DISPATCH_INTERVAL, SCRAPE_INTERVAL, JobRunner


def _seconds(name, default):
    return float(os.environ.get(name) or default)


def backfill(factory, hours):
    """Let RSS sources that have never been collected reach back ``hours`` on their first cycle.

    Without this a new database only receives items published in the last 15 minutes.
    Feeds only: a search API asked for days of posts would run past its page limit.
    """
    since = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=hours)
    with factory.begin() as db:
        return db.execute(
            update(Source)
            .where(Source.last_success_at.is_(None), Source.source_type == SourceType.rss, Source.is_active.is_(True))
            .values(last_success_at=since)
        ).rowcount


def main():
    load_settings()
    import notifier  # noqa: F401  (puts api/ on the import path)
    from app import config  # the API's settings: same database, same SECRET_KEY for channel contacts

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scrape-interval", type=float, default=_seconds("SCRAPE_INTERVAL_SECONDS", SCRAPE_INTERVAL))
    parser.add_argument("--classify-interval", type=float, default=_seconds("CLASSIFY_INTERVAL_SECONDS", CLASSIFY_INTERVAL))
    parser.add_argument("--dispatch-interval", type=float, default=_seconds("DISPATCH_INTERVAL_SECONDS", DISPATCH_INTERVAL))
    parser.add_argument("--once", action="store_true", help="Run each cycle once, in order, and exit")
    parser.add_argument("--backfill-hours", type=float, default=0,
                        help="First run only: RSS sources never collected before reach back this many hours")
    args = parser.parse_args()
    for value in (args.scrape_interval, args.classify_interval, args.dispatch_interval):
        if not math.isfinite(value) or value < 1:
            parser.error("intervals must be finite numbers >= 1 (seconds)")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs contain the bot token

    engine = make_engine(config.DATABASE_URL)
    factory = make_session_factory(engine)
    try:
        seed_source(factory)
        seed_rules(factory)
        if args.backfill_hours > 0:
            print(json.dumps({"backfill_hours": args.backfill_hours, "sources": backfill(factory, args.backfill_hours)}), flush=True)
        runner = JobRunner(factory, args.scrape_interval, args.classify_interval, args.dispatch_interval)
        if args.once:
            runner.run_once()
            return
        stop = Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        runner.start()
        while not stop.wait(0.5):  # short waits, so Ctrl+C is noticed on Windows too
            pass
        runner.stop()
        runner.join(timeout=90)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
