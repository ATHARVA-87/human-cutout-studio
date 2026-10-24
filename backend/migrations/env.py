"""Alembic environment: how migrations connect to the database and where the table definitions live."""

from logging.config import fileConfig

from alembic import context

from backend.app.db import models  # noqa: F401  (importing registers every table on Base.metadata)
from backend.app.db.session import Base, engine

config = context.config
# When the app runs migrations at startup it passes its own connection and keeps its own logging setup.
if config.config_file_name and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata  # what the schema SHOULD look like; autogenerate compares the database to this


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    run(connection)  # called from the app (backend/app/db/session.py)
else:
    with engine.connect() as connection:  # called from the `alembic` command line
        run(connection)
