from backend.app.api.health import router
from backend.app.core.config import Settings


def test_environment_settings_parse_rate_limit_and_origins() -> None:
    settings = Settings(_env_file=None, requests_per_hour=7, cors_origins=["http://example.test"])
    assert settings.requests_per_hour == 7
    assert settings.cors_origins == ["http://example.test"]


def test_health_router_is_exposed() -> None:
    assert any(route.path == "/health" for route in router.routes)
