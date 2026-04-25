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
async def success_page(token: str = None, order_id: str = None):
    """Shown after checkout completes. Token-only per §16.5 (P2F).

    The order_id query parameter is intentionally still in the function
    signature so that legacy `?order_id=` URLs are matched by FastAPI's
    parameter binding (rather than producing a generic 404 / 422), but
    the legacy branch is no longer served — it returns a 410 Gone page
    pointing the user at their email link.
    """
    if not token and order_id:
        # Legacy success URL with raw order_id. §16.5 violation. Serve 410.
        from server import _gone_410_response
        return _gone_410_response()
    # Token present (or no params at all — let the JS handle missing-token UX)
    return FileResponse(str(WEB_DIR / "success.html"))
