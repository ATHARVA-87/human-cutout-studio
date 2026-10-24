"""Composition routes: cut the person out of one photo and prepare it for placing on another;
list, reopen and delete past compositions; save where the person was placed in the editor."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.api.deps import get_owned, model_or_503
from backend.app.db.models import Composition, CompositionPlacement, User
from backend.app.db.session import get_session
from backend.app.schemas import CompositionListResponse, CompositionResponse, Placement
from backend.app.services.auth import current_user
from backend.app.services.jobs import COMPOSE_COST, run_paid_job
from backend.app.services.realism import crop_to_person, match_colors, touches_bottom
from backend.app.services.retention import expiry_of
from backend.app.services.storage import LocalStorage, delete_job_folder, media_url, read_image

router = APIRouter(prefix="/compositions", tags=["compositions"])


def to_response(composition: Composition, placement: CompositionPlacement | None = None, credits: int | None = None) -> CompositionResponse:
    return CompositionResponse(
        id=composition.id,
        created_at=composition.created_at,
        expires_at=expiry_of(composition.created_at),
        background_url=media_url(composition.background_path),
        cutout_url=media_url(composition.cutout_path),
        anchor_bottom=composition.anchor_bottom,
        placement=Placement(x=placement.x, bottom=placement.bottom, height=placement.height, mirrored=placement.mirrored) if placement else None,
        credits=credits,
    )


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
    session.refresh(composition)  # load created_at, which the database fills in
    return to_response(composition, credits=user.credits)


@router.get("", response_model=CompositionListResponse)
def list_compositions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> CompositionListResponse:
    # One query with a LEFT JOIN brings each composition together with its saved placement (or NULL),
    # instead of one extra query per item (the "N+1 queries" problem).
    rows = session.execute(
        select(Composition, CompositionPlacement)
        .outerjoin(CompositionPlacement, CompositionPlacement.composition_id == Composition.id)
        .where(Composition.user_id == user.id)
        .order_by(Composition.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(Composition).where(Composition.user_id == user.id)) or 0
    return CompositionListResponse(items=[to_response(composition, placement) for composition, placement in rows], total=total)


@router.get("/{composition_id}", response_model=CompositionResponse)
def get_composition(composition_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> CompositionResponse:
    composition = get_owned(session, Composition, composition_id, user)
    return to_response(composition, session.get(CompositionPlacement, composition.id))


@router.put("/{composition_id}/placement", status_code=status.HTTP_204_NO_CONTENT)
def save_placement(
    composition_id: UUID, body: Placement, session: Session = Depends(get_session), user: User = Depends(current_user)
) -> None:
    """Save where the person is in the editor (the browser calls this automatically while you edit).

    PUT is idempotent: sending the same placement twice gives the same result. The upsert
    (INSERT ... ON CONFLICT DO UPDATE) creates the row the first time and updates it afterwards.
    """
    composition = get_owned(session, Composition, composition_id, user)
    values = body.model_dump()
    statement = insert(CompositionPlacement).values(composition_id=composition.id, **values)
    statement = statement.on_conflict_do_update(index_elements=[CompositionPlacement.composition_id], set_={**values, "updated_at": func.now()})
    session.execute(statement)
    session.commit()


@router.delete("/{composition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_composition(composition_id: UUID, session: Session = Depends(get_session), user: User = Depends(current_user)) -> None:
    composition = get_owned(session, Composition, composition_id, user)
    files = composition.cutout_path
    session.delete(composition)  # the saved placement goes too (ON DELETE CASCADE)
    session.commit()
    delete_job_folder(files)  # only after the commit: never delete files of a row that still exists
