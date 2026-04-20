"""Static content pages.

Serves the landing page, Privacy Policy, Terms of Service, and the
success page after checkout. These are all static HTML files bundled
in Engine/web/ — no computation, no engine calls.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent.parent / "web"


@router.get("/")
async def homepage():
    return FileResponse(str(WEB_DIR / "index.html"))


@router.get("/privacy")
async def privacy_page():
    return FileResponse(str(WEB_DIR / "privacy.html"))


@router.get("/terms")
async def terms_page():
    return FileResponse(str(WEB_DIR / "terms.html"))


@router.get("/success")
async def success_page(order_id: str = None, token: str = None):
    """Shown after checkout completes. Accepts either token (preferred per
    §16.5) or order_id (grandfathered). The page itself is static; the
    JS polls for reading readiness."""
    return FileResponse(str(WEB_DIR / "success.html"))
