"""Run the dedicated collector worker (30-second cadence by default)."""
import argparse
import json
import math
import os
import signal
from threading import Event

from models import make_engine, make_session_factory
from .config import load_settings
from .scheduler import run_schedule
from .service import run_cycle
from .sources import seed_source


def main():
    load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=float, default=30, help='Start-to-start polling seconds (default: 30)')
    parser.add_argument('--once', action='store_true', help='Run one cycle and exit')
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 1:
        parser.error('--interval must be a finite number >= 1')
    url = os.environ.get('COLLECTOR_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not url:
        parser.error('Set COLLECTOR_DATABASE_URL to the collector PostgreSQL database')
    engine = make_engine(url)
    factory = make_session_factory(engine)
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        seed_source(factory)
        def cycle():
            print(json.dumps(run_cycle(factory)), flush=True)
        if args.once:
            cycle()
        else:
            run_schedule(cycle, stop, args.interval)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
