# News collector (UC scrape cycle)

The collector uses **root `models.py` and `schema.sql` (PostgreSQL)**. The web
API currently has a separate, incompatible set of models in `api/app/models.py`.
Do not run the API's `init_db` against the collector database: its `sources`,
`news_items`, users and delivery columns differ. Schema unification is still
needed before collected news can flow into the current web UI. Collection does
not classify news or send alerts; those are subsequent pipeline stages.

## Install and run

From the repository root (Python 3.11+ and PostgreSQL):

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://user:password@localhost/ainews'
# On a NEW database, initialize once (psql uses a plain PostgreSQL URL):
psql 'postgresql://user:password@localhost/ainews' -f schema.sql
# Only for sources configured with render_js=true:
python -m playwright install chromium
python -m collector --once           # one cycle; JSON summary on stdout
python -m collector                  # worker: immediate cycle, then every 30 seconds
```

For the complete local setup, run `docker compose -f compose.collector.yml up -d --build --wait`.
It starts PostgreSQL and a dedicated collector worker; the root `.env` must exist
and is mounted read-only for database settings. The worker restarts
with Docker and does not run inside FastAPI processes. Use `--interval` only to
change polling cadence; the first publication window remains 900 seconds.

The default cadence is start-to-start (00:00, 00:30, 01:00), rather than waiting
30 seconds after completion. Slow cycles run serially and skip missed ticks.
A PostgreSQL advisory lock prevents overlap with manual API requests and other
workers. SIGINT/SIGTERM request a stop after the current cycle.

Each source collects publication timestamps in `[last successful cutoff, current
cutoff)`. On first use the start is current cutoff minus 900 seconds. All sources
share a cycle cutoff. Failed sources
keep their previous cutoff and catch up next cycle, which can exceed 900 seconds.
Successful cutoffs persist across restarts. Undated and future-dated items are not
inserted. Feed responses are fetched again on each poll so an item excluded as
future-dated can become eligible in a later window. Summary results show the
window start/end for each successful source.

Strict publication windows can miss articles added to a feed late with an older
publication timestamp. Provider retention and search windows can also limit
outage recovery. Older articles already stored remain in the database.

## Configure sources

Sources live in the canonical database's `sources` table. The CLI does not seed
sources. The optional [local testing API](POSTMAN.md) seeds four RSS feeds and an enabled public Bluesky
source at startup for Postman testing. It also seeds a New York Times Article
Search API source. Put `NYT_API_KEY` in the project-root `.env` and enable Article
Search for that key in the NYT developer portal. Startup disables the previous,
blocked NYT RSS source and inserts the API source with a new ID; historical rows
remain. Existing API source settings are preserved. Restart the testing API and
rebuild the worker after updating the code.

NYT searches for `"artificial intelligence"`, requests UTC calendar date bounds,
and applies the exact publication window locally. It maps headlines, links,
abstracts and lead paragraphs; it does not fetch full paywalled articles.
The local relevance filter checks only article titles for AI terms (including
AI, A.I., artificial intelligence, machine learning, LLM, chatbot, ChatGPT,
OpenAI and Anthropic). Summaries and subject keywords do not affect relevance.
Relevant articles with indirect titles may be excluded. Existing saved articles
are not reclassified by this filter.
The dedicated adapter uses the official authenticated API endpoint, waits at least
12 seconds between requests, and follows numbered pages (up to 100). Incomplete
pagination fails without advancing the checkpoint. API keys are read at request
time and are never stored in source config or included in reported errors.

Find the new ID with `GET /collector/sources`, then test without saving using
`GET /collector/preview?source_id=ID&lookback_hours=168&limit=20`.
Use `POST /collector/run?source_id=ID` to collect and
`GET /collector/items?source_id=ID` to inspect saved articles.

For every source, manually review its
terms and official API/RSS availability, then record `terms_url` and
`terms_status: "allowed"` in `config`. Unreviewed or disallowed sources fail closed.
This is a human review gate, not automatic legal interpretation; review again when
terms change. robots.txt is checked each cycle per host; denied paths, failed
robots checks, and robots redirects fail closed. Missing robots (404/410) permits
fetching after terms approval. No paywall or login bypass is attempted.

For example, after reviewing the publisher's current terms, insert an RSS source:

```sql
INSERT INTO sources (name, source_type, url, base_weight, config)
VALUES ('Hugging Face Blog', 'rss', 'https://huggingface.co/blog/feed.xml', 30,
'{"terms_status":"allowed","terms_url":"https://huggingface.co/terms-of-service",
  "min_interval_seconds":5}');
