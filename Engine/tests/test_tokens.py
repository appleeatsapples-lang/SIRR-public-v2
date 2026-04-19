"""Tests for the signed URL token module (§16.5 hardening)."""
from __future__ import annotations

import os
import sys
import time

# Set a stable test secret BEFORE importing the module so the closure binds to it
os.environ["SIRR_TOKEN_SECRET"] = "test-secret-for-unit-tests-only"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
from tokens import (  # noqa: E402
    mint_token,
    verify_token,
    try_verify_token,
    TokenError,
    TokenMalformed,
    TokenSignatureInvalid,
    TokenExpired,
    DEFAULT_TTL_SECONDS,
)


def test_round_trip():
    tok = mint_token("ord_abc123")
    assert verify_token(tok) == "ord_abc123"


def test_round_trip_preserves_special_chars():
    tok = mint_token("ord_with-dashes_and_underscores")
    assert verify_token(tok) == "ord_with-dashes_and_underscores"


def test_token_shape():
    tok = mint_token("ord_1")
    parts = tok.split(".")
    assert len(parts) == 2
    assert len(parts[0]) > 0 and len(parts[1]) > 0
    # No padding equals signs — URL safe
    assert "=" not in tok
    assert "+" not in tok and "/" not in tok


def test_tamper_rejected():
    tok = mint_token("ord_x")
    # Flip one character in the signature
    tampered = tok[:-4] + ("B" if tok[-4] != "B" else "C") + tok[-3:]
    try:
        verify_token(tampered)
        assert False, "tampered token should have been rejected"
    except TokenSignatureInvalid:
        pass


def test_empty_and_malformed_rejected():
    for bad in ["", "no-dot", "a.b.c", "...", "only.", ".only"]:
        assert try_verify_token(bad) is None, f"should reject {bad!r}"


def test_non_string_rejected():
    assert try_verify_token(None) is None
    # verify_token should raise for non-string
    try:
        verify_token(12345)  # type: ignore
        assert False
    except TokenMalformed:
        pass


def test_expired_rejected():
    tok = mint_token("ord_expire_me", ttl_seconds=-60)
    try:
        verify_token(tok)
        assert False, "expired token should have been rejected"
    except TokenExpired:
        pass


def test_bad_base64_rejected():
    # payload looks like b64 but signature is garbage bytes
    bad = "!!!not-b64!!!.!!!also-not!!!"
    assert try_verify_token(bad) is None


def test_mint_requires_string_oid():
    for bad in [None, "", 123, [], {}]:
        try:
            mint_token(bad)  # type: ignore
            assert False, f"mint should reject oid={bad!r}"
        except (ValueError, TypeError, AttributeError):
            pass


def test_default_ttl_is_30_days():
    assert DEFAULT_TTL_SECONDS == 30 * 24 * 60 * 60


def test_expiry_embedded_roughly_correct():
    import json
    import base64
    tok = mint_token("ord_exptest")
    payload_b64 = tok.split(".")[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    now = int(time.time())
    assert payload["oid"] == "ord_exptest"
    assert payload["exp"] > now
    assert payload["exp"] <= now + DEFAULT_TTL_SECONDS + 5  # within 5s slop
