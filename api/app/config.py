"""Settings read from environment variables (or a .env file next to this folder)."""
import os
from pathlib import Path

from dotenv import load_dotenv

_API_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_API_DIR / ".env")
load_dotenv(_API_DIR.parent / ".env")  # the repo-root .env the collector reads; api/.env wins


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# The same PostgreSQL database the collector writes to (created with schema.sql).
DATABASE_URL = _get("DATABASE_URL") or _get("COLLECTOR_DATABASE_URL") or "postgresql+psycopg:///ainews"

# Signs the Telegram start-link token and is the key for encrypting channel
# contacts (chat IDs, emails, webhook URLs). It must stay the same between
# restarts, or saved channels can no longer be read.
SECRET_KEY = _get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY in api/.env (any long random string, e.g. `python -c \"import secrets; print(secrets.token_hex(32))\"`).")

# Session cookie (Change 7: sessions last 7 days)
SESSION_DAYS = 7
COOKIE_SECURE = _get("COOKIE_SECURE", "false").lower() == "true"

# Verification codes (ChannelVerifier in Section 8)
CODE_LIFETIME_MINUTES = 10
MAX_FAILED_ATTEMPTS = 3
TELEGRAM_LINK_MINUTES = 10

# Telegram bot
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = _get("TELEGRAM_BOT_USERNAME")  # optional, looked up with getMe if empty
TELEGRAM_MODE = _get("TELEGRAM_MODE", "polling")  # "polling" for local dev, "webhook" when deployed
TELEGRAM_WEBHOOK_SECRET = _get("TELEGRAM_WEBHOOK_SECRET")

# Email over SMTP. If SMTP_HOST is empty, emails are printed in the server console instead.
SMTP_HOST = _get("SMTP_HOST")
SMTP_PORT = int(_get("SMTP_PORT", "587"))
SMTP_USER = _get("SMTP_USER")
SMTP_PASSWORD = _get("SMTP_PASSWORD")
SMTP_FROM = _get("SMTP_FROM") or SMTP_USER

# Allowed browser origins (only needed if the web app is NOT served through the Vite proxy)
CORS_ORIGINS = [o for o in _get("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
