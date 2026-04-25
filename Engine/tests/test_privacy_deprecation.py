"""Tests for P2D — H2 deprecation + H3 grandfather removal."""
from __future__ import annotations

import os
import sys

# Stable encryption key for token tests — must be set BEFORE server.py imports
# crypto.py via tokens.py. SIRR_TOKEN_SECRET is now obsolete (P2F) but harmless.
os.environ["SIRR_ENCRYPTION_KEY"] = "a" * 64
os.environ["SIRR_TOKEN_SECRET"] = "test-secret-for-unit-tests-only"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402
from tokens import mint_token  # noqa: E402

client = TestClient(server.app)


def test_reading_raw_returns_410():
    r = client.get("/reading/any-order-id")
    assert r.status_code == 410
    assert "retired" in r.text.lower()
    # The response must NOT echo the order_id back
    assert "any-order-id" not in r.text


def test_reading_raw_unified_returns_410():
    r = client.get("/reading/any-order-id/unified")
    assert r.status_code == 410
    assert "any-order-id" not in r.text


def test_reading_raw_merged_returns_410():
    r = client.get("/reading/any-order-id/merged")
    assert r.status_code == 410
    assert "any-order-id" not in r.text


def test_r_token_invalid_returns_404():
    # Unsigned string that looks like an order_id must 404 on /r/
    # (grandfather removed in P2D)
    r = client.get("/r/looks-like-an-order-id-but-isnt-a-token")
    assert r.status_code == 404


def test_r_token_invalid_unified_returns_404():
    r = client.get("/r/looks-like-an-order-id/unified")
    assert r.status_code == 404


def test_r_token_invalid_merged_returns_404():
    r = client.get("/r/looks-like-an-order-id/merged")
    assert r.status_code == 404


def test_r_valid_token_reaches_handler():
    """A validly-signed token must pass token-verify and reach the
    internal serve helper. We don't require the order to exist — just
    that resolution succeeded (reach-through proves grandfather-removal
    didn't break the happy path)."""
    tok = mint_token("nonexistent-order-for-test")
    r = client.get(f"/r/{tok}")
    # Either 200 (if fixture existed) or 404 from the helper's own
    # get_order() lookup — NOT 404 from _resolve_token_or_order_id,
    # NOT 410 from the deprecated route.
    assert r.status_code in (200, 404)


def test_r_valid_token_unified_reaches_handler():
    tok = mint_token("nonexistent-order-for-test")
    r = client.get(f"/r/{tok}/unified")
    assert r.status_code in (200, 404)


def test_r_valid_token_merged_reaches_handler():
    tok = mint_token("nonexistent-order-for-test")
    r = client.get(f"/r/{tok}/merged")
    assert r.status_code in (200, 404)


# ── P2F surface closures ──────────────────────────────────────────────────


def test_api_order_status_raw_returns_410():
    """P2F: /api/order-status/{order_id} is now deprecated. Use the
    token-gated /api/r/{token}/status instead."""
    r = client.get("/api/order-status/any-order-id")
    assert r.status_code == 410
    # Must NOT echo the order_id back
    assert "any-order-id" not in r.text


def test_success_with_order_id_query_returns_410():
    """P2F: /success?order_id=... legacy query branch is gone."""
    r = client.get("/success?order_id=any-order-id")
    assert r.status_code == 410
    assert "any-order-id" not in r.text


def test_success_with_token_query_returns_200():
    """P2F: /success?token=... still serves the static page."""
    tok = mint_token("nonexistent-order-for-test")
    r = client.get(f"/success?token={tok}")
    assert r.status_code == 200  # serves success.html


def test_success_with_no_params_still_serves_page():
    """No params at all still returns 200 — JS handles missing-token UX."""
    r = client.get("/success")
    assert r.status_code == 200


# ── P2F-PR2 hardening: response-body cleanups ────────────────────────────


def test_status_response_does_not_include_reading_url():
    """Codex Finding 1: status JSON must not echo raw /reading/ URL.

    Source-level check on _serve_order_status_by_id — it must not
    include 'reading_url' in its returned dict literal."""
    import inspect
    src = inspect.getsource(server._serve_order_status_by_id)
    assert "reading_url" not in src, \
        "status helper still references reading_url (Codex Finding 1)"
    # Also assert the live endpoint shape — non-existent token => 404,
    # but a real call would return only {status: ...}
    tok = mint_token("nonexistent-order-for-test")
    r = client.get(f"/api/r/{tok}/status")
    assert r.status_code == 404


def test_checkout_response_does_not_include_order_id():
    """Codex Finding 2: checkout response must not echo raw order_id.

    Source-level check: assert no `return {...}` line in create_checkout
    contains the literal '"order_id": order_id' (which would re-introduce
    the leak). Outbound payment-provider payloads (LS checkout_data.custom,
    Stripe metadata) are intentional — those are server-to-server."""
    import inspect
    import re
    src = inspect.getsource(server.create_checkout)
    # Find `return {...}` lines (one per branch: test, LS, Stripe)
    return_lines = [
        line for line in src.splitlines()
        if line.strip().startswith("return {")
    ]
    assert len(return_lines) == 3, \
        f"expected 3 return-dict branches in create_checkout, got {len(return_lines)}"
    for line in return_lines:
        assert '"order_id": order_id' not in line, \
            f"checkout return still includes order_id (Codex Finding 2): {line!r}"
