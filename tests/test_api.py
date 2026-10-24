"""End-to-end API tests against a real PostgreSQL database (`segmentation_test`) with a fake model.

Skipped automatically when PostgreSQL is not running (start it with `docker compose up db -d`).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

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

from backend.app.db.models import (  # noqa: E402
    Composition,
    CompositionPlacement,
    CreditTransaction,
    EmailToken,
    IpEvent,
    LoginAttempt,
    Prediction,
    RateLimitBucket,
    User,
)
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.services.email import outbox  # noqa: E402
from backend.app.services.inference import SegmentationResult  # noqa: E402
from backend.app.services.retention import run_cleanup  # noqa: E402


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


def last_link(email: str, path: str) -> str:
    """The token from the newest email sent to `email` whose link goes to /#/<path>?token=..."""
    for message in reversed(outbox):
        if message.to == email and f"/#/{path}?token=" in message.text:
            return message.text.split(f"/#/{path}?token=")[1].split()[0]
    raise AssertionError(f"no {path} email for {email}")


def new_user(client: TestClient, verify: bool = True) -> tuple[TestClient, str]:
    """Register a fresh user on its own cookie jar (a separate 'browser'), confirming the email by default."""
    browser = TestClient(app)
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = browser.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert response.status_code == 201, response.text
    if verify:
        assert browser.post("/api/auth/verify-email", json={"token": last_link(email, "verify")}).status_code == 204
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
    assert browser.get("/api/auth/me").json() == {"email": email, "credits": 30, "email_verified": True, "retention_days": 5}
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


# ---------- history, deletion, account erasure, login limit, retention, headers ----------


def job_folder(media_url: str) -> Path:
    """/api/media/<collection>/<id>/<file> -> the uploads/<uuid> folder on disk that holds that job's files."""
    collection, item_id = media_url.split("/")[3:5]
    with SessionLocal() as session:
        if collection == "predictions":
            row = session.get(Prediction, uuid.UUID(item_id))
            assert row is not None
            return Path(row.original_path).parent
        composition = session.get(Composition, uuid.UUID(item_id))
        assert composition is not None
        return Path(composition.cutout_path).parent


def segment(browser: TestClient) -> dict:
    response = browser.post("/api/predictions", files={"image": image_file()})
    assert response.status_code == 201, response.text
    return response.json()


