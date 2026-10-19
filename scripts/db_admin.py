#!/usr/bin/env python3
"""Owner-only database tools: check how much space the database uses, or wipe all app data.

There is deliberately NO web endpoint for this. To run it you need the database connection
string (your local .env, or the Neon URL for production). Having that secret is the permission.

  python scripts/db_admin.py stats                     # local database from .env
  python scripts/db_admin.py reset                     # asks you to type the database name first
  SEGMENTATION_DATABASE_URL='postgresql+psycopg://...' python scripts/db_admin.py stats   # production
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.db import models  # noqa: E402,F401  (registers the tables)
from backend.app.db.session import Base, engine  # noqa: E402


def app_tables() -> list[str]:
    """Tables defined by the app that actually exist in this database."""
    existing = set(inspect(engine).get_table_names())
    return [table.name for table in Base.metadata.sorted_tables if table.name in existing]


def stats() -> None:
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    with engine.connect() as connection:
        size = connection.scalar(text("SELECT pg_size_pretty(pg_database_size(current_database()))"))
        print(f"Total size: {size}")
        for table in app_tables():
            rows = connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            print(f"  {table:<22} {rows:>8} rows")


def reset(skip_confirmation: bool) -> int:
    target = engine.url
    print(f"Database: {target.render_as_string(hide_password=True)}")
    if not skip_confirmation:
        typed = input(f"This deletes ALL users, sessions, credits and history. Type the database name ({target.database}) to confirm: ")
        if typed.strip() != target.database:
            print("Names do not match. Nothing was deleted.")
            return 1
    tables = app_tables()
    if tables:
        with engine.begin() as connection:  # one transaction: all tables are emptied, or none
            connection.execute(text("TRUNCATE " + ", ".join(f'"{name}"' for name in tables) + " RESTART IDENTITY CASCADE"))
    print(f"Emptied {len(tables)} tables.")

    # Generated images live on the app server's disk. From your laptop only the local folder can be
    # cleared; on Render the disk is temporary and is wiped on every restart anyway.
    if target.host in {"localhost", "127.0.0.1"} and settings.storage_dir.is_dir():
        for child in settings.storage_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        print(f"Cleared local files in {settings.storage_dir}/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stats", help="show database size and row counts")
    reset_parser = commands.add_parser("reset", help="delete all app data (keeps the tables)")
    reset_parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()
    if args.command == "stats":
        stats()
        return 0
    return reset(args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
