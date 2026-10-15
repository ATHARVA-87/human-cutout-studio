from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def migrate_schema() -> None:
    """Small compatibility migration for the local pre-auth development database."""
    Base.metadata.create_all(engine)
    columns = {item["name"] for item in inspect(engine).get_columns("predictions")}
    with engine.begin() as connection:
        if "user_id" not in columns:
            connection.execute(text("ALTER TABLE predictions ADD COLUMN user_id UUID"))
        if "cutout_path" not in columns:
            connection.execute(text("ALTER TABLE predictions ADD COLUMN cutout_path TEXT"))
