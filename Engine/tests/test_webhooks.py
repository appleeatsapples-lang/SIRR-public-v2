"""Tests for webhook signature verification.

Guards the §16 security hardening behavior:
  - LS webhook MUST fail-closed when LEMONSQUEEZY_WEBHOOK_SECRET is unset.
  - Missing / wrong signatures return 400.
  - Valid signatures pass through.

These tests import the full server app. If dependencies for the engine
stack aren't installed (anthropic, pyswisseph, etc.), the import will
fail and these tests are skipped via pytest.importorskip.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))


@pytest.fixture
def client(monkeypatch):
    """Return a TestClient for the real server app with a known LS secret.

    Sets the env BEFORE import so module-level LS_WEBHOOK_SECRET captures it.
    """
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", "test-secret-for-webhook")
    # Fresh import so LS_WEBHOOK_SECRET picks up the patched env.
    for mod in ("server",):
        if mod in sys.modules:
            del sys.modules[mod]
    server = pytest.importorskip("server")
    from fastapi.testclient import TestClient
    return TestClient(server.app), server


def _sign(secret: str, payload_bytes: bytes) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def test_ls_webhook_rejects_missing_signature(client):
    tc, _ = client
    body = json.dumps({"meta": {"event_name": "ping"}}).encode()
    r = tc.post(
        "/api/webhook/lemonsqueezy",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert "signature" in r.json()["detail"].lower()


def test_ls_webhook_rejects_wrong_signature(client):
    tc, _ = client
    body = json.dumps({"meta": {"event_name": "ping"}}).encode()
    r = tc.post(
        "/api/webhook/lemonsqueezy",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "deadbeef" * 8,  # wrong-length nonsense
        },
    )
    assert r.status_code == 400


def test_ls_webhook_accepts_valid_signature_non_order_event(client):
    """A correctly-signed payload for an event we don't handle (not
    order_created) still returns 200 — only the update_order+thread
    block is gated by event_name. This verifies the signature path
    succeeds without triggering a background engine run."""
    tc, _ = client
    body = json.dumps({"meta": {"event_name": "subscription_created"}}).encode()
    sig = _sign("test-secret-for-webhook", body)
    r = tc.post(
        "/api/webhook/lemonsqueezy",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert r.status_code == 200
    assert r.json() == {"received": True}


def test_ls_webhook_fails_closed_when_secret_unset(monkeypatch):
    """Regression guard for the audit fix (2026-04-20).

    An unset LEMONSQUEEZY_WEBHOOK_SECRET MUST cause the webhook to return
    503, not 200. Previously the webhook fell-open when the env var was
    empty: any attacker with a guessable order_id could trigger engine
    runs (Anthropic API burn).
    """
    monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)
    for mod in ("server",):
        if mod in sys.modules:
            del sys.modules[mod]
    server = pytest.importorskip("server")
    from fastapi.testclient import TestClient
    tc = TestClient(server.app)

    body = json.dumps({"meta": {"event_name": "order_created"}}).encode()
    r = tc.post(
        "/api/webhook/lemonsqueezy",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()
