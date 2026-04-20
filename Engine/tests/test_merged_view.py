"""Tests for merged_view.py — the unified+legacy composition.

Exercises the renderer against the synthetic fixture to guarantee:
  - All four visual blocks fire when their source data is present
  - Graceful degradation: each block skipped when its data is absent,
    rest of the page still renders
  - No regression to unified_view (same entry point, same CSS)
"""
from __future__ import annotations

import copy
import json
import os
import sys
import types
from pathlib import Path

import pytest

# anthropic shim so reading_generator imports cleanly in test environments
# that don't have the SDK installed.
sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))

ENGINE = Path(__file__).parent.parent
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ENGINE / "web_backend"))

from unified_synthesis import compute_unified_synthesis  # noqa: E402


@pytest.fixture(scope="module")
def synthetic_output():
    """Load and enrich the synthetic FATIMA fixture the same way
    server._generate_merged_view does — tag allowlisted results with
    domain/tradition but do NOT filter out other results (visual
    extractors need access to tarot_birth, cardology, etc.)."""
    import importlib.util
    server_spec = importlib.util.find_spec("server")
    assert server_spec is not None, "server module must be importable"
    server = importlib.util.module_from_spec(server_spec)
    server_spec.loader.exec_module(server)

    fixture = ENGINE / "fixtures" / "synthetic_output.json"
    output = json.loads(fixture.read_text(encoding="utf-8"))
    output["unified"] = compute_unified_synthesis(output)
    for r in output.get("results", []):
        rid = r.get("id", "")
        if rid in server.SIRR_UNIFIED_ALLOWLIST:
            r["domain"] = server.DOMAIN_MAP[rid]
            r["tradition"] = server.MODULE_TRADITION.get(rid, "Other Traditions")
    output["view"] = "merged"
    return output


def test_renders_without_raising(synthetic_output):
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    # Non-trivial size — the synthetic profile has all domains populated
    assert len(html) > 40_000, f"unexpectedly small: {len(html)} chars"


def test_all_four_visual_blocks_present(synthetic_output):
    """Synthetic profile has data for every visual block. All four must fire."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    assert "Your Numeric Signature" in html
    assert "Your Cards" in html
    assert "Your Animals" in html
    assert "Your Planets" in html


def test_all_four_domain_sections_present(synthetic_output):
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    assert ">Numerology</h2>" in html
    assert ">Name Intelligence</h2>" in html
    assert ">Astro Timing</h2>" in html
    assert ">Convergence</h2>" in html


def test_visual_block_content_from_synthetic(synthetic_output):
    """Specific markers proving extractors are pulling real data, not
    placeholder scaffolding."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    # Tarot — from tarot_birth (Wheel of Fortune) and tarot_name (Emperor)
    assert "Wheel of Fortune" in html
    assert "The Emperor" in html
    # Cardology — 8 of Diamonds from synthetic
    assert "8 of Diamonds" in html
    # BaZi — Horse year pillar, Rabbit day pillar
    assert ">Horse<" in html
    assert "Rabbit" in html
    # Planets — Mars in joy, Vimshottari Dasha Timeline
    assert "In Joy" in html
    assert "Vimshottari Dasha Timeline" in html
    # Profection badge
    assert "Profection" in html


def test_convergence_monte_carlo_still_rendered(synthetic_output):
    """Regression guard — merged view must preserve the Monte Carlo
    convergence section from unified_view unchanged."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    assert "Monte Carlo Evidence" in html


def _strip_ids(output, ids_to_remove):
    """Return a deep-copy of output with the given module IDs dropped
    from results. Used for graceful-degradation tests."""
    clone = copy.deepcopy(output)
    clone["results"] = [r for r in clone.get("results", []) if r.get("id") not in ids_to_remove]
    return clone


def test_graceful_degradation_no_numerology(synthetic_output):
    """If core_numbers is empty, the numeric-signature block is skipped
    but the rest of the page still renders."""
    from merged_view import render_merged_html
    clone = copy.deepcopy(synthetic_output)
    clone["profile"]["core_numbers"] = {}
    # Also strip abjad_kabir so there's no fallback source
    clone = _strip_ids(clone, {"abjad_kabir"})
    clone["profile"]["core_numbers"] = {}
    html = render_merged_html(clone)
    assert "Your Numeric Signature" not in html
    # Rest of the page still renders
    assert ">Numerology</h2>" in html
    assert "Your Cards" in html
    assert "Your Animals" in html


def test_graceful_degradation_no_tarot(synthetic_output):
    clone = _strip_ids(synthetic_output, {"tarot_birth", "tarot_name", "cardology"})
    from merged_view import render_merged_html
    html = render_merged_html(clone)
    assert "Your Cards" not in html
    assert "Your Numeric Signature" in html
    assert "Your Animals" in html
    assert "Your Planets" in html


def test_graceful_degradation_no_animals(synthetic_output):
    clone = _strip_ids(synthetic_output, {
        "chinese_zodiac", "bazi_pillars", "bazi_daymaster",
        "nakshatra", "celtic_tree", "mayan", "temperament",
    })
    from merged_view import render_merged_html
    html = render_merged_html(clone)
    assert "Your Animals" not in html
    assert "Your Cards" in html
    assert "Your Planets" in html


def test_graceful_degradation_no_planets(synthetic_output):
    clone = _strip_ids(synthetic_output, {
        "planetary_joy", "firdaria", "vimshottari", "profection", "almuten",
    })
    from merged_view import render_merged_html
    html = render_merged_html(clone)
    assert "Your Planets" not in html
    # Animal block and others still present
    assert "Your Animals" in html
    assert "Your Cards" in html


def test_unified_view_still_renders(synthetic_output):
    """Regression guard — merged view must not have broken unified_view's
    rendering path. Both share CSS and several render_ helpers."""
    from unified_view import render_unified_html
    # Unified view expects filtered results (only allowlisted), so make a
    # filtered clone rather than reusing the merged-style fixture.
    clone = copy.deepcopy(synthetic_output)
    clone["results"] = [r for r in clone["results"] if "domain" in r]
    html = render_unified_html(clone)
    assert "<!DOCTYPE html>" in html
    assert ">Numerology</h2>" in html
    assert "Monte Carlo Evidence" in html
    # Unified view does NOT include the merged-view visual blocks
    assert "Your Numeric Signature" not in html
    assert "Your Cards" not in html


def test_f22_stringified_null_values_filtered():
    """Regression guard for F2.2 — stringified hint values (None, N/A,
    null, etc.) should be in HIDE_EXACT_VALUES so they don't leak
    through to any view."""
    from presentation import HIDE_EXACT_VALUES
    for noise in ("None", "none", "N/A", "n/a", "null", "NULL", "undefined"):
        assert noise in HIDE_EXACT_VALUES, (
            f"{noise!r} must be in HIDE_EXACT_VALUES to be filtered from views"
        )


def test_server_wires_merged_routes():
    """Smoke test: both new routes must be registered on the app."""
    import importlib.util
    server_spec = importlib.util.find_spec("server")
    server = importlib.util.module_from_spec(server_spec)
    server_spec.loader.exec_module(server)

    paths = [str(getattr(r, "path", "")) for r in server.app.routes]
    assert "/reading/{order_id}/merged" in paths
    assert "/r/{token}/merged" in paths
