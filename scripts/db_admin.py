#!/usr/bin/env python3
"""Owner-only database tools: check how much space the database uses, or wipe all app data.

There is deliberately NO web endpoint for this. To run it you need the database connection
string (your local .env, or the Neon URL for production). Having that secret is the permission.

  python scripts/db_admin.py stats                     # local database from .env
  python scripts/db_admin.py reset                     # asks you to type the database name first
  python scripts/db_admin.py cleanup                   # run the retention job now (normally automatic)
  SEGMENTATION_DATABASE_URL='postgresql+psycopg://...' python scripts/db_admin.py stats   # production
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
# Work from the project folder, so .env and uploads/ mean the same thing wherever the script is started.
os.chdir(PROJECT_ROOT)

from sqlalchemy import inspect, text  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.db import models  # noqa: E402,F401  (registers the tables)
from backend.app.db.session import Base, engine  # noqa: E402
from backend.app.services.retention import run_cleanup  # noqa: E402


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


LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def local_uploads_folder() -> Path | None:
    """The uploads folder to empty, only for a local database and only if it is inside the project."""
    if engine.url.host not in LOCAL_HOSTS:
        return None  # production images live on the Render server, not on this computer
    folder = settings.storage_dir.resolve()
    if folder == PROJECT_ROOT or PROJECT_ROOT not in folder.parents:
        raise SystemExit(f"Refusing to empty {folder}: it must be a folder inside {PROJECT_ROOT}.")
    return folder


def reset(skip_confirmation: bool) -> int:
    target = engine.url
    folder = local_uploads_folder()
    print(f"Database: {target.render_as_string(hide_password=True)}")
    if folder:
        print(f"Files:    everything inside {folder}")
    if skip_confirmation and target.host not in LOCAL_HOSTS:
        raise SystemExit("--yes is only allowed for a local database. Type the confirmation for production.")
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
    if folder and folder.is_dir():
        for child in folder.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        print(f"Cleared local files in {folder}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stats", help="show database size and row counts")
    reset_parser = commands.add_parser("reset", help="delete all app data (keeps the tables)")
    reset_parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    commands.add_parser("cleanup", help=f"delete data older than {settings.retention_days} days now")
    args = parser.parse_args()
    if args.command == "stats":
        stats()
        return 0
    if args.command == "cleanup":
        print(f"Database: {engine.url.render_as_string(hide_password=True)}")
        report = run_cleanup()
        print(report if report else "Another cleanup is already running; nothing done.")
        return 0
    return reset(args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
