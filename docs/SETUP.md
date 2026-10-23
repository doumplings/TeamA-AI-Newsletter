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

The API and the collector share **one PostgreSQL database** built from `schema.sql`
(root `models.py`). The collector writes news into it; the API reads it for the web app.

One-time setup (from the repo root, with PostgreSQL running):

```bash
createdb ainews
psql -d ainews -f schema.sql                          # creates all tables (run once per new database)
python3 -m venv .venv && source .venv/bin/activate    # one environment for the API and the collector
pip install -r requirements.txt
cp api/.env.example api/.env                          # set SECRET_KEY, check DATABASE_URL
```

Then three terminals, each with `source .venv/bin/activate` from the repo root:

```bash
# Terminal 1: API (http://localhost:8000/docs)
cd api && uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2: collector, scrapes the sources into the same database
export COLLECTOR_DATABASE_URL=postgresql+psycopg:///ainews
python -m collector --once        # one cycle now; drop --once to repeat every 30 seconds
```

```bash
# Terminal 3: web app (http://localhost:5173), with VITE_API_MODE=live in web/.env
cd web && npm run dev
```

Collected stories show up on the dashboard under **Latest AI news**. They are not scored or
sent yet: that needs the classifier and the dispatcher (next pipeline stages).
`python api/seed_demo.py` adds a demo account with a notification history.

With nothing filled in `api/.env`, sign-up, email (codes are printed in Terminal 1),
the dashboard and history already work. To make each channel really deliver:

### Telegram (about 2 minutes)
1. In Telegram, open **@BotFather** → `/newbot` → pick a name and a username ending in `bot`.
2. Copy the token into `TELEGRAM_BOT_TOKEN` in `api/.env` and restart the API.
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
cd api && pytest -q        # 17 API tests against a throwaway `ainews_test` PostgreSQL database
cd web && npm run build    # type-checks all the TypeScript
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
- Collected news is not scored (classifier, UC-12) or sent automatically (dispatcher, UC-13/14) yet.
- A removed channel's deliveries leave the subscriber's history: `deliveries` has no `user_id`, and its `channel_id` becomes NULL (C2).
- "Send me a sample news item" stands in for the real Dispatcher until UC-13/14 are merged. It uses the same adapters (`api/app/adapters.py`).
- There's no rate limiting on login or code sending yet.
