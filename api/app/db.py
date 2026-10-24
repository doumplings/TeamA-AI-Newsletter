"""Database connection: the shared PostgreSQL database (schema.sql) the collector also writes to."""
from models import make_engine, make_session_factory

from . import config

engine = make_engine(config.DATABASE_URL)
SessionLocal = make_session_factory(engine)


def get_db():
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
