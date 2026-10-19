from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings read from environment variables (prefix SEGMENTATION_) or a local .env file.

    A real environment variable always wins over the .env file, which is how production
    (Render) and the owner-only admin script point the app at a different database.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEGMENTATION_", extra="ignore")

    database_url: str = "postgresql+psycopg://segmentation:segmentation@localhost:5432/segmentation"
    checkpoint_path: Path = Path("backend/weights/model.pth")
    storage_dir: Path = Path("uploads")
    frontend_dist: Path = Path("frontend/dist")
    max_upload_bytes: int = 10 * 1024 * 1024
    # Browsers only send a Secure cookie over HTTPS, so this is True in production and False locally.
    cookie_secure: bool = False
    # Token bucket: each user may start `bucket_capacity` jobs, refilled evenly over `bucket_period_seconds`.
    bucket_capacity: int = 10
    bucket_period_seconds: int = 30 * 60
    # One CPU thread keeps memory low on the free hosting tier.
    torch_threads: int = 1


settings = Settings()
