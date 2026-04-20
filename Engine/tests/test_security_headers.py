"""Tests for security_headers.py — browser-security header middleware.

Verifies that the middleware applies the expected headers to responses
from a minimal FastAPI app. Doesn't import server.py directly — tests
the middleware class in isolation so the test is fast and not dependent
on the engine stack.
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
from security_headers import (  # noqa: E402
    SecurityHeadersMiddleware,
    SECURITY_HEADERS,
    CSP_HEADER,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/custom-csp")
    async def custom_csp():
        from fastapi.responses import JSONResponse
        resp = JSONResponse({"ok": True})
        # Handler sets a narrower CSP; middleware must NOT overwrite.
        resp.headers["Content-Security-Policy"] = "default-src 'none'"
        return resp

    return app


def test_all_security_headers_present_on_response():
    client = TestClient(_make_app())
    resp = client.get("/ping")
    assert resp.status_code == 200
    for header in SECURITY_HEADERS:
        assert header in resp.headers, f"missing header: {header}"


def test_hsts_two_year_preload():
    client = TestClient(_make_app())
    resp = client.get("/ping")
    hsts = resp.headers["Strict-Transport-Security"]
    assert "max-age=63072000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts


def test_csp_contains_required_directives():
    client = TestClient(_make_app())
    resp = client.get("/ping")
    csp = resp.headers["Content-Security-Policy"]
    # Key anchors of the policy — exact-string match catches accidental
    # deletion of any critical directive during future edits.
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "upgrade-insecure-requests" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert csp == CSP_HEADER  # full equality against module constant


def test_frame_options_deny():
    client = TestClient(_make_app())
    resp = client.get("/ping")
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_permissions_policy_disables_sensitive_features():
    client = TestClient(_make_app())
    resp = client.get("/ping")
    pp = resp.headers["Permissions-Policy"]
    for feature in ("geolocation", "microphone", "camera", "payment"):
        assert f"{feature}=()" in pp


def test_handler_set_header_wins_over_middleware():
    """Handler-set headers must not be overwritten by the middleware.
    Lets individual routes narrow the policy if they need to."""
    client = TestClient(_make_app())
    resp = client.get("/custom-csp")
    # Handler set a narrower policy; middleware should have left it alone.
    assert resp.headers["Content-Security-Policy"] == "default-src 'none'"
    # But other headers that the handler did NOT set should still be applied.
    assert resp.headers["X-Frame-Options"] == "DENY"
