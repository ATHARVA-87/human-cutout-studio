"""Private image delivery: only the signed-in owner can load their images.

Before, generated images were public files under /media/<random folder>/: anyone with the exact link
could open them. Now every image request goes through here, which (1) requires the session cookie and
(2) checks that the item belongs to the caller. Anyone else gets 404, even with the exact link.

The URL names the item by its id and the file by a fixed name (no file paths come from the user, so
path tricks like ../ are impossible). On AWS the same check would happen before handing out a
short-lived S3 "presigned" URL.
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_owned
from backend.app.db.models import Composition, Prediction, User
from backend.app.db.session import get_session
from backend.app.services.auth import current_user

router = APIRouter(prefix="/media", tags=["media"])

PREDICTION_FILES = {"original": "original_path", "mask": "mask_path", "overlay": "overlay_path", "cutout": "cutout_path"}
COMPOSITION_FILES = {"background": "background_path", "cutout": "cutout_path"}


def private_file(path: str) -> FileResponse:
    if not Path(path).is_file():  # deleted by the cleanup job, or the free server's disk was wiped
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This image is no longer on the server.")
    # "private": browsers may cache it, but shared caches (proxies, CDNs) must not.
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/predictions/{item_id}/{file}")
def prediction_file(item_id: UUID, file: str, session: Session = Depends(get_session), user: User = Depends(current_user)) -> FileResponse:
    if file not in PREDICTION_FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return private_file(getattr(get_owned(session, Prediction, item_id, user), PREDICTION_FILES[file]))


@router.get("/compositions/{item_id}/{file}")
def composition_file(item_id: UUID, file: str, session: Session = Depends(get_session), user: User = Depends(current_user)) -> FileResponse:
    if file not in COMPOSITION_FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return private_file(getattr(get_owned(session, Composition, item_id, user), COMPOSITION_FILES[file]))
