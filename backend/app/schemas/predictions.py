from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PredictionResponse(BaseModel):
    id: UUID
    created_at: datetime
    operation: str
    original_filename: str
    source_width: int
    source_height: int
    foreground_fraction: float
    model_version: str
    original_url: str
    mask_url: str
    overlay_url: str
    cutout_url: str | None = None


class PredictionListResponse(BaseModel):
    items: list[PredictionResponse]
    total: int
