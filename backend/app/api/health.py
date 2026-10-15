from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    model_error = getattr(request.app.state, "model_error", None)
    database_error = getattr(request.app.state, "database_error", None)
    return {
        "status": "ok" if model_error is None and database_error is None else "degraded",
        "model": "ready" if model_error is None else str(model_error),
        "database": "ready" if database_error is None else str(database_error),
    }


@router.get("/capabilities")
def capabilities(request: Request) -> dict[str, list[dict[str, str]]]:
    """Advertise only enabled operations; future editing operations add entries here."""
    ready = getattr(request.app.state, "segmentation", None) is not None
    return {"operations": [{"id": "segment_person", "status": "ready" if ready else "unavailable"}]}
