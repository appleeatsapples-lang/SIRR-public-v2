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


def test_success_page_is_token_only():
    """P2F: success page only supports ?token= URLs. The legacy
    ?order_id= branch and any client-side construction of /reading/{id}
    or /api/order-status/{id} URLs must be gone."""
    html = _html()
    # Token branch is the only branch
    assert "params.get('token')" in html
    # Legacy params and URL-construction patterns must NOT appear
    assert "params.get('order_id')" not in html
    assert "orderId" not in html
    # Legacy raw-id URL constructions must NOT appear
    assert "/api/order-status/" not in html
    assert "'/reading/'" not in html


def test_no_order_id_display_element():
    """P2F: the order-id-display element is removed; no JS path writes
    user-visible text containing the order_id."""
    html = _html()
    assert "order-id-display" not in html
    assert "Order: '" not in html  # the legacy "Order: " prefix
    # Token must never be assigned to textContent
    assert ".textContent = 'Order: ' + token" not in html
    assert ".textContent = token" not in html


def test_missing_token_shows_expired_message():
    """P2F: when no token is in the URL, JS shows an expired-link message
    and stops polling — replaces the silent-spinner failure mode."""
    html = _html()
    assert "if (!token)" in html
    assert "expired or is invalid" in html
    # The polling code must throw (not silently continue) when no token
    assert "throw new Error('no token in success URL')" in html


def test_default_redirect_lands_on_merged_view():
    """PR #21 + P2F: success-page redirect lands on /r/{token}/merged
    (token-only after P2F). Regression guard: if someone flips this back
    to /unified or reintroduces the /reading/{id} path, CI catches it."""
    html = _html()
    # New default URL composition (token-only)
    assert "'/r/' + encodeURIComponent(token) + '/merged'" in html
    # Old /unified default must be gone
    assert "'/r/' + encodeURIComponent(token) + '/unified'" not in html
    # P2F: no orderId-based URL anywhere
    assert "encodeURIComponent(orderId)" not in html
