"""AI Newsletter Web API (FastAPI).

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import config, telegram_bot
from .db import Base, SessionLocal, engine
from .models import Source, SourceType
from .routers import auth, channels, subscriber

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't print URLs (they contain the bot token)

SEED_SOURCES = [
    ("OpenAI Blog", SourceType.rss, "https://openai.com/blog/rss.xml", 30),
    ("Anthropic News", SourceType.html, "https://www.anthropic.com/news", 30),
    ("Google DeepMind Blog", SourceType.rss, "https://deepmind.google/blog/rss.xml", 30),
    ("Meta AI Blog", SourceType.html, "https://ai.meta.com/blog/", 30),
    ("Hugging Face Blog", SourceType.rss, "https://huggingface.co/blog/feed.xml", 30),
    ("TechCrunch AI", SourceType.rss, "https://techcrunch.com/category/artificial-intelligence/feed/", 20),
    ("The Verge AI", SourceType.rss, "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 20),
    ("Hacker News (AI)", SourceType.api, "https://hn.algolia.com/api/v1/search?query=AI", 10),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(Source.id).limit(1)):
            db.add_all(Source(name=n, source_type=t, url=u, base_weight=w) for n, t, u, w in SEED_SOURCES)
            db.commit()


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
