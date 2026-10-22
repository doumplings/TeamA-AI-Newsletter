"""AI Newsletter Web API (FastAPI).

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from collector.sources import seed_source

from . import config, telegram_bot
from .db import SessionLocal, engine
from .routers import auth, channels, subscriber

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't print URLs (they contain the bot token)


def init_db() -> None:
    """Check the shared schema is there and add the collector's default sources."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL (the schema.sql database the collector uses).")
    if not inspect(engine).has_table("channel_connections"):
        raise RuntimeError("The database has no tables yet. Run once:  psql -d ainews -f schema.sql  (from the repo root)")
    # Same list the collector seeds, so both processes agree on source ids.
    seed_source(SessionLocal)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    telegram_bot.start_polling()
    yield
    telegram_bot.stop_polling()


app = FastAPI(title="AI Newsletter API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(subscriber.router)
app.include_router(telegram_bot.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "telegram": bool(config.TELEGRAM_BOT_TOKEN),
        "email": "smtp" if config.SMTP_HOST else "console",
    }
