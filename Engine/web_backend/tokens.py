"""Encrypted expiring URL tokens for reading access.

Per §16.5 (broader reading): order IDs must not appear in URLs in any
recoverable form. Earlier versions of this module used HMAC-signed tokens
whose payload was base64-encoded plaintext JSON — anyone with the URL could
decode the order_id without the server's secret. P2F closes that surface
by encrypting the payload with AES-256-GCM (AEAD), so the URL contains
only opaque ciphertext to anyone without the server-side master secret.

Token format: base64url(AES-GCM-encrypt(payload))
  payload   : JSON {"oid": "<order_id>", "exp": <unix_timestamp>}
  encryption: AES-256-GCM via crypto.encrypt_bytes(context="sirr-token-v1")
              The context binds the derived key to this specific use case;
              compromise of token-encryption keys does not affect Tier 2
              storage keys (which use order_id as context).

Tokens expire after DEFAULT_TTL_SECONDS (30 days), matching Tier 2 retention.

Security properties:
  - Confidential: payload not readable without master secret
  - Unforgeable: AEAD auth tag detects any tampering
  - Time-bounded: expiry embedded and enforced on verify
  - No database lookup required to verify — self-contained
  - O(1) verify

Migration note: Tokens minted by the previous (HMAC-signed) format are
NOT compatible with this version. Existing tokens-in-the-wild become
invalid on deploy and must be re-minted. Production callers should mint
fresh tokens via Railway SSH before announcing any URL changes.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Optional

from crypto import decrypt_bytes, encrypt_bytes

# 30 days in seconds — matches Tier 2 retention window
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60

# Context string for HKDF key derivation. Must match between mint and verify.
# Versioned so future changes can rotate without breaking existing tokens.
_TOKEN_CONTEXT = "sirr-token-v1"


def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """URL-safe base64 decode, pad-tolerant."""
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def mint_token(order_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Mint an encrypted token for the given order_id.

    Args:
        order_id: The internal order identifier this token grants access to.
        ttl_seconds: Validity window in seconds. Defaults to 30 days.

    Returns:
        A URL-safe string containing only opaque ciphertext. The order_id
        is not recoverable from this string without the server's master
        encryption key. Typical length ~150-180 chars.
    """
    if not order_id or not isinstance(order_id, str):
        raise ValueError("order_id must be a non-empty string")
    payload = {"oid": order_id, "exp": int(time.time()) + int(ttl_seconds)}
    payload_bytes = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    blob = encrypt_bytes(payload_bytes, context=_TOKEN_CONTEXT)
    return _b64url_encode(blob)


class TokenError(Exception):
    """Base class for all token verification failures."""


class TokenMalformed(TokenError):
    """Token does not parse as a valid encrypted blob."""


class TokenSignatureInvalid(TokenError):
    """AEAD authentication tag verification failed (tampered or wrong key)."""


class TokenExpired(TokenError):
    """Token's embedded expiry timestamp is in the past."""


def verify_token(token: str) -> str:
    """Verify an encrypted token and return the embedded order_id.

    Raises TokenMalformed, TokenSignatureInvalid, or TokenExpired on failure.

    Args:
        token: The string minted by mint_token().

    Returns:
        The order_id string embedded in the token's payload.
    """
    if not token or not isinstance(token, str):
        raise TokenMalformed("empty or non-string token")

    try:
        blob = _b64url_decode(token)
    except Exception:
        raise TokenMalformed("base64 decode failed")

    try:
        payload_bytes = decrypt_bytes(blob, context=_TOKEN_CONTEXT)
    except Exception:
        # crypto.decrypt_bytes raises on AEAD auth failure or malformed blob.
        # Don't echo the underlying message — could leak crypto details.
        raise TokenSignatureInvalid("decryption or auth tag check failed")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise TokenMalformed("payload JSON parse failed")

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
