"""Zero-knowledge operator admin (§16.3).

Two routes:
- GET /admin              — static HTML dashboard (auth in browser)
- GET /api/internal/metrics — aggregate snapshot (server-side auth)

Both routes share the same SIRR_INTERNAL_SECRET auth model. The dashboard
never fetches the secret server-side; the browser prompts for it, holds it
in memory only, and sends it on every API call.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from auth import require_internal_secret
from sanitize import sanitize_exception

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent.parent / "web"


@router.get("/api/internal/metrics")
async def operator_metrics(request: Request):
    """Zero-knowledge operator dashboard JSON.

    Returns aggregate counts / distributions / health indicators. Never
    returns order_ids, names, emails, DOBs, or anything that could point
    at a specific customer. Rare buckets (<5 members) collapsed per
    MIN_BUCKET_SIZE in metrics.py.
    """
    require_internal_secret(request)
    try:
        from metrics import compute_snapshot
        return compute_snapshot()
    except Exception as metrics_err:
        print(f"[metrics-endpoint] failed: {sanitize_exception(metrics_err)}", file=sys.stderr)
        raise HTTPException(500, "metrics computation failed")


@router.get("/admin")
async def admin_dashboard():
    """Renders the operator dashboard HTML. On load the page prompts for
    the internal secret, holds it in browser memory only, and uses it to
    fetch /api/internal/metrics. Server never stores or logs the secret."""
    admin_html = WEB_DIR / "admin.html"
    if not admin_html.exists():
        raise HTTPException(404, "admin dashboard not bundled")
    return FileResponse(str(admin_html), media_type="text/html")
