# Test real AI news collection in Postman

The standalone testing API uses the canonical PostgreSQL tables from `schema.sql`.
It runs on port **8001**. The subscriber API on port 8000 uses separate tables;
these requests do not populate the subscriber dashboard or send notifications.

## 1. Start the collector database

Open Docker Desktop and wait for it to start. From `TeamA-AI-Newsletter`:

```sh
docker compose -f compose.collector.yml up -d --build --wait
```

This starts a dedicated worker that automatically collects every 30 seconds,
and creates a dedicated PostgreSQL database on localhost port 55432 and initializes
`schema.sql` on its first startup. Data persists in the `collector_data` volume.
The credentials below are for this local development database only.

If you already have a dedicated PostgreSQL database, initialize a **new, empty**
database with `psql "$YOUR_POSTGRES_URL" -v ON_ERROR_STOP=1 -f schema.sql` instead,
and use its SQLAlchemy URL in the next step. Never use the subscriber API database.

## 2. Start the testing API

In the same terminal, from `TeamA-AI-Newsletter`:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
export COLLECTOR_DATABASE_URL='postgresql+psycopg://collector:collector_local@127.0.0.1:55432/ainews_collector'
python -m uvicorn collector.api:app --host 127.0.0.1 --port 8001
```

Keep this terminal running. Open http://127.0.0.1:8001/docs to see the endpoints.
The API loads the project-root `.env`; shell variables take precedence.
Set `COLLECTOR_DATABASE_URL` in either location.
If startup fails, check Docker's health and that `schema.sql` was initialized.

At startup the API adds missing sources: **Hugging Face Blog, OpenAI News,
Google AI Blog, MIT News — Artificial Intelligence**, and **Bluesky — AI news**.
NYT Article Search is also seeded; set `NYT_API_KEY` in the project-root `.env`.
The previous NYT RSS source is disabled at startup. Find the new API source ID
using `GET /collector/sources`; do not reuse the old RSS ID.
Bluesky uses the public API without credentials. Restarting preserves existing source settings and articles.
All sources use policy checks and a minimum five-second interval. Publisher access
and feed validity must be checked with a live run; a blocked source fails independently.

This is an unauthenticated local testing API: keep it bound to `127.0.0.1`.
The Compose worker collects automatically every 30 seconds. Manual POST requests
can trigger an extra cycle; the database lock prevents overlapping collection.
POST runs all active sources in this database. The summary includes a `sources`
array with success/failure and item counts for each source. First collection includes only the previous 900 seconds. Later cycles use each
source's saved successful cutoff, with no overlap. Undated articles are skipped.
Existing historical rows remain.

## 3. Import and run in Postman

1. Choose **Import**, then select `postman/collector.postman_collection.json`.
2. Use the included `base_url` collection variable (`http://127.0.0.1:8001`).
3. Run requests **1 through 9 in order**. Request 2 saves the Hugging Face source
   ID automatically; do not assume its ID is always 1.
4. Set Postman's request timeout to at least **600000 ms** for network delays.

| Request | Expected result |
| --- | --- |
| `GET /health` | `ok: true` with PostgreSQL available |
| `GET /collector/sources` | Source name, URL, last success time and errors |
| `POST /collector/run` | `items_added`, `duplicates`, `failures`, and `run_id` |
| `GET /collector/items?limit=20&offset=0` | Paginated articles and total count |
| `GET /collector/items?source_id=...&limit=20` | Articles from the selected source |
| `POST /collector/run` again | Usually zero new items unless the publisher added news |

`GET /collector/items` returns each article's title, original and canonical URL,
summary, body (when supplied by RSS), publication time, collection time, and source
name/ID. Results are ordered by collection time, newest first. Use `offset=20`
for the next page; `limit` ranges from 1 to 100. Dates are UTC-aware timestamps.
Articles without publication dates are skipped; a missing body is returned as null.
Previously stored undated articles may still be returned.

## 4. Check whether the collected news is correct

- Open the returned article URLs and compare titles and summaries to the publisher.
- Compare `published_at` to the feed; `collected_at` is when our system saved it.
- Run collection again and check that the same articles are not inserted twice.
  Conditional HTTP can return no changes without increasing `duplicates`.
- A source failure is reported as `failures > 0` in an HTTP 200 cycle summary;
  inspect `GET /collector/sources` for `last_error` and `consecutive_failures`.
- `skipped` means another collector cycle holds the database lock; wait and retry.
- Empty results do not prove collection succeeded: check the cycle summary and
  source's last-success timestamp. No articles in a 15-minute window is normal when publishers have no updates;
the Postman tests validate the response structure rather than require new articles.

The feed is AI-focused, but collection itself does not classify articles, assign
importance scores, or verify their factual accuracy.

## Validation

```sh
python -m pytest tests/test_collector.py tests/test_collector_api.py tests/test_collector_schedule.py -q
```

For the optional database integration test, set `COLLECTOR_TEST_DATABASE_URL` to a
**disposable**, schema-initialized PostgreSQL database. That test persists a fixture
article and mocks HTTP, so it checks storage and duplicate handling without a live
publisher dependency. Use Postman for the live network test above.

To stop the database while preserving collected articles:

