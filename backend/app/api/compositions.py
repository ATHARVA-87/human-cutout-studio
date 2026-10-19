"""Composition route: cut the person out of one photo and prepare it for placing on another."""

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.predictions import model_or_503
from backend.app.db.models import Composition, User
from backend.app.db.session import get_session
from backend.app.schemas import CompositionResponse
from backend.app.services.auth import current_user
from backend.app.services.jobs import COMPOSE_COST, run_paid_job
from backend.app.services.realism import crop_to_person, match_colors, touches_bottom
from backend.app.services.storage import LocalStorage, media_url, read_image

router = APIRouter(prefix="/compositions", tags=["compositions"])


@router.post("", response_model=CompositionResponse, status_code=status.HTTP_201_CREATED)
async def create_composition(
    request: Request,
    person_image: UploadFile = File(...),
    background_image: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> CompositionResponse:
    person, background = await read_image(person_image), await read_image(background_image)
    service = model_or_503(request)

    def work():
        cutout = service.predict(person).cutout
        anchor_bottom = touches_bottom(cutout)  # check before cropping: needs the original frame
        cutout = match_colors(crop_to_person(cutout), background)
        return anchor_bottom, LocalStorage().save_composition(background, cutout)

    anchor_bottom, (background_path, cutout_path) = await run_paid_job(session, user, COMPOSE_COST, "background_composition", work)
    composition = Composition(user_id=user.id, background_path=background_path, cutout_path=cutout_path, anchor_bottom=anchor_bottom)
    session.add(composition)
    session.commit()
    return CompositionResponse(
        id=composition.id,
        background_url=media_url(background_path),
        cutout_url=media_url(cutout_path),
        anchor_bottom=anchor_bottom,
        credits=user.credits,
    )