def test_history_pages_and_items_can_be_deleted(client) -> None:
    browser, _ = new_user(client)
    first, second = segment(browser), segment(browser)
    composition = browser.post("/api/compositions", files={"person_image": image_file(), "background_image": image_file()}).json()
    page = browser.get("/api/predictions?limit=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["items"][0]["id"] == second["id"]  # newest first
    assert browser.get("/api/predictions?limit=0").status_code == 422
    listed = browser.get("/api/compositions").json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == composition["id"]
    created = datetime.fromisoformat(listed["items"][0]["created_at"])
    assert datetime.fromisoformat(listed["items"][0]["expires_at"]) - created == timedelta(days=5)

    first_folder = job_folder(first["cutout_url"])
    assert browser.delete(f"/api/predictions/{first['id']}").status_code == 204
    assert not first_folder.exists()  # files are gone too
    assert browser.get(first["cutout_url"]).status_code == 404
    assert browser.get("/api/predictions").json()["total"] == 1
    assert browser.delete(f"/api/predictions/{first['id']}").status_code == 404
    assert browser.delete(f"/api/compositions/{composition['id']}").status_code == 204
    assert browser.get("/api/compositions").json()["total"] == 0


def test_cannot_delete_someone_elses_item(client) -> None:
    owner, _ = new_user(client)
    prediction = segment(owner)
    stranger, _ = new_user(client)
    assert stranger.delete(f"/api/predictions/{prediction['id']}").status_code == 404
    assert owner.get(f"/api/predictions/{prediction['id']}").status_code == 200


def test_login_is_blocked_after_five_failures(client) -> None:
    _, email = new_user(client)
    attacker = TestClient(app)
    for _ in range(5):
        assert attacker.post("/api/auth/login", json={"email": email, "password": "wrong-guess"}).status_code == 401
    blocked = attacker.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0  # even the right password waits
    with SessionLocal() as session:  # pretend 16 minutes have passed
        session.query(LoginAttempt).update({LoginAttempt.created_at: datetime.now(UTC) - timedelta(minutes=16)})
        session.commit()
    assert attacker.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200


def test_delete_account_erases_everything(client) -> None:
    browser, email = new_user(client)
    folder = job_folder(segment(browser)["cutout_url"])
    assert browser.request("DELETE", "/api/auth/account", json={"password": "wrong-password"}).status_code == 403
    assert browser.request("DELETE", "/api/auth/account", json={"password": "password123"}).status_code == 204
    assert browser.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    assert not folder.exists()
    with SessionLocal() as session:
        assert session.query(User).filter_by(email=email).count() == 0
        orphans = session.query(CreditTransaction).outerjoin(User, CreditTransaction.user_id == User.id).filter(User.id.is_(None)).count()
        assert orphans == 0  # ON DELETE CASCADE removed the ledger rows


def test_cleanup_deletes_only_data_older_than_five_days(client) -> None:
    browser, _ = new_user(client)
    old, fresh = segment(browser), segment(browser)
    six_days_ago = datetime.now(UTC) - timedelta(days=6)
    with SessionLocal() as session:
        session.query(Prediction).filter(Prediction.id == uuid.UUID(old["id"])).update({Prediction.created_at: six_days_ago})
        session.commit()
    old_folder = job_folder(old["cutout_url"])
    os.utime(old_folder, (six_days_ago.timestamp(), six_days_ago.timestamp()))

    report = run_cleanup()
    assert report is not None and report.predictions >= 1 and report.folders >= 1
    assert browser.get(f"/api/predictions/{old['id']}").status_code == 404
    assert not old_folder.exists()
    assert browser.get(f"/api/predictions/{fresh['id']}").status_code == 200
    assert job_folder(fresh["cutout_url"]).exists()


def test_security_headers_and_request_id(client) -> None:
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert len(response.headers["X-Request-ID"]) == 12
    assert client.get("/api/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    assert client.get("/api/health", headers={"X-Request-ID": "<script>"}).headers["X-Request-ID"] != "<script>"


# ---------- editor placement autosave ----------


def compose(browser: TestClient) -> dict:
    response = browser.post("/api/compositions", files={"person_image": image_file(), "background_image": image_file()})
    assert response.status_code == 201, response.text
    return response.json()


def test_editor_placement_is_saved_and_restored(client) -> None:
    browser, _ = new_user(client)
    composition = compose(browser)
    assert composition["placement"] is None  # never edited yet
    placement = {"x": 0.3, "bottom": 0.9, "height": 0.55, "mirrored": True}
    assert browser.put(f"/api/compositions/{composition['id']}/placement", json=placement).status_code == 204
    assert browser.get(f"/api/compositions/{composition['id']}").json()["placement"] == placement
    moved = {**placement, "x": 0.7}  # saving again updates the same row (upsert)
    assert browser.put(f"/api/compositions/{composition['id']}/placement", json=moved).status_code == 204
    listed = browser.get("/api/compositions").json()["items"][0]
    assert listed["placement"] == moved  # the list includes it too (LEFT JOIN)


def test_placement_is_validated_and_owner_only(client) -> None:
    owner, _ = new_user(client)
    composition = compose(owner)
    url = f"/api/compositions/{composition['id']}/placement"
    assert owner.put(url, json={"x": 1.5, "bottom": 0.9, "height": 0.5}).status_code == 422  # x must be 0-1
    stranger, _ = new_user(client)
    assert stranger.put(url, json={"x": 0.5, "bottom": 0.9, "height": 0.5}).status_code == 404


def test_deleting_a_composition_deletes_its_placement(client) -> None:
    browser, _ = new_user(client)
    composition = compose(browser)
    browser.put(f"/api/compositions/{composition['id']}/placement", json={"x": 0.5, "bottom": 1, "height": 0.6})
    assert browser.delete(f"/api/compositions/{composition['id']}").status_code == 204
    with SessionLocal() as session:
        assert session.get(CompositionPlacement, uuid.UUID(composition["id"])) is None  # ON DELETE CASCADE


# ---------- per-IP abuse limits ----------


def test_sign_ups_are_limited_per_ip(client, monkeypatch) -> None:
    with SessionLocal() as session:  # start from a clean slate for this test's address
        session.query(IpEvent).delete()
        session.commit()
    monkeypatch.setattr(settings, "registrations_per_ip_per_day", 2)
    new_user(client)
    new_user(client)
    third = TestClient(app).post("/api/auth/register", json={"email": f"x-{uuid.uuid4().hex[:8]}@example.com", "password": "password123"})
    assert third.status_code == 429 and "new accounts" in third.json()["detail"]


def test_password_spraying_from_one_ip_is_blocked(client, monkeypatch) -> None:
    with SessionLocal() as session:
        session.query(IpEvent).delete()
        session.commit()
    monkeypatch.setattr(settings, "login_failures_per_ip", 3)
    attacker = TestClient(app)
    for _ in range(3):  # one guess each against three DIFFERENT accounts: the per-email limit never triggers
        email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
        assert attacker.post("/api/auth/login", json={"email": email, "password": "Summer2026!"}).status_code == 401
    blocked = attacker.post("/api/auth/login", json={"email": "another@example.com", "password": "Summer2026!"})
    assert blocked.status_code == 429 and "your network" in blocked.json()["detail"]
    with SessionLocal() as session:  # only hashes are stored, never the raw address
        assert all(len(row.ip_hash) == 64 and "testclient" not in row.ip_hash for row in session.query(IpEvent))


# ---------- email verification ----------


def test_new_accounts_must_confirm_email_before_running_jobs(client) -> None:
    browser, email = new_user(client, verify=False)
    assert browser.get("/api/auth/me").json()["email_verified"] is False
    blocked = browser.post("/api/predictions", files={"image": image_file()})
    assert blocked.status_code == 403 and "Confirm your email" in blocked.json()["detail"]
    token = last_link(email, "verify")
    assert TestClient(app).post("/api/auth/verify-email", json={"token": token}).status_code == 204  # works without signing in
    assert browser.get("/api/auth/me").json()["email_verified"] is True
    assert browser.post("/api/predictions", files={"image": image_file()}).status_code == 201
    assert browser.post("/api/auth/verify-email", json={"token": token}).status_code == 400  # single use


def test_resending_verification_replaces_the_old_link_and_is_limited(client) -> None:
    browser, email = new_user(client, verify=False)
    first = last_link(email, "verify")
    assert browser.post("/api/auth/resend-verification").status_code == 202
    second = last_link(email, "verify")
    assert first != second
    assert browser.post("/api/auth/verify-email", json={"token": first}).status_code == 400  # older link stopped working
    assert browser.post("/api/auth/resend-verification").status_code == 202  # 3rd email within the hour
    assert browser.post("/api/auth/resend-verification").status_code == 429  # 4th: limited
    assert browser.post("/api/auth/verify-email", json={"token": last_link(email, "verify")}).status_code == 204


def test_verification_links_expire(client) -> None:
    _, email = new_user(client, verify=False)
    token = last_link(email, "verify")
    with SessionLocal() as session:
        session.query(EmailToken).filter(EmailToken.purpose == "verify").update(
            {EmailToken.expires_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
    assert TestClient(app).post("/api/auth/verify-email", json={"token": token}).status_code == 400


# ---------- password reset ----------


def test_forgot_password_answers_the_same_for_unknown_emails(client) -> None:
    sent_before = len(outbox)
    unknown = TestClient(app).post("/api/auth/forgot-password", json={"email": "nobody-here@example.com"})
    assert unknown.status_code == 202 and len(outbox) == sent_before  # same answer, no email sent
    _, email = new_user(client)
    known = TestClient(app).post("/api/auth/forgot-password", json={"email": email})
    assert known.status_code == 202 and known.json() == unknown.json()  # can't tell which emails have accounts


def test_password_reset_changes_password_and_signs_out_everywhere(client) -> None:
    browser, email = new_user(client)
    assert TestClient(app).post("/api/auth/forgot-password", json={"email": email}).status_code == 202
    token = last_link(email, "reset")
    assert "/#/reset?token=" in outbox[-1].text and outbox[-1].text.startswith("Someone asked")
    assert TestClient(app).post("/api/auth/reset-password", json={"token": token, "password": "brand-new-pass"}).status_code == 204
    assert browser.get("/api/auth/me").status_code == 401  # old session ended
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": email, "password": "brand-new-pass"}).status_code == 200
    again = TestClient(app).post("/api/auth/reset-password", json={"token": token, "password": "another-pass1"})
    assert again.status_code == 400  # the link works only once


def test_reset_link_uses_the_configured_address_not_the_host_header(client) -> None:
    _, email = new_user(client)
    TestClient(app).post("/api/auth/forgot-password", json={"email": email}, headers={"Host": "attacker.example"})
    assert "attacker.example" not in outbox[-1].text
    assert outbox[-1].text.split("/#/reset")[0].endswith(settings.public_url.rstrip("/").split("//")[1])


# ---------- private images ----------


def test_images_are_only_visible_to_their_owner(client) -> None:
    owner, _ = new_user(client)
    prediction = segment(owner)
    url = prediction["cutout_url"]
    assert url.startswith("/api/media/predictions/")
    assert owner.get(url).status_code == 200
    assert owner.get(url).headers["cache-control"].startswith("private")
    stranger, _ = new_user(client)
    assert stranger.get(url).status_code == 404  # the exact link is not enough
    assert TestClient(app).get(url).status_code == 401  # nor without signing in
    assert owner.get(url.replace("/cutout", "/../../etc/passwd")).status_code == 404
    assert owner.get("/media/" + str(job_folder(url).name) + "/cutout.png").status_code == 404  # old public path is gone
