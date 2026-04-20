"""Tests for success page polling behavior (Engine/web/success.html).

These tests protect the audit fix (2026-04-20, F2.1) from accidental
regression. They're substring-assertions on the static HTML file,
not real JS execution — light but catches deletion of the termination
branches that would otherwise leave users watching a spinner forever.
"""
from __future__ import annotations

import os
from pathlib import Path

_HTML_PATH = Path(__file__).parent.parent / "web" / "success.html"


def _html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8")


def test_success_html_exists():
    assert _HTML_PATH.exists(), f"success.html missing at {_HTML_PATH}"


def test_polling_has_max_window():
    """Poll count must be bounded — without this, a silently-stuck
    background job leaves the user's spinner spinning indefinitely."""
    html = _html()
    assert "MAX_POLLS" in html
    assert "MAX_POLL_SECONDS" in html
    assert "pollCount > MAX_POLLS" in html
    assert "showTimedOut" in html


def test_consecutive_failure_tracking():
    """Fetch or parse errors must surface after a threshold, not be
    swallowed silently."""
    html = _html()
    assert "consecutiveFailures" in html
    assert "MAX_CONSECUTIVE_FAILURES" in html
    assert "showUnreachable" in html


def test_termination_states_have_user_messages():
    """Each terminal state must tell the user what happened."""
    html = _html()
    # Timeout state
    assert "taking longer than expected" in html.lower()
    # Failure state
    assert "something went wrong" in html.lower()
    # Unreachable state
    assert "unable to reach" in html.lower()
    # Ready state
    assert "your reading is ready" in html.lower()


def test_noscript_fallback_present():
    """Users with JS disabled must get explanatory text, not a blank spinner."""
    html = _html()
    assert "<noscript>" in html
    assert "</noscript>" in html
    assert "JavaScript is required" in html


def test_token_and_order_id_both_supported():
    """Success page must accept both URL param shapes (§16.5 + legacy)."""
    html = _html()
    assert "params.get('token')" in html
    assert "params.get('order_id')" in html
    # Token path redirects to /r/{token}/unified
    assert "'/r/'" in html
    # Order_id path redirects to /reading/{id}/unified
    assert "'/reading/'" in html


def test_order_id_never_displayed_as_token():
    """The display-only block shows order_id but never token material."""
    html = _html()
    # The display block exists
    assert "order-id-display" in html
    # Token is never assigned to textContent
    assert ".textContent = 'Order: ' + token" not in html
    assert ".textContent = token" not in html


def test_default_redirect_lands_on_merged_view():
    """PR #21: the success-page default redirect must land new customers
    on /r/{token}/merged (and /reading/{order_id}/merged for legacy
    order_id URLs). The merged view is the product's primary reader
    surface; unified stays accessible but isn't the landing page.

    Regression guard: if someone flips this back to /unified by accident,
    CI catches it here."""
    html = _html()
    # New default URL composition
    assert "'/r/' + encodeURIComponent(token) + '/merged'" in html
    assert "'/reading/' + encodeURIComponent(orderId) + '/merged'" in html
    # Old defaults must be gone — no drift back
    assert "'/r/' + encodeURIComponent(token) + '/unified'" not in html
    assert "'/reading/' + encodeURIComponent(orderId) + '/unified'" not in html
