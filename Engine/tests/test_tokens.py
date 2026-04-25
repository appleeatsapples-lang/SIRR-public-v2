"""Tests for the encrypted URL token module (§16.5 hardening, P2F)."""
from __future__ import annotations

import base64
import json
import os
import sys
import time

# Stable encryption key for tests — set BEFORE importing crypto.py via tokens.py
# 64 hex chars = 32 bytes = AES-256 key. Tokens minted under this key are
# self-consistent within the test process.
os.environ["SIRR_ENCRYPTION_KEY"] = "a" * 64

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
    """Tokens are now a single base64url-encoded ciphertext blob — no more
    `<payload>.<signature>` split. URL-safe (no padding, no '+' or '/')."""
    tok = mint_token("ord_1")
    # Single segment — no dots
    assert "." not in tok
    # URL-safe
    assert "=" not in tok
    assert "+" not in tok and "/" not in tok
    # Decodes as base64url to a non-empty byte blob
    padded = tok + "=" * (-len(tok) % 4)
    raw = base64.urlsafe_b64decode(padded)
    # Must be at least HEADER(5) + NONCE(12) + payload + TAG(16) bytes
    assert len(raw) >= 33, f"token decodes to too few bytes: {len(raw)}"


def test_token_payload_is_not_clear_text():
    """Privacy: the token must not reveal the order_id when client-side
    decoded. This is the entire point of P2F."""
    token = mint_token("muhab-akif-23sep1996-9376")
    # Must NOT be possible to recover oid by base64-decode + JSON-parse
    try:
        # Try the OLD format (which we're moving away from)
        first_segment = token.split(".")[0]
        padded = first_segment + "=" * (-len(first_segment) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        payload = json.loads(decoded)
        assert "oid" not in payload, \
            "PRIVACY FAILURE: token payload is readable JSON"
    except (ValueError, json.JSONDecodeError, IndexError):
        # Expected: token is not the old format, decode fails. Pass.
        pass

    # Also: the entire token, decoded as base64, must not contain the
    # order_id string in any byte form. Belt-and-suspenders.
    padded_full = token + "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode(padded_full)
    assert b"muhab-akif-23sep1996-9376" not in raw, \
        "PRIVACY FAILURE: order_id appears in raw token bytes"


def test_tamper_rejected():
    """Tampering with any byte of the ciphertext or auth tag must trip
    the AEAD authentication tag check."""
    tok = mint_token("ord_x")
    # Flip a character near the end (which lands inside the GCM auth tag)
    tampered = tok[:-2] + ("A" if tok[-2] != "A" else "B") + tok[-1]
    try:
        verify_token(tampered)
        assert False, "tampered token should have been rejected"
    except TokenSignatureInvalid:
        pass


def test_empty_and_malformed_rejected():
    """Empty strings and obviously-not-tokens must reject (return None
    from try_verify_token, not raise unexpectedly)."""
    for bad in ["", "!!!not-b64!!!", "too short", "AAAAAAAAAAAAAAAA"]:
        assert try_verify_token(bad) is None, f"should reject {bad!r}"


def test_non_string_rejected():
    assert try_verify_token(None) is None
    # verify_token should raise TokenMalformed for non-string
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
    """Non-base64 garbage must reject cleanly."""
    bad = "!!!not-b64!!!"
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


def test_expiry_embedded_correctly():
    """The exp timestamp inside the (decrypted) payload is roughly now+TTL.

    Verify by minting, calling verify_token (which decrypts and returns oid),
    then minting another with negative TTL and asserting it raises TokenExpired.
    Direct payload introspection isn't possible client-side anymore (that's
    the privacy property); we infer expiry behavior via the public API."""
    now_before = int(time.time())
    tok = mint_token("ord_exptest")
    # Round-trip works -> not expired -> exp > now
    assert verify_token(tok) == "ord_exptest"
    now_after = int(time.time())
    # And the inverse: expired tokens raise
    expired = mint_token("ord_exptest", ttl_seconds=-1)
    try:
        verify_token(expired)
        assert False, "negative TTL should produce expired token"
    except TokenExpired as e:
        msg = str(e)
        # Expiry should be roughly "now-1" — within a few seconds of `now_before`
        # (the message format is "token expired at <exp>, now <now>")
        assert "expired at" in msg
