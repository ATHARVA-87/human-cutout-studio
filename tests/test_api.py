"""End-to-end API tests against a real PostgreSQL database (`segmentation_test`) with a fake model.

Skipped automatically when PostgreSQL is not running (start it with `docker compose up db -d`).
"""

from __future__ import annotations

import io
import os
import uuid

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.core.config import settings


def ensure_test_database() -> bool:
    """Create the test database if needed. Returns False when PostgreSQL is unreachable."""
    url = make_url(settings.database_url)
    try:
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database})
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
        admin.dispose()
        return True
    except Exception:
        return False


if not ensure_test_database():
    message = "PostgreSQL is not reachable; start it with `docker compose up db -d`."
    if os.environ.get("CI"):  # GitHub Actions sets CI=true: there, a missing database is an error, not a skip
        raise RuntimeError(message)
    pytest.skip(message, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.db.models import RateLimitBucket, User  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.services.inference import SegmentationResult  # noqa: E402


class FakeSegmentation:
    """Pretends the bottom-centre of every image is a person. Lets tests run without model weights."""

    fail = False

    def predict(self, image: Image.Image) -> SegmentationResult:
        if self.fail:
            raise RuntimeError("simulated model crash")
        width, height = image.size
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rectangle((width // 3, height // 4, 2 * width // 3, height), fill=255)
        cutout = image.convert("RGB")
        cutout.putalpha(mask)
        return SegmentationResult(mask, cutout, image.copy(), 0.25, "fake-model")


def image_file(format_name: str = "PNG", name: str = "photo.png", content_type: str = "image/png"):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 140, 90)).save(buffer, format=format_name)
    return (name, buffer.getvalue(), content_type)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:  # `with` runs the startup code (creates tables)
        app.state.segmentation = FakeSegmentation()
        yield test_client


def new_user(client: TestClient) -> tuple[TestClient, str]:
    """Register a fresh user on its own cookie jar (a separate 'browser')."""
    browser = TestClient(app)
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = browser.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert response.status_code == 201, response.text
    return browser, email


def set_user(email: str, **values) -> None:
    with SessionLocal() as session:
        user = session.query(User).filter_by(email=email).one()
        for key, value in values.items():
            setattr(user, key, value)
        session.commit()


def bucket_tokens(email: str) -> float:
    with SessionLocal() as session:
        user = session.query(User).filter_by(email=email).one()
        return session.get(RateLimitBucket, user.id).tokens


def test_register_gives_welcome_credits_and_duplicate_is_rejected(client) -> None:
    browser, email = new_user(client)
    assert browser.get("/api/auth/me").json() == {"email": email, "credits": 30}
    assert bucket_tokens(email) == 10
    duplicate = TestClient(app).post("/api/auth/register", json={"email": email.upper(), "password": "password123"})
    assert duplicate.status_code == 409


def test_short_password_returns_readable_validation_error(client) -> None:
    response = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert response.status_code == 422


def test_second_login_signs_out_the_first_browser(client) -> None:
    first, email = new_user(client)
    second = TestClient(app)
    assert second.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    assert second.get("/api/auth/me").status_code == 200
    assert first.get("/api/auth/me").status_code == 401


def test_wrong_password_is_rejected(client) -> None:
    _, email = new_user(client)
    response = TestClient(app).post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert response.status_code == 401


def test_logout_ends_the_session(client) -> None:
    browser, _ = new_user(client)
    assert browser.post("/api/auth/logout").status_code == 204
    assert browser.get("/api/auth/me").status_code == 401
    assert browser.post("/api/auth/logout").status_code == 204  # safe to repeat


def test_segmentation_charges_one_credit_and_appears_in_history(client) -> None:
    browser, _ = new_user(client)
    response = browser.post("/api/predictions", files={"image": image_file()})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["credits"] == 29
    assert browser.get(body["cutout_url"]).status_code == 200
    history = browser.get("/api/predictions").json()
    assert history["total"] == 1 and history["items"][0]["id"] == body["id"]


def test_other_users_cannot_read_my_prediction(client) -> None:
    owner, _ = new_user(client)
    prediction_id = owner.post("/api/predictions", files={"image": image_file()}).json()["id"]
    stranger, _ = new_user(client)
    assert stranger.get(f"/api/predictions/{prediction_id}").status_code == 404


def test_only_jpg_and_png_are_accepted(client) -> None:
    browser, _ = new_user(client)
    response = browser.post("/api/predictions", files={"image": image_file("WEBP", "photo.webp", "image/webp")})
    assert response.status_code == 415
    disguised = browser.post("/api/predictions", files={"image": image_file("WEBP", "photo.png", "image/png")})
    assert disguised.status_code == 415  # the real file format is checked, not just the declared type
    assert browser.get("/api/auth/me").json()["credits"] == 30


def test_too_large_upload_is_rejected_before_charging(client, monkeypatch) -> None:
    browser, _ = new_user(client)
    monkeypatch.setattr(settings, "max_upload_bytes", 100)  # anything bigger than 100 bytes is "too large"
    assert browser.post("/api/predictions", files={"image": image_file()}).status_code == 413
    assert browser.get("/api/auth/me").json()["credits"] == 30


def test_health_reports_ok_with_status_200_and_503_when_degraded(client) -> None:
    app.state.model_error = None
    assert client.get("/api/health").status_code == 200
    app.state.model_error = "model missing"
    try:
        response = client.get("/api/health")
    finally:
        app.state.model_error = None
    assert response.status_code == 503 and response.json()["status"] == "degraded"


def test_rate_limit_allows_ten_jobs_then_returns_429(client) -> None:
    browser, _ = new_user(client)
    for _ in range(10):
        assert browser.post("/api/predictions", files={"image": image_file()}).status_code == 201
    blocked = browser.post("/api/predictions", files={"image": image_file()})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert browser.get("/api/auth/me").json()["credits"] == 20  # the blocked request cost nothing


def test_no_credits_returns_402_without_using_a_token_and_recharge_works(client) -> None:
    browser, email = new_user(client)
    assert browser.post("/api/auth/recharge").status_code == 400  # still has 30 credits
    set_user(email, credits=0)
    assert browser.post("/api/predictions", files={"image": image_file()}).status_code == 402
    assert bucket_tokens(email) == 10
    recharged = browser.post("/api/auth/recharge")
    assert recharged.status_code == 200 and recharged.json()["credits"] == 30


def test_composition_costs_two_credits_and_detects_half_body(client) -> None:
    browser, _ = new_user(client)
    response = browser.post(
        "/api/compositions",
        files={"person_image": image_file(), "background_image": image_file("JPEG", "bg.jpg", "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["credits"] == 28
    assert body["anchor_bottom"] is True  # the fake person reaches the bottom edge
    cutout = Image.open(io.BytesIO(browser.get(body["cutout_url"]).content))
    assert cutout.mode == "RGBA" and cutout.size[1] < 48  # cropped to the person


def test_failed_job_refunds_credits(client) -> None:
    browser, _ = new_user(client)
    app.state.segmentation.fail = True
    try:
        response = browser.post("/api/predictions", files={"image": image_file()})
    finally:
        app.state.segmentation.fail = False
    assert response.status_code == 500
    assert browser.get("/api/auth/me").json()["credits"] == 30
