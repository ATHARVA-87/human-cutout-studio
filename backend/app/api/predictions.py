"""Person segmentation routes: create a cutout, list your past results, fetch one result."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import Prediction, User
from backend.app.db.session import get_session
from backend.app.schemas import PredictionListResponse, PredictionResponse
from backend.app.services.auth import current_user
from backend.app.services.inference import SegmentationService
from backend.app.services.jobs import SEGMENT_COST, run_paid_job
from backend.app.services.storage import LocalStorage, media_url, read_image

router = APIRouter(prefix="/predictions", tags=["predictions"])


def model_or_503(request: Request) -> SegmentationService:
    service = getattr(request.app.state, "segmentation", None)
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The model is not loaded yet. Try again shortly.")
    return service


def to_response(prediction: Prediction, credits: int | None = None) -> PredictionResponse:
    return PredictionResponse(
        id=prediction.id,
        created_at=prediction.created_at,
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
def list_predictions(limit: int = 20, offset: int = 0, session: Session = Depends(get_session), user: User = Depends(current_user)) -> PredictionListResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "limit must be 1-100 and offset must be 0 or more.")
    items = session.scalars(
        select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.created_at.desc()).offset(offset).limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(Prediction).where(Prediction.user_id == user.id)) or 0
    return PredictionListResponse(items=[to_response(item) for item in items], total=total)


@router.get("/{prediction_id}", response_model=PredictionResponse)
def get_prediction(prediction_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> PredictionResponse:
    prediction = session.get(Prediction, prediction_id)
    # 404 (not 403) for other users' results, so IDs of other people's work are not confirmed.
    if prediction is None or prediction.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prediction not found.")
    return to_response(prediction)
