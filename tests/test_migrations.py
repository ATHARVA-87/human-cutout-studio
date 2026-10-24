"""Migrations must build the schema from nothing, and every migration must be reversible."""

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.app.core.config import settings
from backend.app.db.session import PROJECT_ROOT

DATABASE = "segmentation_migrations_test"


@pytest.fixture()
def empty_database():
    url = make_url(settings.database_url)
    try:
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE}"'))
            connection.execute(text(f'CREATE DATABASE "{DATABASE}"'))
    except Exception:
        if os.environ.get("CI"):
            raise
        pytest.skip("PostgreSQL is not reachable; start it with `docker compose up db -d`.")
    engine = create_engine(url.set(database=DATABASE))
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE}"'))
    admin.dispose()


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    return config


def migrate(engine, action, target: str) -> set[str]:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        action(config, target)
    return set(inspect(engine).get_table_names())


def test_upgrade_from_nothing_then_downgrade_and_upgrade_again(empty_database) -> None:
    tables = migrate(empty_database, command.upgrade, "head")
    assert {"users", "session_tokens", "credit_transactions", "predictions", "compositions", "ip_events"} <= tables
    with empty_database.connect() as connection:
        newest = ScriptDirectory.from_config(alembic_config()).get_current_head()
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == newest
    assert migrate(empty_database, command.downgrade, "base") <= {"alembic_version"}  # every migration undone
    assert "ip_events" in migrate(empty_database, command.upgrade, "head")
