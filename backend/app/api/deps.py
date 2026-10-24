"""Small helpers shared by the route modules."""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.db.models import Composition, Prediction, User
from backend.app.services.inference import SegmentationService

Owned = TypeVar("Owned", Prediction, Composition)


def model_or_503(request: Request) -> SegmentationService:
    service = getattr(request.app.state, "segmentation", None)
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The model is not loaded yet. Try again shortly.")
    return service


def get_owned(session: Session, model: type[Owned], item_id: UUID, user: User) -> Owned:
    """Fetch a row that must belong to `user`.

    Someone else's item gets the same 404 as a missing one, so IDs of other people's work are never confirmed.
    """
    item = session.get(model, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return item
