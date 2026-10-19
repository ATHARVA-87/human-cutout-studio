from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, response: Response) -> dict[str, str]:
    """Used by Render (and you) to check that the model and database loaded at startup.

    Render looks only at the HTTP status code, so a broken deploy must answer 503, not 200.
    Otherwise a deploy with a wrong database URL would replace the working version.
    """
    model_error = getattr(request.app.state, "model_error", None)
    database_error = getattr(request.app.state, "database_error", None)
    healthy = model_error is None and database_error is None
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "model": "ready" if model_error is None else str(model_error),
        "database": "ready" if database_error is None else str(database_error),
    }
