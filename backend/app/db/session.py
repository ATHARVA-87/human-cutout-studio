from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings


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


def create_tables() -> None:
    """Create any missing tables. Existing tables are left as they are (no migrations in this project)."""
    from . import models  # noqa: F401  (importing registers the tables on Base.metadata)

    Base.metadata.create_all(engine)
