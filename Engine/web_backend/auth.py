"""Shared authentication helpers for /api/internal/* endpoints.

Centralized so multiple routers can enforce the same auth model without
duplicating the constant-time comparison logic.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def require_internal_secret(request: Request) -> None:
    """Verify the X-Internal-Secret header against SIRR_INTERNAL_SECRET env.

    Raises:
        HTTPException(503): if SIRR_INTERNAL_SECRET is unset (fail-closed)
        HTTPException(401): if the provided header doesn't match

    Uses hmac.compare_digest for constant-time comparison, defeating
    timing side-channel attacks that could otherwise leak the secret
    one byte at a time.
    """
    configured = os.environ.get("SIRR_INTERNAL_SECRET", "").strip()
    if not configured:
        raise HTTPException(503, "endpoint disabled (no SIRR_INTERNAL_SECRET)")
    provided = request.headers.get("x-internal-secret", "")
    if not hmac.compare_digest(provided, configured):
        raise HTTPException(401, "invalid or missing internal secret")
