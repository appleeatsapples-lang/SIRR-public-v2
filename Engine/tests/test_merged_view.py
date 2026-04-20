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


# ─────────────────────────────────────────────────────────────
# PR #19 density pass — guards on the disclosure behavior
# ─────────────────────────────────────────────────────────────


def test_top_flow_has_no_coherence_or_theses_or_evidence_intro(synthetic_output):
    """PR #19: top-of-page scaffolding is removed. Coherence, Three
    Civilizational Lenses, and the Evidence Intro paragraph must NOT
    appear before the first domain section. They still render below,
    but the top of the page is reserved for the reading itself."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    first_domain = html.find("<h2>Numerology</h2>")
    assert first_domain > 0, "Numerology domain header missing"
    top = html[:first_domain]
    # These classes may appear later in the HTML (theses inside footnote
    # disclosure, etc.) but must not be in the top region.
    assert 'class="coherence-stat"' not in top, "Coherence top stat should be demoted"
    assert 'class="evidence-intro"' not in top, "Evidence intro should be gone"
    assert 'class="theses"' not in top, "Theses should be demoted to footnote"


def test_top_flow_order(synthetic_output):
    """First-screen ordering: portrait → tension → patterns → domains."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    # tension may or may not fire depending on fixture — just check relative
    # order for the elements that are always present.
    portrait_idx = html.find('class="portrait"')
    patterns_idx = html.find('class="patterns"')
    numerology_idx = html.find("<h2>Numerology</h2>")
    assert 0 < portrait_idx < patterns_idx < numerology_idx


def test_rows_overflow_hidden_behind_disclosure(synthetic_output):
    """Domains with more than 6 qualifying rows must emit a
    'Show all N signals · +M more' disclosure instead of a hard cap."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    # Synthetic profile has plenty of rows in each domain, so at least
    # one overflow disclosure must be present.
    assert html.count('class="more-rows"') >= 1
    # The summary label uses this specific phrasing — regression-guard it
    assert "Show all" in html
    assert "more" in html
    assert "signals" in html


def test_first_six_rows_visible_per_domain(synthetic_output):
    """Inside a domain with >6 rows, the first 6 must render OUTSIDE
    the overflow disclosure (visible by default), not inside it."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    # Find the first <section class="domain"> block that has an overflow
    # disclosure, then split on the <details> and count visible rows
    # before it.
    start = html.find('class="more-rows"')
    assert start > 0, "no overflow disclosure found — fixture too small?"
    # Walk backwards to the enclosing <section class="domain">
    section_start = html.rfind('<section class="domain">', 0, start)
    assert section_start >= 0
    visible_region = html[section_start:start]
    # Each row is either <details class="row"> or <div class="plain-row">
    visible_rows = (
        visible_region.count('<details class="row">') +
        visible_region.count('<div class="plain-row">')
    )
    assert visible_rows == 6, f"expected 6 visible rows, got {visible_rows}"


def test_monte_carlo_wrapped_in_footnote_disclosure(synthetic_output):
    """Monte Carlo receipts must be closed-by-default below the domain sections."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    assert "Monte Carlo Receipts" in html
    # Must be inside a footnote disclosure
    mc_idx = html.find("Monte Carlo Receipts")
    enclosing_details = html.rfind('<details class="footnote">', 0, mc_idx)
    assert enclosing_details >= 0, "Monte Carlo not wrapped in footnote disclosure"
    # Content (Monte Carlo Evidence label from render_convergences) is
    # inside the disclosure body, reachable when expanded
    assert "Monte Carlo Evidence" in html


def test_coherence_demoted_to_bottom_badge(synthetic_output):
    """Coherence stat is now a single-line bottom badge, not a top hero."""
    from merged_view import render_merged_html
    html = render_merged_html(synthetic_output)
    # New badge class is present
    assert 'class="coherence-bottom"' in html
    # And it appears AFTER all domain sections
    bottom_idx = html.find('class="coherence-bottom"')
    last_domain_idx = html.rfind("<h2>Convergence</h2>")
    assert last_domain_idx > 0 and bottom_idx > last_domain_idx


def test_unified_view_untouched_by_density_pass(synthetic_output):
    """Regression guard: the density pass applies ONLY to merged_view.
    unified_view must still render with its full scaffolding."""
    import copy
    from unified_view import render_unified_html
    clone = copy.deepcopy(synthetic_output)
    clone["results"] = [r for r in clone["results"] if "domain" in r]
    html = render_unified_html(clone)
    # Top flow scaffolding is still there in unified view
    assert 'class="evidence-intro"' in html or "Underlying Signals" in html
    # And there's no "more-rows" or "footnote" disclosure — unified is unchanged
    assert 'class="more-rows"' not in html
    assert 'class="footnote"' not in html
