"""Shapes of JSON request and response bodies (validated by Pydantic)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Account(BaseModel):
    email: str
    credits: int


class PredictionResponse(BaseModel):
    id: UUID
    created_at: datetime
    original_filename: str
    source_width: int
    source_height: int
    foreground_fraction: float
    model_version: str
    original_url: str
    mask_url: str
    overlay_url: str
    cutout_url: str
    credits: int | None = None  # balance after this job (only on create)


class PredictionListResponse(BaseModel):
    items: list[PredictionResponse]
    total: int


class CompositionResponse(BaseModel):
    id: UUID
    background_url: str
    cutout_url: str
    anchor_bottom: bool
    credits: int
