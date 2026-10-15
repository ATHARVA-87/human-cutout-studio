from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.db.models import Composition, User
from backend.app.db.session import get_session
from backend.app.services.auth import current_user
from backend.app.services.credits import charge
from backend.app.services.rate_limit import enforce_rate_limit
from backend.app.services.storage import LocalStorage

router = APIRouter(prefix="/compositions", tags=["compositions"])
class CompositionResponse(BaseModel): id: str; background_url: str; cutout_url: str; credits: int
def media(path: str) -> str: return "/media/" + str(Path(path).resolve().relative_to(settings.storage_dir.resolve())).replace("\\", "/")
async def image(upload: UploadFile) -> object:
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp"}: raise HTTPException(415, "Upload a JPEG, PNG, or WebP image.")
    contents = await upload.read()
    if not contents or len(contents) > settings.max_upload_bytes: raise HTTPException(413, "Image is too large.")
    try: return LocalStorage.decode(contents)
    except ValueError as error: raise HTTPException(422, "The uploaded file is not a valid image.") from error
@router.post("", response_model=CompositionResponse, status_code=201)
async def create_composition(request: Request, person_image: UploadFile = File(...), background_image: UploadFile = File(...), session: Session = Depends(get_session), user: User = Depends(current_user)) -> CompositionResponse:
    person, background = await image(person_image), await image(background_image)
    service = getattr(request.app.state, "segmentation", None)
    if service is None: raise HTTPException(503, "Image processing is temporarily unavailable.")
    enforce_rate_limit(session, request.client.host if request.client else "unknown", "compose_person")
    charge(session, user, 2, "background_composition")
    result = service.predict(person)
    background_path, cutout_path = LocalStorage().save_composition_inputs(background, result.cutout)
    composition = Composition(user_id=user.id, background_path=background_path, cutout_path=cutout_path); session.add(composition); session.commit(); session.refresh(composition)
    return CompositionResponse(id=str(composition.id), background_url=media(background_path), cutout_url=media(cutout_path), credits=user.credits)
