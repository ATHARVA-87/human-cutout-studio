from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed runtime settings; no secrets belong in source control."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SEGMENTATION_", extra="ignore")

    database_url: str = "postgresql+psycopg://segmentation:segmentation@db:5432/segmentation"
    checkpoint_path: Path = Path("backend/weights/model.pth")
    storage_dir: Path = Path("uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    requests_per_hour: int = 5
    rate_limit_salt: str = "development-only-change-me"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
