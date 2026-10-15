from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.app.api import auth, compositions, health, predictions
from backend.app.core.config import settings
from backend.app.db.session import migrate_schema
from backend.app.services.inference import SegmentationService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        migrate_schema()
        app.state.database_error = None
    except SQLAlchemyError as error:
        # Keep health diagnostics available when a local database has not started yet.
        app.state.database_error = str(error)
    try:
        service = SegmentationService(settings.checkpoint_path)
        service.load()
        app.state.segmentation = service
        app.state.model_error = None
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        app.state.segmentation = None
        app.state.model_error = str(error)
    yield


app = FastAPI(title="Human Segmentation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=settings.storage_dir, check_dir=False), name="media")
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(compositions.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
