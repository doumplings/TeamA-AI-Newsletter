"""Set up a new database: create the tables from schema.sql, then add the default
sources and scoring rules. Safe to run again; an existing schema is left alone.

    python init_db.py            # uses DATABASE_URL from .env (repo root or api/)
    python init_db.py --check    # only show what is in the database

Works against any PostgreSQL, local or hosted (e.g. Supabase), without needing psql.
"""
import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from classifier import seed_rules  # noqa: E402
from collector.config import load_settings  # noqa: E402
from collector.sources import seed_source  # noqa: E402
from models import Base, make_engine, make_session_factory  # noqa: E402


def database_url():
    load_settings()
    from dotenv import load_dotenv
    load_dotenv(ROOT / "api" / ".env", override=False)
    url = os.environ.get("DATABASE_URL") or os.environ.get("COLLECTOR_DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL in .env (see .env.example).")
    return url


def create_schema(engine):
    """Run schema.sql as one script (it is a single BEGIN ... COMMIT)."""
    raw = engine.raw_connection()
    try:
        connection = raw.driver_connection
        connection.autocommit = True
        connection.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
    finally:
        raw.close()


def close_public_data_api(engine):
    """On Supabase, keep the tables out of the auto-generated public REST API.

    Supabase serves every table in ``public`` to anyone holding the project's anon
    key unless row-level security is on. Turning it on with no policies shuts that
    door; this app connects as the table owner, which RLS does not restrict.
    Returns the number of tables changed (0 on a plain PostgreSQL server).
    """
    with engine.begin() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = 'anon'")):
            return 0
        tables = [t.name for t in Base.metadata.sorted_tables]
        open_tables = conn.scalars(
            text("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace "
                 "AND relkind = 'r' AND NOT relrowsecurity AND relname = ANY(:names)"),
            {"names": tables},
        ).all()
        for name in open_tables:
            conn.execute(text(f'ALTER TABLE public."{name}" ENABLE ROW LEVEL SECURITY'))
        return len(open_tables)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Only report the tables and row counts")
    args = parser.parse_args()

    engine = make_engine(database_url())
    try:
        print(f"Database: {engine.url.host or 'local socket'} / {engine.url.database}")
        if not args.check:
            if inspect(engine).has_table("channel_connections"):
                print("Schema already there; left as it is.")
            else:
                create_schema(engine)
                print("Created the schema from schema.sql.")
            closed = close_public_data_api(engine)
            if closed:
                print(f"Supabase: row-level security turned on for {closed} tables (closes the public REST API).")
            factory = make_session_factory(engine)
            seed_source(factory)
            seed_rules(factory)
        existing = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name in existing:
                    count = conn.scalar(text(f'SELECT count(*) FROM "{table.name}"'))
                    print(f"  {table.name:<22}{count:>7} rows")
                else:
                    print(f"  {table.name:<22}missing")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
