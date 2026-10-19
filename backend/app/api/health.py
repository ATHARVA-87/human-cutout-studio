from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    """Used by the hosting platform (and you) to check that the model and database are ready."""
    model_error = getattr(request.app.state, "model_error", None)
    database_error = getattr(request.app.state, "database_error", None)
    return {
        "status": "ok" if model_error is None and database_error is None else "degraded",
        "model": "ready" if model_error is None else str(model_error),
        "database": "ready" if database_error is None else str(database_error),
    }
