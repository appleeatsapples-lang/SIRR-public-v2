"""Retention purge endpoint (§16.2 / §16.6).

Single route: POST /api/internal/purge.

Auth via SIRR_INTERNAL_SECRET header. Invoked by the Railway scheduled job
(Tools/scripts/retention_cron.sh) nightly at 03:00 UTC, plus the admin
dashboard's "Run retention purge" button for manual triggers.
"""
from __future__ import annotations

import sys

from fastapi import APIRouter, HTTPException, Request

from auth import require_internal_secret
from sanitize import sanitize_exception

router = APIRouter()


@router.post("/api/internal/purge")
async def trigger_purge(request: Request):
    """Run Tier 2 retention sweep + Tier 3 deletion queue drain.

    Returns JSON summary of what was done. Never surfaces filenames,
    order IDs, or any user data — only counts and timestamps.
    """
    require_internal_secret(request)
    try:
        from retention import purge_cycle
        return purge_cycle()
    except Exception as purge_err:
        print(f"[purge-endpoint] failed: {sanitize_exception(purge_err)}", file=sys.stderr)
        raise HTTPException(500, "purge cycle failed")
