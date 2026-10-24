"""Code that runs around EVERY request: request IDs, access logging, and security headers."""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request, Response

from backend.app.core.config import settings

logger = logging.getLogger("human_cutout.http")

# Content Security Policy: the browser may load scripts, styles, fonts and API calls ONLY from this
# site. Even if an attacker managed to inject HTML, it could not load or send data anywhere else.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data: blob:",  # data: for the favicon and canvas downloads
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",  # nobody may show this site inside an <iframe> (clickjacking)
    ]
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # the browser must trust our Content-Type, not guess
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",  # older browsers' version of frame-ancestors
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


async def request_context(request: Request, call_next) -> Response:
    # Reuse the caller's ID (e.g. from a proxy) if it looks safe, otherwise make one. Returning it in
    # X-Request-ID lets a user report "request abc123 failed" and you find that exact log line.
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("%s %s -> unhandled error [id=%s]", request.method, request.url.path, request_id)
        raise
    milliseconds = (time.perf_counter() - started) * 1000

    response.headers["X-Request-ID"] = request_id
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not request.url.path.startswith(("/docs", "/redoc")):  # FastAPI's docs pages load assets from a CDN
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if settings.cookie_secure:  # production is HTTPS-only: tell browsers never to use plain HTTP
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")

    if request.url.path.startswith("/api"):  # one line per API call; no emails or other personal data
        logger.info("%s %s -> %s in %.0f ms [id=%s]", request.method, request.url.path, response.status_code, milliseconds, request_id)
    return response
