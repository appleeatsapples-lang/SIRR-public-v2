"""Signed expiring URL tokens for reading access.

Per §16.5: order IDs must not appear in URLs (they act as capability tokens
and leak via referrers, browser history, and server logs). Instead, we mint
a signed token that includes the order ID plus an expiry timestamp, signed
with a server secret.

Token format: base64url(payload) + "." + base64url(signature)
  payload   : JSON {"oid": "<order_id>", "exp": <unix_timestamp>}
  signature : HMAC-SHA256(payload, secret)

Tokens expire after DEFAULT_TTL_SECONDS (30 days), matching the Tier 2
retention window defined in DECISIONS_LOCKED §16.2.

Security properties:
  - Unforgeable without the secret key
  - Tamper-evident (any payload change invalidates signature)
  - Time-bounded (expiry embedded and enforced on verify)
  - No database lookup required to verify — self-contained
  - One-time signing cost, O(1) verify

If SIRR_TOKEN_SECRET env var is unset, a deterministic fallback is derived
from STRIPE_WEBHOOK_SECRET or a per-process random string (dev only; will
log a warning so it doesn't silently pass in production).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from typing import Optional

# 30 days in seconds — matches Tier 2 retention window
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60

# Derive a stable token secret. Priority order:
#   1. SIRR_TOKEN_SECRET (dedicated)
#   2. Derived from STRIPE_WEBHOOK_SECRET (reuses existing secret material)
#   3. Random per-process (dev only — printed warning)
_SECRET = os.environ.get("SIRR_TOKEN_SECRET")
if not _SECRET:
    _derived_from = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if _derived_from:
        _SECRET = hashlib.sha256(
            b"sirr-token-v1|" + _derived_from.encode("utf-8")
        ).hexdigest()
    else:
        _SECRET = secrets.token_hex(32)
        print(
            "[WARN] SIRR_TOKEN_SECRET not set and no STRIPE_WEBHOOK_SECRET "
            "to derive from — using per-process random secret. "
            "Tokens will NOT survive server restart. Set SIRR_TOKEN_SECRET "
            "in production.",
            file=sys.stderr,
        )

_SECRET_BYTES = _SECRET.encode("utf-8") if isinstance(_SECRET, str) else _SECRET


def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """URL-safe base64 decode, pad-tolerant."""
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _sign(payload_bytes: bytes) -> bytes:
    """HMAC-SHA256 signature of payload using the server secret."""
    return hmac.new(_SECRET_BYTES, payload_bytes, hashlib.sha256).digest()


def mint_token(order_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Mint a signed token for the given order_id.

    Args:
        order_id: The internal order identifier this token grants access to.
        ttl_seconds: Validity window in seconds. Defaults to 30 days.

    Returns:
        A URL-safe string of the form "<payload>.<signature>", suitable for
        inclusion in URLs or query params. Typical length ~120 chars.
    """
    if not order_id or not isinstance(order_id, str):
        raise ValueError("order_id must be a non-empty string")
    payload = {"oid": order_id, "exp": int(time.time()) + int(ttl_seconds)}
    payload_bytes = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    signature = _sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


class TokenError(Exception):
    """Base class for all token verification failures."""


class TokenMalformed(TokenError):
    """Token does not parse as <payload>.<signature> or payload isn't JSON."""


class TokenSignatureInvalid(TokenError):
    """HMAC signature does not match the payload."""


class TokenExpired(TokenError):
    """Token's embedded expiry timestamp is in the past."""


def verify_token(token: str) -> str:
    """Verify a signed token and return the embedded order_id.

    Raises TokenMalformed, TokenSignatureInvalid, or TokenExpired on failure.

    Args:
        token: The string minted by mint_token().

    Returns:
        The order_id string embedded in the token's payload.
    """
    if not token or not isinstance(token, str):
        raise TokenMalformed("empty or non-string token")

    parts = token.split(".")
    if len(parts) != 2:
        raise TokenMalformed("expected <payload>.<signature>")

    payload_b64, sig_b64 = parts
    try:
        payload_bytes = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception as e:
        raise TokenMalformed(f"base64 decode failed: {e}")

    # Signature check FIRST (before parsing) to avoid side-channel info leaks
    expected_sig = _sign(payload_bytes)
    if not hmac.compare_digest(expected_sig, sig):
        raise TokenSignatureInvalid("signature mismatch")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise TokenMalformed(f"payload JSON parse failed: {e}")

    if not isinstance(payload, dict):
        raise TokenMalformed("payload not a JSON object")
    oid = payload.get("oid")
    exp = payload.get("exp")
    if not isinstance(oid, str) or not oid:
        raise TokenMalformed("payload missing oid")
    if not isinstance(exp, (int, float)):
        raise TokenMalformed("payload missing exp")

    now = int(time.time())
    if now >= int(exp):
        raise TokenExpired(f"token expired at {exp}, now {now}")

    return oid


def try_verify_token(token: str) -> Optional[str]:
    """Non-raising variant of verify_token. Returns order_id or None."""
    try:
        return verify_token(token)
    except TokenError:
        return None
