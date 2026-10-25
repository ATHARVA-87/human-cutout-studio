"""Database tables. Each class below is one PostgreSQL table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from .session import Base


class User(Base):
    __tablename__ = "users"
    # The database itself refuses a negative balance, even if application code has a bug.
    __table_args__ = (CheckConstraint("credits >= 0", name="credits_not_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # Set once the user clicks the link in the verification email. Until then they can sign in but not run jobs.
    # server_default=false fills the column for users who existed before it was added (see migration 0003).
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    # Temporary guest account (no real email or password); deleted on logout or after `guest_hours`.
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=expression.false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmailToken(Base):
    """A one-time link sent by email: verify the address, or reset the password.

    Only a SHA-256 hash of the token is stored (like session tokens), so a leaked database can't be used
    to verify or reset anything. Each token expires and can be used once (`used_at`).
    """

    __tablename__ = "email_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(10), nullable=False)  # "verify" or "reset"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionToken(Base):
    """The logged-in session. `user_id` is UNIQUE, so a user can have only one active session."""

    __tablename__ = "session_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditTransaction(Base):
    """Append-only ledger: every credit change is recorded, so balances can be audited."""

    __tablename__ = "credit_transactions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RateLimitBucket(Base):
    """Token bucket per user: how many jobs they may start right now, and when it was last updated."""

    __tablename__ = "rate_limit_buckets"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LoginAttempt(Base):
    """One row per FAILED login, used to stop password guessing. Stores a hash of the email, not the email."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_email_created", "email_hash", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IpEvent(Base):
    """Sign-ups and failed logins per client IP, for per-IP abuse limits. Stores a salted hash, not the IP."""

    __tablename__ = "ip_events"
    __table_args__ = (Index("ix_ip_events_ip_kind_created", "ip_hash", "kind", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "register" or "login_failure"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"
    # Matches the history query: WHERE user_id = ? ORDER BY created_at DESC.
    __table_args__ = (Index("ix_predictions_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_width: Mapped[int] = mapped_column(Integer, nullable=False)
    source_height: Mapped[int] = mapped_column(Integer, nullable=False)
    foreground_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    mask_path: Mapped[str] = mapped_column(Text, nullable=False)
    overlay_path: Mapped[str] = mapped_column(Text, nullable=False)
    cutout_path: Mapped[str] = mapped_column(Text, nullable=False)


class Composition(Base):
    __tablename__ = "compositions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    background_path: Mapped[str] = mapped_column(Text, nullable=False)
    cutout_path: Mapped[str] = mapped_column(Text, nullable=False)
    # True when the person was cut off at the bottom of the source photo (e.g. a half-body shot).
    anchor_bottom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CompositionPlacement(Base):
    """Where the user left the person in the editor, so "Edit again" continues from there.

    Stored as fractions of the background image (0-1), so the values don't depend on screen size.
    One row per composition (the composition id is the primary key); deleted with the composition.
    """

    __tablename__ = "composition_placements"
    composition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compositions.id", ondelete="CASCADE"), primary_key=True)
    x: Mapped[float] = mapped_column(Float, nullable=False)  # feet position, fraction of background width
    bottom: Mapped[float] = mapped_column(Float, nullable=False)  # feet position, fraction of background height
    height: Mapped[float] = mapped_column(Float, nullable=False)  # person height, fraction of background height
    mirrored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