```

The same RSS adapter handles AI news publishers and AI company feeds. Use each
publisher's official feed URL. The existing API's seed list is a starting point
for review; it is not imported into the canonical database automatically.

HTML sources require `item_selector`, `title_selector`, and `link_selector`.
Optional `date_selector` reads a `datetime` attribute or visible date;
`summary_selector` and `body_selector` extract card content. Example config:

```json
{
  "terms_url": "https://publisher.example/terms",
  "terms_status": "allowed",
  "item_selector": "article",
  "title_selector": "h2 a",
  "link_selector": "h2 a",
  "date_selector": "time",
  "summary_selector": "p",
  "min_interval_seconds": 5,
  "render_js": false
}
```

Use `render_js: true` for permitted JavaScript pages. Playwright routes document,
script, XHR and fetch traffic through the same Requests policy and pacing checks;
other resources are blocked. Browser APIs that require cookies, POSTs, or complex
redirect behavior may need a dedicated official API adapter. HTML extraction is
from the listing cards, not a recursive full-site crawl. HTML listing pagination
is not implemented; choose a feed/API for high-volume sources.

Set `api_url` or `rss_url` on an HTML source when an official endpoint exists.
`api_url` takes priority, then `rss_url`, then the configured source URL/type.
Endpoints are explicitly configured following review; discovery is not automatic.
Changing endpoints requires clearing `etag` and `last_modified` on the source.
There is no fallback to HTML following an API/feed access failure.

Generic JSON APIs accept `items_path` (a dotted object path, or empty for a root
array), `fields` mapping `title`, `url`, `published_at`, `summary`, and `body` to
row paths, optional `params`, `since_param`, `next_token_path`, and
`page_token_param`. Dates must be ISO 8601 or RFC email dates. For example, HN
Algolia uses `items_path: "hits"`, fields `url: "url"`,
`published_at: "created_at"`; scope the request's `params` to AI news.
Missing required title/link or invalid dates fail the source without advancing
its checkpoint. Items with no publication date are skipped. Generic numeric-offset/page-number pagination needs a dedicated
adapter; token pagination is supported.

## Bluesky

The testing API and dedicated worker seed an enabled **Bluesky — AI news** source
at `https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts`. Public requests do not need a token, but public search can return 403. For
authenticated search, set `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD` in the root
`.env`; see [Postman troubleshooting](POSTMAN.md#bluesky-search-returns-403).
The adapter maps post text, publication `createdAt` and AT URIs to normalized news
items with stable `bsky.app` permalinks. Replies and unrelated text are excluded.
The search uses AI terms and English language; it is a relevance filter, not a
factual verification service. Query indexing can lag publication time.

The API receives `since` and `until` for the current publication window, returns
latest-first results, and paginates with `cursor`. The default limit is 100 results
per page and 100 pages per cycle. Incomplete pagination fails without advancing
the source cutoff. The exact public AppView endpoint uses API access handling;
website sources retain robots checks. Error status, pacing and retry limits remain.

Startup retires the previous social provider's source record without removing
historical articles. The collector no longer loads its bearer-token settings.

## Reliability and duplicate handling

- `last_checked_at` records attempted sources. `last_success_at` stores the
  successful publication-window cutoff, and failed sources never skip ahead.
- Publication windows have inclusive starts and exclusive ends. Undated articles are skipped. Conditional validators
  are stored for diagnostics, but requests re-read content each cycle so items
  previously beyond the upper cutoff can become eligible later.
- Requests respect the greatest configured delay, robots crawl delay, and robots
  request rate. HTTP 429 and transient server errors retry at most three times,
  respecting Retry-After. A wait over 60 seconds fails the
  source for a later cycle. No token is logged in source errors.
- Canonical URLs remove fragments and common tracking parameters, sort queries,
  and are protected by the existing database unique constraint. Exact normalized
  title plus nonempty body/summary also discards reposts under different URLs.
  Fuzzy/semantic matching (the remainder of UC-11) is not implemented.
- Items and source success state commit atomically per source. A failed source
  rolls back and records its failure independently; later sources still run.
- `cycle_runs.items_processed` is the number of inserted records, `failures` is
  the number of failed sources; `notes` contains duplicate totals and errors.
  Inspect `sources.last_error` and `consecutive_failures` for operational status.

## Tests

```sh
pip install pytest
python -m pytest tests/test_collector.py tests/test_collector_api.py tests/test_collector_schedule.py -q
```

Unit tests cover adapters, URL normalization, policies, pacing, 304 preservation,
feed preference, and incomplete pagination. Run a real cycle against a disposable
PostgreSQL database with reviewed sources to validate live source policy, browser
installation, database transactions, and changing publisher markup.

API references: [Requests](https://requests.readthedocs.io/en/stable/user/advanced/),
[feedparser](https://feedparser.readthedocs.io/en/latest/date-parsing.html),
[Playwright routing](https://playwright.dev/python/docs/network),
[Bluesky API](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts).

### Bluesky query diagnostics

AI terms are searched independently (`artificial intelligence`, `machine learning`,
`LLM`, `OpenAI`, `Anthropic`) rather than combined into a Boolean expression.
Posts found by multiple terms are merged by canonical permalink. Preview and cycle
results include `diagnostics.searches` with per-term counts and
`duplicate_search_hits`. The aggregate returned/filtered counts count search hits,
while `eligible_items` is the number of unique eligible posts.
Startup upgrades the built-in Bluesky query configuration in existing databases
without moving its successful checkpoint or changing its enabled state.

`docker compose -f compose.collector.yml up -d --build collector-worker`
`docker compose -f compose.collector.yml logs -f --tail=50 --timestamps collector-worker`
