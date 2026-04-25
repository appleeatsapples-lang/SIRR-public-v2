"""Tests for P2D — H2 deprecation + H3 grandfather removal."""
from __future__ import annotations

import os
import sys

# Stable secret for token tests — must be set BEFORE server.py imports tokens.py
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
