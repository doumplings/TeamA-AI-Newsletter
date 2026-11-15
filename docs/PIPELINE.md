# Pipeline worker: scheduler, classifier, dispatcher

The worker is one process that runs the three scheduled cycles from Report 2
(Sections 5.1, 8.2 and 9). The stages never call each other: each one reads and
writes the shared PostgreSQL database, and the scheduler decides when each runs.

```
scrape (collector/)  ->  news_items  ->  classify (classifier/)  ->  dispatch + send (notifier/)
        UC-10, UC-11                          UC-12                       UC-13, UC-14, UC-15
                         every cycle writes one row to cycle_runs
```

| Package | Report class | What it does |
|---|---|---|
| `scheduler/` | JobRunner | One thread per job, each on its own interval, never started again while its last run is still going. New items wake the classifier early; scored items wake the dispatcher early. |
| `collector/` | Collector, adapters, PolicyChecker, Normalizer | Fetches each active source inside its access policy and stores new items. See [COLLECTOR.md](COLLECTOR.md). |
| `collector/dedup.py` | Deduplicator | Same-story check: at least half of the title words shared and at most 3 days apart (Section 6.3.3). The repeat is stored, linked with `duplicate_of`, and the original gets `corroboration_count + 1`. Only other sources are compared. |
| `classifier/` | ImportanceClassifier, ScoreResult | Score = source points + keyword points + 5 x extra sources, kept in 0-100. High is 70+, Medium 40-69, Low below 40. Rules are rows in `scoring_rules` (K1-K6, Table 6-6b); `rule_matches` records why an item scored as it did. |
| `notifier/` | Dispatcher, RetryHandler | Queues one `deliveries` row per recipient channel (enabled, verified, level high enough, source followed), then sends what is due through the channel adapters in `api/app/adapters.py`. Failures wait 1, 2, 4, then 8 minutes, up to 5 tries. |

## Run it

Setup is in [SETUP.md](SETUP.md): one `.env` at the repo root, then `python init_db.py`.

```bash
python -m scheduler            # every 15 min / 2 min / 2 min (Section 9.3)
python -m scheduler --once     # one scrape, classify and dispatch cycle, then exit
python -m scheduler --scrape-interval 60 --classify-interval 20 --dispatch-interval 20   # demo pace
```

- `--backfill-hours 72`: on the first run only, RSS sources that have never been
  collected reach back that many hours. Without it a new database only receives
  items published in the last 15 minutes.
- Intervals can also be set with `SCRAPE_INTERVAL_SECONDS`, `CLASSIFY_INTERVAL_SECONDS`
  and `DISPATCH_INTERVAL_SECONDS` in `.env`.
- Each cycle prints one JSON line. Stop with Ctrl+C; the current cycle finishes first.
- The worker must use the same `SECRET_KEY` as the API, because it decrypts the channel
  contacts the API stored. Reading the same `.env` takes care of that.

## Where to look

- **Web app, signed in as an administrator:** Admin -> Pipeline shows the queue sizes and
  the latest cycle runs (refreshes every 10 seconds); Admin -> Sources adds, edits,
  switches off and removes sources (UC-9). `python api/seed_demo.py` creates the
  administrator `admin@ainewsletter.dev`.
- **Database:** `cycle_runs` (one row per cycle), `news_items` (score, level,
  `duplicate_of`, `classified_at`, `dispatched_at`), `rule_matches`, `deliveries`.

## Behaviour worth knowing

- **Backlog is not sent.** An item still undispatched 24 hours after it was collected is
  marked dispatched without notifying anyone, so starting the worker on an old database
  does not flood subscribers.
- **Repeats are scored but never delivered**; the original already went out.
- **A story is scored with the sources known at that moment.** A later repeat raises
  `corroboration_count` but does not rescore or resend it (Section 9.1.3).
- **Nothing is sent twice.** `deliveries` has a unique (item, channel) rule, and due rows
  are read with `FOR UPDATE SKIP LOCKED`, so two workers can run at once.
- **Sources that need credentials fail until they have them.** The New York Times source
  needs `NYT_API_KEY`; Bluesky public search may answer 403 without `BLUESKY_HANDLE` and
  `BLUESKY_APP_PASSWORD`. Add the keys to `.env`, or switch the source off in Admin -> Sources.

## Tests

```bash
python -m pytest tests -q      # classifier, same-story check, retry, dispatcher, scheduler, adapters
cd api && python -m pytest -q  # Web API, including source administration
```

The test names carry the IDs from Report 2, Section 11 (UT-01 to UT-18, UT-25 to UT-28,
IT-02 to IT-06, ST-11). Database tests build a throwaway PostgreSQL database from
`schema.sql`; they find the server through `PGHOST`, `PGPORT` and `PGUSER`.
