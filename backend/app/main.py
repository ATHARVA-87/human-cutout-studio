"""FastAPI application: API routes (including owner-only images under /api/media) and the built React app (/)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api import auth, compositions, health, media, predictions
from backend.app.core.config import settings
from backend.app.core.middleware import request_context
from backend.app.db.session import run_migrations
from backend.app.services.inference import SegmentationService
from backend.app.services.retention import cleanup_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)  # keep "Running upgrade ..." lines, drop setup noise
logger = logging.getLogger("human_cutout.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: migrate the database schema, load the model, start the data-retention job."""
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_migrations()  # alembic upgrade head
        app.state.database_error = None
    except Exception as error:  # unreachable database or a failed migration
        # Keep starting so /api/health can report the problem (with 503) instead of the server crashing.
        app.state.database_error = str(error).splitlines()[0]
        logger.error("startup: database not ready: %s", app.state.database_error)
    try:
        service = SegmentationService(settings.model_path, threads=settings.model_threads)
        service.load()
        app.state.segmentation, app.state.model_error = service, None
    except Exception as error:  # missing or corrupt model.onnx: start anyway and report it in /api/health
        app.state.segmentation, app.state.model_error = None, str(error)
        logger.error("startup: model not ready: %s", app.state.model_error)

    cleanup = asyncio.create_task(cleanup_forever())  # deletes data older than the retention period
    yield
    cleanup.cancel()  # server shutting down
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup


app = FastAPI(title="Human Cutout API", version="1.0.0", lifespan=lifespan)
app.middleware("http")(request_context)  # request ID, access log, security headers
for module in (health, auth, predictions, compositions, media):
    app.include_router(module.router, prefix="/api")

# In Docker/production the React app is built into frontend/dist and served from the same origin,
# so the session cookie just works and no CORS setup is needed. In development Vite serves it instead.
if settings.frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
