"""Deleting accounts and everything that belongs to them (used by "Delete account", guest logout and cleanup)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.db.models import Composition, Prediction, User
from backend.app.db.session import rows_affected
from backend.app.services.storage import delete_job_folder


def folders_of(session: Session, user_ids: list[UUID]) -> list[str]:
    """One stored file path per job of these users (each job's files live in its own uploads/<uuid>/ folder)."""
    paths = list(session.scalars(select(Prediction.original_path).where(Prediction.user_id.in_(user_ids))))
    paths += list(session.scalars(select(Composition.cutout_path).where(Composition.user_id.in_(user_ids))))
    return paths


def delete_users(session: Session, user_ids: list[UUID]) -> int:
    """Delete accounts with ONE statement: every foreign key to users is ON DELETE CASCADE, so PostgreSQL also
    removes their sessions, ledger, rate-limit bucket, history and email links in the same transaction.
    Commits, then removes the image folders (files only after the rows are really gone)."""
    if not user_ids:
        return 0
    folders = folders_of(session, user_ids)
    deleted = rows_affected(session.execute(delete(User).where(User.id.in_(user_ids))))
    session.commit()
    for path in folders:
        delete_job_folder(path)
    return deleted
