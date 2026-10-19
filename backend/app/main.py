"""FastAPI application: API routes, generated images (/media) and the built React app (/)."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

# Lets `uvicorn backend.app.main:app` import the `segmentation` package from src/ without installing it.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.app.api import auth, compositions, health, predictions  # noqa: E402
from backend.app.core.config import settings  # noqa: E402
from backend.app.db.session import create_tables  # noqa: E402
from backend.app.services.inference import SegmentationService  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: create tables and load the model into memory."""
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        create_tables()
        app.state.database_error = None
    except SQLAlchemyError as error:
        # Keep starting so /api/health can report the problem instead of the server crashing.
        app.state.database_error = str(error).splitlines()[0]
    try:
        service = SegmentationService(settings.checkpoint_path, threads=settings.torch_threads)
        service.load()
        app.state.segmentation, app.state.model_error = service, None
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        app.state.segmentation, app.state.model_error = None, str(error)
    yield


app = FastAPI(title="Human Cutout API", version="1.0.0", lifespan=lifespan)
for module in (health, auth, predictions, compositions):
    app.include_router(module.router, prefix="/api")
app.mount("/media", StaticFiles(directory=settings.storage_dir, check_dir=False), name="media")

# In Docker/production the React app is built into frontend/dist and served from the same origin,
# so the session cookie just works and no CORS setup is needed. In development Vite serves it instead.
if settings.frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
