"""Tests for errors.py — styled error/status page rendering."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
from errors import (  # noqa: E402
    render_page,
    render_404,
    render_401,
    render_400,
    render_500,
    render_reading_processing,
    render_reading_pending,
)


def test_renders_valid_html():
    html = render_404()
    assert "<!doctype html>" in html.lower()
    assert "<html" in html
    assert "</html>" in html


def test_all_renderers_produce_output():
    for fn in [render_404, render_401, render_400, render_500,
               render_reading_processing, render_reading_pending]:
        out = fn()
        assert len(out) > 500  # template alone is ~3k chars
        assert "<html" in out


def test_substitutions_happened():
    html = render_404()
    # None of the raw template markers should survive
    for marker in ("{{TITLE}}", "{{CODE}}", "{{HEADLINE}}",
                   "{{DETAIL}}", "{{ACTIONS}}"):
        assert marker not in html, f"Unsubstituted marker {marker} in output"


def test_404_has_expected_content():
    html = render_404()
    assert "404" in html
    assert "drift" in html.lower() or "not" in html.lower()


def test_401_has_expected_content():
    html = render_401()
    assert "401" in html


def test_400_accepts_custom_detail():
    html = render_400("Invalid date: must be YYYY-MM-DD")
    assert "Invalid date" in html
    assert "YYYY-MM-DD" in html


def test_400_default_detail():
    html = render_400()
    assert "400" in html


def test_html_escaping_on_headline():
    html = render_page(
        title="x",
        code="500",
        headline="<script>alert('xss')</script>",
        detail="normal",
    )
    # Raw script tag must NOT appear
    assert "<script>alert" not in html
    # Escaped version must
    assert "&lt;script&gt;" in html


def test_html_escaping_on_detail():
    html = render_page(
        title="x", code="x",
        headline="x",
        detail="see <https://evil.com> for details",
    )
    assert "<https://evil.com>" not in html
    assert "&lt;https://evil.com&gt;" in html


def test_actions_rendered_with_escaping():
    html = render_page(
        title="x", code="x", headline="x", detail="x",
        actions=[("Click <me>", "/safe", True), ("Also", "/other", False)],
    )
    # Escaped label
    assert "Click &lt;me&gt;" in html
    # Both hrefs present
    assert 'href="/safe"' in html
    assert 'href="/other"' in html
    # Primary class applied to first button
    assert 'class="primary"' in html


def test_actions_optional():
    # Should not crash with None or empty list
    html1 = render_page(title="x", code="x", headline="x", detail="x", actions=None)
    html2 = render_page(title="x", code="x", headline="x", detail="x", actions=[])
    assert "{{ACTIONS}}" not in html1
    assert "{{ACTIONS}}" not in html2


def test_reading_processing_says_refresh():
    html = render_reading_processing()
    assert "refresh" in html.lower() or "prepared" in html.lower()


def test_template_not_mutated_between_calls():
    # Run a bunch and make sure the cached template still has markers
    # only as substitution targets, not leaking across calls
    for _ in range(5):
        h1 = render_404()
        h2 = render_500()
        assert "404" in h1
        assert "500" in h2
        assert "404" not in h2
        assert "500" not in h1
