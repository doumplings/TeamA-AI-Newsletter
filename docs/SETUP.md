# AI Newsletter: web app (Team A, CSCI 441)

This is the web client from Report 2 (Sections 8 and 10), plus a small FastAPI web API
so channel setup, the code check and the dashboard can run for real.

```
ai-newsletter/
├── web/   React + TypeScript + Vite + Tailwind CSS + Axios   (the 5 screens)
└── api/   FastAPI + SQLAlchemy                               (auth, channels, profile, history)
```

| Screen | Route | Report class | Live? |
|---|---|---|---|
| Landing page | `/` | LandingPage | static |
| Sign-up / log-in | `/signup`, `/login` | RegisterPage | ✅ |
| Channel setup + code check | `/setup`, `/dashboard/notifications` | ChannelSetupPage, VerifyChannelDialog | ✅ real Telegram / Discord / email |
| Dashboard | `/dashboard` | DashboardPage | ✅ |
| History | `/dashboard/history` | HistoryPage | ✅ (fills up when news is sent) |

---

## 1. Run it with fake data (no server)

```bash
cd web
npm install
npm run dev            # open http://localhost:5173
```

`web/.env` has `VITE_API_MODE=mock`. Everything runs in the browser, and the code dialog
shows you the code because nothing is really sent. Use this mode to work on the UI.

## 2. Run it live

The API and the worker share **one PostgreSQL database** built from `schema.sql`
(root `models.py`). The worker collects, scores and sends news; the API reads and writes
the same tables for the web app. Both read one `.env` file at the repo root.

### The database (hosted on Supabase)

1. [supabase.com/dashboard](https://supabase.com/dashboard) -> **New project**. Save the database password.
2. **Connect** (top bar) -> **Session pooler** -> copy the URI and put it in `.env` as `DATABASE_URL`,
   with the password filled in. Use the Session pooler (port 5432), not the Transaction pooler
   (6543): the collector takes a session-level advisory lock.
3. `python init_db.py` creates the tables and adds the default sources and scoring rules.

Any PostgreSQL 16+ works the same way (for a local one: `createdb ainews`, then
`DATABASE_URL=postgresql:///ainews`). `init_db.py` needs no `psql`.

In the Supabase dashboard, **Table Editor** shows the rows of every table and
**Database -> Schema Visualizer** draws the tables with their foreign-key links.
Row-level security is on for every table, so they are not reachable through Supabase's
public REST API; the app connects as the table owner and is not affected.

### One-time setup (from the repo root)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # set DATABASE_URL and SECRET_KEY
python init_db.py                                     # tables, default sources, scoring rules
python api/seed_demo.py                               # optional: demo account, history, administrator
```

On Windows, keep the repository in a short path (for example `C:\Users\you\TeamA-AI-Newsletter`)
and run `git config core.longpaths true`; a long path stops Python loading SQLAlchemy.

Then three terminals, each with the environment activated, from the repo root:

```bash
# Terminal 1: API (http://localhost:8000/docs)
python -m uvicorn app.main:app --app-dir api --reload --port 8000
```

```bash
# Terminal 2: worker: scrape, classify and dispatch cycles on their intervals (docs/PIPELINE.md)
python -m scheduler --backfill-hours 72
```

```bash
# Terminal 3: web app (http://localhost:5173), with VITE_API_MODE=live in web/.env
cd web && npm install && npm run dev
```

Collected stories show up on the dashboard under **Latest AI news** with their importance
level, and the ones that clear a subscriber's threshold are sent to their channels and
listed in **History**. Administrators also get **Admin -> Sources** and **Admin -> Pipeline**.

| Account from `seed_demo.py` | Password | What it shows |
|---|---|---|
| `demo@ainewsletter.dev` | `demo1234` | A subscriber with an email channel and a notification history |
| `admin@ainewsletter.dev` | `admin1234` | The Admin pages (source list, pipeline status) |

With only `DATABASE_URL` and `SECRET_KEY` filled in, sign-up, email (codes and news are
printed in the terminal), the dashboard and history already work. To make each channel really deliver:

### Telegram (about 2 minutes)
1. In Telegram, open **@BotFather** → `/newbot` → pick a name and a username ending in `bot`.
2. Copy the token into `TELEGRAM_BOT_TOKEN` in `.env` and restart the API and the worker.
3. In the app, pick Telegram → **Open Telegram** → press **Start**. The page notices within 2 seconds.

Locally the API uses **polling** (it asks Telegram for new messages), so you don't need a public URL.
After you deploy, set `TELEGRAM_MODE=webhook` and register `https://<your-api>/telegram/webhook`
with Telegram's `setWebhook`.

### Discord (no setup on our side)
In your Discord server: **Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL**,
then paste it in the app.

### Email
For Gmail: turn on 2-Step Verification, create an **App Password**, then set
`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=<your gmail>`, `SMTP_PASSWORD=<app password>`.

## 3. Tests

```bash
python -m pytest tests -q         # pipeline: classifier, same-story check, dispatcher, retry, scheduler
cd api && python -m pytest -q     # API tests against a throwaway `ainews_test` PostgreSQL database
cd web && npm run build           # type-checks all the TypeScript
```

---

## How the pieces fit (and why)

**One `ApiClient` interface, two implementations** (`web/src/api/`).
`HttpApiClient` calls the server with Axios. `MockApiClient` keeps fake data in localStorage and
follows the same rules (6-digit code, 3 tries, 10 minutes). The pages only import `api`, so moving
from fake to live is one line in `.env`, and the front end can keep working while the back end is unfinished.

**The Vite proxy** (`web/vite.config.ts`) forwards `/api/*` to `localhost:8000`. The browser thinks
it's one site, so the HTTP-only session cookie just works and we don't have to fight CORS.

**Changes from Section 10.2 that are built in**
- Change 1: Telegram is connected by a link with a signed, 10-minute token, so there's no handle and no code to type.
- Change 2: The email field is pre-filled with the sign-up email.
- Change 3: The cursor starts in the first field, and the code checks itself after the 6th digit (pasting works).
- Change 4: There's no "Finish setup" step. The dashboard opens after the first verified channel.
- Changes 5 and 6: Each channel row shows its status, its own level (3 buttons) and on/off.
- Change 7: Sessions last 7 days.
- Change 8: A channel is saved when it's verified. "Save changes" is only for levels and on/off.

**Security basics (REQ-18):** passwords use scrypt with a salt. Sessions and verification codes are
stored only as SHA-256 hashes. Channel contacts are encrypted (Fernet, keyed from `SECRET_KEY`)
with a keyed hash for lookups. The client only ever sees masked contacts.

## Not done yet / next steps
- A removed channel's deliveries leave the subscriber's history: `deliveries` has no `user_id`, and its `channel_id` becomes NULL (C2).
- "Send me a sample news item" sends one made-up item straight away, without waiting for the worker. It uses the same adapters as the Dispatcher (`api/app/adapters.py`).
- Email goes out over SMTP, not a provider's HTTPS API (Section 5.4), so there is no bounce information.
- HTML sources still need hand-written selectors in their settings.
- There's no rate limiting on login or code sending yet.
