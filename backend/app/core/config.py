from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings read from environment variables (prefix SEGMENTATION_) or a local .env file.

    A real environment variable always wins over the .env file, which is how production
    (Render) and the owner-only admin script point the app at a different database.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEGMENTATION_", extra="ignore")

    database_url: str = "postgresql+psycopg://segmentation:segmentation@localhost:5432/segmentation"
    # The exported network (scripts/export_onnx.py). Training uses model.pth; the server only needs this.
    model_path: Path = Path("backend/weights/model.onnx")
    storage_dir: Path = Path("uploads")
    frontend_dist: Path = Path("frontend/dist")
    max_upload_bytes: int = 10 * 1024 * 1024
    # Uploads are processed at most this many pixels on the longest side (keeps memory under 512 MB).
    max_image_side: int = 1600
    # Browsers only send a Secure cookie over HTTPS, so this is True in production and False locally.
    cookie_secure: bool = False
    # Token bucket: each user may start `bucket_capacity` jobs, refilled evenly over `bucket_period_seconds`.
    bucket_capacity: int = 10
    bucket_period_seconds: int = 30 * 60
    # CPU threads for the model. One keeps memory low and matches the free tier's 0.1 CPU.
    model_threads: int = 1
    # Data retention: uploads, results and their history rows are deleted after this many days.
    retention_days: int = 5
    # How often the cleanup job runs while the server is awake (it also runs at every startup).
    cleanup_interval_minutes: int = 60
    # Brute-force protection: this many failed logins for one email within the window -> HTTP 429.
    login_max_failures: int = 5
    login_window_minutes: int = 15
    # Per-IP abuse limits: new accounts per IP per day, and failed logins per IP per login window
    # (stops one person creating many free accounts, or trying one password against many emails).
    registrations_per_ip_per_day: int = 3
    login_failures_per_ip: int = 20
    # Secret mixed into IP hashes so stored hashes can't be reversed by hashing every possible IP.
    ip_hash_salt: str = "local-development-only"

    # The site's own address, used to build links in emails. It is configured, never taken from the
    # request's Host header (an attacker could fake that header and receive someone's reset link).
    # On Render, RENDER_EXTERNAL_URL (set automatically, e.g. https://human-cutout.onrender.com) is used.
    public_url: str = Field(
        default="http://localhost:8000", validation_alias=AliasChoices("SEGMENTATION_PUBLIC_URL", "RENDER_EXTERNAL_URL")
    )
    # How emails are sent: "console" (written to the log; tests and fallback), "smtp" (e.g. the local
    # Mailpit inbox), or "brevo" (Brevo's HTTPS API; Render's free plan blocks SMTP ports).
    email_backend: str = "console"
    email_from: str = "no-reply@example.com"  # with Brevo: a sender address you verified in Brevo
    email_from_name: str = "Human Cutout"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    brevo_api_key: str = ""
    # Guest mode ("Try it without an account"): temporary, already-confirmed accounts without an email.
    guest_credits: int = 10
    guest_hours: int = 24  # deleted by the cleanup job after this long (or right away when they log out)
    guests_per_ip_per_day: int = 5
    # Lifetimes of the links sent by email
    verify_token_hours: int = 24
    reset_token_minutes: int = 30


settings = Settings()
