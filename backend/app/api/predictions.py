"""Person segmentation routes: create a cutout, list your history, open one result, delete one."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_owned, model_or_503
from backend.app.db.models import Prediction, User
from backend.app.db.session import get_session
from backend.app.schemas import PredictionListResponse, PredictionResponse
from backend.app.services.auth import current_user
from backend.app.services.jobs import SEGMENT_COST, run_paid_job
from backend.app.services.retention import expiry_of
from backend.app.services.storage import LocalStorage, delete_job_folder, media_url, read_image

router = APIRouter(prefix="/predictions", tags=["predictions"])


def to_response(prediction: Prediction, credits: int | None = None) -> PredictionResponse:
    return PredictionResponse(
        id=prediction.id,
        created_at=prediction.created_at,
        expires_at=expiry_of(prediction.created_at),
        original_filename=prediction.original_filename,
        source_width=prediction.source_width,
        source_height=prediction.source_height,
        foreground_fraction=prediction.foreground_fraction,
        model_version=prediction.model_version,
        original_url=media_url(prediction.original_path),
        mask_url=media_url(prediction.mask_path),
        overlay_url=media_url(prediction.overlay_path),
        cutout_url=media_url(prediction.cutout_path),
        credits=credits,
    )


@router.post("", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
async def create_prediction(
    request: Request,
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PredictionResponse:
    # Validate everything that is free to check BEFORE spending a token or credits.
    source = await read_image(image)
    service = model_or_503(request)

    def work():
        result = service.predict(source)
        return result, LocalStorage().save_prediction(source, result.mask, result.cutout, result.overlay)

    result, files = await run_paid_job(session, user, SEGMENT_COST, "person_segmentation", work)
    prediction = Prediction(
        user_id=user.id,
        original_filename=(image.filename or "upload")[:255],
        source_width=source.width,
        source_height=source.height,
        foreground_fraction=result.foreground_fraction,
        model_version=result.model_version,
        original_path=files.original_path,
        mask_path=files.mask_path,
        overlay_path=files.overlay_path,
        cutout_path=files.cutout_path,
    )
    session.add(prediction)
    session.commit()
    session.refresh(prediction)  # load created_at, which the database fills in
    return to_response(prediction, credits=user.credits)


@router.get("", response_model=PredictionListResponse)
def list_predictions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PredictionListResponse:
    """Newest first, one page at a time (offset pagination). Uses the (user_id, created_at) index."""
    items = session.scalars(
        select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.created_at.desc()).offset(offset).limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(Prediction).where(Prediction.user_id == user.id)) or 0
    return PredictionListResponse(items=[to_response(item) for item in items], total=total)


@router.get("/{prediction_id}", response_model=PredictionResponse)
def get_prediction(prediction_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> PredictionResponse:
    return to_response(get_owned(session, Prediction, prediction_id, user))


@router.delete("/{prediction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prediction(prediction_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> None:
    prediction = get_owned(session, Prediction, prediction_id, user)
    files = prediction.original_path
    session.delete(prediction)
    session.commit()
    delete_job_folder(files)  # only after the commit: never delete files of a row that still exists