```sh
docker compose -f compose.collector.yml down
```

## Multiple sources and Bluesky

Restart the API and rebuild the worker to insert the new source defaults, then
run `GET /collector/sources` to find their IDs. Re-import the updated Postman
collection for the new Bluesky requests. Do not assume a specific source ID.

- `POST /collector/run` collects all enabled sources.
- `POST /collector/run?source_id=ID` collects one enabled source.
- `GET /collector/items?source_id=ID` shows that source's articles/posts.
- `PATCH /collector/sources/ID` with `{"is_active": false}` disables a source;
  use `true` to enable it. Existing articles remain available.

Bluesky uses `https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts`, with
AI-related search terms, English language and latest-first ordering. Cursor
pagination collects up to 100 pages; hitting the limit fails the source and retains
its checkpoint. No paid API credits are required. Public search can return 403; configure the
authenticated option below when that happens.
An additional local keyword filter excludes unrelated posts and replies. Results
link to the original Bluesky post using the author's stable DID. This filtering
cannot guarantee relevance, factual accuracy, or complete search-index coverage.
Search timestamps may reflect indexing time; local filtering checks publication
`createdAt` against the collector's window. Delayed indexing can miss posts under
the strict publication-time policy.

The former social provider is disabled automatically on startup. Historical source
and article rows remain so foreign-key references and history are preserved. Its
credentials are no longer read by the collector. You may remove unused credentials
from your private `.env`; they are not required for Bluesky.

The public AppView search endpoint uses API handling; website URLs still use
robots.txt checks. Requests respect pacing, Retry-After and bounded retries.
Bluesky access errors include HTTP status codes in the source's `last_error`.
A source failure does not prevent other sources from collecting.

## Automatic 15-minute collection

Keep Docker running. The dedicated `collector-worker` runs immediately on startup,
then on a fixed 30-second cadence, independently of Postman or the testing API.
Check recent cycle summaries with:

```sh
docker compose -f compose.collector.yml logs --tail=50 collector-worker
```

A normal sequence is 12:00–12:15, 12:15–12:30, then 12:30–12:45, using inclusive
starts and exclusive ends. On a failed
source, its next successful run catches up from its prior successful cutoff.
Sources must provide publication dates; late-added articles with dates older than
the previous cutoff can be missed under this strict publication-time rule.

Restart after changes to `.env` or code:

```sh
docker compose -f compose.collector.yml up -d --build --force-recreate collector-worker
```

For host-only operation, `python -m collector` runs the same worker and reads the
root `.env`. Use `python -m collector --once` for a single cycle. Avoid starting
multiple schedulers; the lock prevents overlap but does not coordinate their ticks.

## Bluesky search returns 403

Public search can be restricted. Create a Bluesky account if you do not have one,
then create an **App Password** in Bluesky Settings → Privacy and Security → App
Passwords. Use an app password, not your normal account password.

Add the following privately to the project-root `.env`:

```dotenv
BLUESKY_HANDLE=your-handle.bsky.social
BLUESKY_APP_PASSWORD=your-app-password
```

The collector then creates a session through `bsky.social` and sends authenticated
search through its AppView proxy. This option supports Bluesky-hosted accounts;
custom PDS hosting needs separate server configuration. Credentials and session
JWTs stay out of source records, responses, and logs. The session is reused across
pages within a cycle. The worker remains on the same 30-second schedule.

```sh
docker compose -f compose.collector.yml up -d --build --force-recreate collector-worker
docker compose -f compose.collector.yml logs -f --tail=30 collector-worker
```

If login fails, check the handle and app password. If authenticated search still
returns 403, check account access and service availability. No hostname or path
case changes are used to evade an endpoint restriction. The failed source keeps
its checkpoint and other sources continue normally.

## Successful cycles but zero new articles

A successful cycle means fetching and parsing completed. It does not guarantee
new posts in the publication window. Each successful source now includes
`diagnostics`: `returned_by_source`, `filtered_by_adapter` (irrelevant posts or
replies), `outside_window`, `undated_items`, and `eligible_items`. Duplicates are
counted separately after the publication filter.

Restart the testing API after updating code. Preview a wider window in Postman:

```text
GET /collector/preview?source_id=16&lookback_hours=24&limit=20
```

Use actual source IDs from `/collector/sources`. The preview returns live results
and diagnostic counts, without saving articles or moving a checkpoint. It does
not require news to have been saved in the database. `lookback_hours` supports
1–168; `limit` controls the displayed results, not the network pagination limit.
The updated Postman collection includes RSS and Bluesky preview requests.
If even the wider preview returns no source items, investigate search terms and
provider coverage rather than assuming no AI news was published.

### Bluesky query diagnostics

AI terms are searched independently (`artificial intelligence`, `machine learning`,
`LLM`, `OpenAI`, `Anthropic`) rather than combined into a Boolean expression.
Posts found by multiple terms are merged by canonical permalink. Preview and cycle
results include `diagnostics.searches` with per-term counts and
`duplicate_search_hits`. The aggregate returned/filtered counts count search hits,
while `eligible_items` is the number of unique eligible posts.
Startup upgrades the built-in Bluesky query configuration in existing databases
without moving its successful checkpoint or changing its enabled state.
