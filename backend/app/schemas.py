"""Shapes of JSON request and response bodies (validated by Pydantic)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class Account(BaseModel):
    email: str
    credits: int
    email_verified: bool  # jobs are allowed only after the email link was clicked
    is_guest: bool  # temporary account from "Try it without an account"
    retention_days: int  # how long uploads and results are kept (shown in the UI)
    guest_hours: int  # how long guest accounts last


class EmailOnly(BaseModel):
    email: EmailStr


class TokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)  # the random token from an email link


class NewPassword(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class PredictionResponse(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime  # when the retention job deletes it
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


class Placement(BaseModel):
    """Editor position as fractions of the background image. The ranges match the editor's limits."""

    x: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=2)  # the feet may go below the bottom edge (part of the person hidden)
    height: float = Field(ge=0.01, le=2)
    mirrored: bool = False


class CompositionResponse(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    background_url: str
    cutout_url: str
    anchor_bottom: bool
    placement: Placement | None = None  # where the user left the person last time (None = never edited)
    credits: int | None = None  # balance after this job (only on create)


class CompositionListResponse(BaseModel):
    items: list[CompositionResponse]
    total: int
