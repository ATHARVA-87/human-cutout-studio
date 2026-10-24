from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, Result, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASELINE_REVISION = "0001"  # the first migration: the schema as it was before migrations were introduced
MIGRATION_LOCK_ID = 2026_10_25  # names the PostgreSQL lock that lets only one app instance migrate at a time


class Base(DeclarativeBase):
    pass


# A small connection pool: free hosted Postgres plans limit connections, and requests
# never hold a connection while the model runs (see services/credits.py).
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,  # test a connection before use; hosted DBs drop idle ones
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one database session per HTTP request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def rows_affected(result: Result[Any]) -> int:
    """How many rows an UPDATE or DELETE changed. (SQLAlchemy's type hints only put .rowcount on CursorResult.)"""
    return cast(CursorResult[Any], result).rowcount


def run_migrations() -> None:
    """Bring the database schema up to date ("alembic upgrade head"). Runs at every startup; a no-op if current.

    Everything happens in ONE transaction (PostgreSQL can roll back schema changes too), behind an advisory
    lock, so two app instances starting at the same moment never migrate at the same time.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            # A database created before migrations existed already has the baseline tables:
            # record it as being at the baseline, then apply only the newer migrations.
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
