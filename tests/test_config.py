from backend.app.core.config import Settings


def test_settings_read_from_arguments_and_defaults() -> None:
    settings = Settings(_env_file=None, bucket_capacity=7, cookie_secure=True)
    assert settings.bucket_capacity == 7
    assert settings.cookie_secure is True
    assert settings.bucket_period_seconds == 1800


def test_environment_variable_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv("SEGMENTATION_BUCKET_CAPACITY", "3")
    assert Settings(_env_file=None).bucket_capacity == 3
