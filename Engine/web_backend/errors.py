"""Styled error and status page rendering.

Shared renderer for inline status pages (reading-processing, reading-pending)
and for the FastAPI exception handler chain (404, 401, 400, 500).

Loads _error.html template at import time, substitutes simple {{KEYS}}.
No third-party templating dep — stdlib str.replace is plenty.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import List, Optional, Tuple

_TEMPLATE_PATH = Path(__file__).parent.parent / "web" / "_error.html"
_TEMPLATE_CACHE: Optional[str] = None


def _load_template() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


def render_page(
    *,
    title: str,
    code: str,
    headline: str,
    detail: str,
    actions: Optional[List[Tuple[str, str, bool]]] = None,
) -> str:
    """Render the error/status template.

    actions: list of (label, href, is_primary) tuples. Rendered as anchor tags.
    All text inputs are HTML-escaped — callers pass plain strings.
    """
    tpl = _load_template()
    actions_html = ""
    if actions:
        buttons = []
        for label, href, is_primary in actions:
            cls = ' class="primary"' if is_primary else ""
            buttons.append(
                f'<a href="{html.escape(href)}"{cls}>{html.escape(label)}</a>'
            )
        actions_html = "".join(buttons)

    return (
        tpl.replace("{{TITLE}}", html.escape(title))
        .replace("{{CODE}}", html.escape(code))
        .replace("{{HEADLINE}}", html.escape(headline))
        .replace("{{DETAIL}}", html.escape(detail))
        .replace("{{ACTIONS}}", actions_html)
    )


# ── Preset renderers for common cases ────────────────────────────────────

def render_404() -> str:
    return render_page(
        title="Not found",
        code="404",
        headline="This page has drifted away.",
        detail=(
            "The reading or resource you're looking for doesn't exist here. "
            "It may have been purged by the 30-day retention policy, "
            "or the link may simply be wrong."
        ),
        actions=[("Return home", "/", True)],
    )


def render_401() -> str:
    return render_page(
        title="Unauthorized",
        code="401",
        headline="This door is closed to you.",
        detail=(
            "Your access token is missing, invalid, or expired. "
            "Reading links expire 30 days after issue."
        ),
        actions=[("Return home", "/", True)],
    )


def render_400(detail: Optional[str] = None) -> str:
    return render_page(
        title="Bad request",
        code="400",
        headline="Something in that request didn't line up.",
        detail=detail or (
            "The information submitted couldn't be interpreted. "
            "Check the form and try again."
        ),
        actions=[("Return home", "/", True)],
    )


def render_500() -> str:
    return render_page(
        title="Internal error",
        code="500",
        headline="Something broke on our side.",
        detail=(
            "An unexpected error occurred. No data has been lost. "
            "If this persists, wait a moment and try again."
        ),
        actions=[("Return home", "/", True)],
    )


def render_reading_processing() -> str:
    return render_page(
        title="Reading in progress",
        code="processing",
        headline="Your reading is being prepared.",
        detail=(
            "The engine is computing your 238 modules across "
            "sixteen traditions. This takes less than a minute. "
            "Refresh this page shortly."
        ),
        actions=[("Refresh", "", True)],
    )


def render_reading_pending() -> str:
    return render_page(
        title="Payment confirmed",
        code="queued",
        headline="Payment confirmed. Your reading is being generated.",
        detail=(
            "The engine will start in just a moment. "
            "Refresh this page shortly."
        ),
        actions=[("Refresh", "", True)],
    )
