from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.models import Prediction
from backend.app.db.session import get_session
from backend.app.schemas.predictions import PredictionListResponse, PredictionResponse
from backend.app.services.rate_limit import enforce_rate_limit
from backend.app.services.storage import LocalStorage
from backend.app.services.auth import current_user
from backend.app.services.credits import charge
from backend.app.db.models import User

router = APIRouter(prefix="/predictions", tags=["predictions"])


def as_response(prediction: Prediction) -> PredictionResponse:
    root = settings.storage_dir.resolve()

    def url(path: str) -> str:
        return "/media/" + str(Path(path).resolve().relative_to(root)).replace("\\", "/")

    return PredictionResponse(
        id=prediction.id,
        created_at=prediction.created_at,
        operation=prediction.operation,
        original_filename=prediction.original_filename,
        source_width=prediction.source_width,
        source_height=prediction.source_height,
        foreground_fraction=prediction.foreground_fraction,
        model_version=prediction.model_version,
        original_url=url(prediction.original_path),
        mask_url=url(prediction.mask_path),
        overlay_url=url(prediction.overlay_path),
        cutout_url=url(prediction.cutout_path) if prediction.cutout_path else None,
    )


@router.post("", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
async def create_prediction(
    request: Request,
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PredictionResponse:
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image.")
    contents = await image.read()
    if not contents or len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Image must be between 1 byte and {settings.max_upload_bytes} bytes.")
    try:
        source = LocalStorage.decode(contents)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="The uploaded file is not a valid image.") from error
    service = getattr(request.app.state, "segmentation", None)
    if service is None:
        raise HTTPException(status_code=503, detail="The trained model is not ready for inference.")
    client_host = request.client.host if request.client else "unknown"
    enforce_rate_limit(session, client_host, "segment_person")
    charge(session, user, 1, "person_segmentation")
    result = service.predict(source)
    artifacts = LocalStorage().save(source, result.mask, result.cutout, result.overlay)
    prediction = Prediction(
        operation="segment_person",
        original_filename=image.filename or "upload",
        source_width=source.width,
        source_height=source.height,
        foreground_fraction=result.foreground_fraction,
        model_version=result.model_version,
        original_path=artifacts.original_path,
        mask_path=artifacts.mask_path,
        overlay_path=artifacts.overlay_path,
        cutout_path=artifacts.cutout_path, user_id=user.id,
    )
    session.add(prediction)
    session.commit()
    session.refresh(prediction)
    return as_response(prediction)


@router.get("", response_model=PredictionListResponse)
def list_predictions(limit: int = 20, offset: int = 0, session: Session = Depends(get_session), user: User = Depends(current_user)) -> PredictionListResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1–100 and offset must be non-negative.")
    items = session.scalars(select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.created_at.desc()).offset(offset).limit(limit)).all()
    total = session.scalar(select(func.count()).select_from(Prediction).where(Prediction.user_id == user.id)) or 0
    return PredictionListResponse(items=[as_response(item) for item in items], total=total)


@router.get("/{prediction_id}", response_model=PredictionResponse)
def get_prediction(prediction_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> PredictionResponse:
    prediction = session.get(Prediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return as_response(prediction)
