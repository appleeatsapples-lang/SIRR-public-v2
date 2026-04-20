"""
SIRR Merged View Renderer
=========================
PR #18 — feat/merged-reading-view.

Unified 4-domain architecture hydrated with legacy's visual vocabulary
at each domain header. Same output.json feeds this and every other
view — template restructuring, no new computation.

Additive: this module imports CSS + render helpers from unified_view
and extractor functions from reading_generator, then adds visual-block
renderers that slot into each domain section between the domain header
and the analytical table.

The 166-tradition gallery from html_reading.py is intentionally DROPPED.
The 4 domain tables already cover that content; re-rendering them as
27 tradition sections below would duplicate. If anyone wants the old
tradition-by-tradition view, /reading/{id} still serves it.

Aesthetic: inherits unified_view's cream/rust/archival palette. Legacy
dark/gold visuals are reskinned to match — no dual-aesthetic chrome.

Visual block per domain:
  numerology        → Your Numeric Signature (6 anchor number cells)
  name_intelligence → Your Cards (3 tarot + 1 cardology playing card)
  astro_timing      → Your Animals + Your Planets
                      (BaZi year/day + 4 planets + Vimshottari bar
                       + profection badge)
  convergence       → (no visual block; Monte Carlo IS the visual)

Graceful degradation: each block is skipped if its source data is
missing (returns empty string). The domain section still renders with
just the analytical table — same as /reading/{id}/unified today.
"""
from __future__ import annotations
from typing import Dict, Any, List
import html as htmllib
import sys
import types as _types

# anthropic shim — reading_generator imports anthropic at module scope
# for narrative generation. We only need its pure extractors, so install
# a stub before import so the shared render path doesn't need the SDK.
sys.modules.setdefault("anthropic", _types.ModuleType("anthropic"))

from unified_view import (
    CSS as _UNIFIED_CSS,
    DOMAIN_LABELS, DOMAIN_SUBTITLES, DOMAIN_ORDER,
    render_header, render_portrait, render_coherence, render_patterns,
    render_theses, render_tension, render_convergences,
    _esc,
)
from presentation import (
    HIDE_EXACT_VALUES as _HIDE_EXACT_VALUES,
    ID_LABEL_REWRITES as _ID_LABEL_REWRITES,
    clean_value as _clean_value,
    resolve_display as _resolve_display,
)
from reading_generator import (
    extract_animal_profile, extract_planetary_profile, PLANET_GLYPHS,
)


# ────────────────────────────────────────────────────────────────────
# Additional CSS — visual blocks, reskinned to unified_view's palette.
# ────────────────────────────────────────────────────────────────────

VISUAL_CSS = """
/* ─── Merged-view visual blocks (cream/rust reskin of legacy) ─── */

.visual-block {
  margin: 4px 0 28px;
  padding: 0 0 24px;
}

.visual-block .block-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  margin-bottom: 20px;
  font-weight: 500;
}

/* 6-cell numeric signature — the gist of numerology as a tradition:
   Life Path / Expression / Soul Urge / Personality / Birthday / Abjad Root. */
.num-sig-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}
@media (max-width: 720px) { .num-sig-grid { grid-template-columns: repeat(3, 1fr); gap: 14px; } }
@media (max-width: 440px) { .num-sig-grid { grid-template-columns: repeat(2, 1fr); } }

.num-cell {
  text-align: center;
  padding: 14px 8px 12px;
  background: var(--bg-alt);
  border-radius: 2px;
}

.num-cell .num-value {
  font-family: 'Instrument Serif', serif;
  font-size: 36px;
  line-height: 1;
  color: var(--accent);
  font-weight: 400;
  letter-spacing: -0.02em;
}

.num-cell .num-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--muted);
  margin-top: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.num-cell .num-meaning {
  font-family: 'Newsreader', serif;
  font-style: italic;
  font-size: 11.5px;
  color: var(--fg-soft);
  margin-top: 6px;
  line-height: 1.3;
}

/* Tarot / cardology card row */
.card-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

.tarot-card, .playing-card {
  width: 118px;
  min-height: 180px;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 18px 10px 14px;
}

.tarot-card .tarot-numeral {
  font-family: 'Instrument Serif', serif;
  font-size: 15px;
  color: var(--accent);
  letter-spacing: 3px;
}

.tarot-card .tarot-glyph {
  font-size: 32px;
  margin: 14px 0;
  line-height: 1;
  color: var(--fg-soft);
}

.tarot-card .tarot-name {
  font-family: 'Newsreader', serif;
  font-size: 12.5px;
  color: var(--fg);
  text-align: center;
  line-height: 1.35;
  font-style: italic;
}

.tarot-card .tarot-label, .playing-card .playing-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--muted);
  margin-top: auto;
  padding-top: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.playing-card .playing-suit {
  font-size: 42px;
  line-height: 1;
  margin-top: 6px;
}
.playing-card .playing-suit.red { color: var(--accent); }
.playing-card .playing-suit.black { color: var(--fg); }

.playing-card .playing-rank {
  font-family: 'Instrument Serif', serif;
  font-size: 17px;
  color: var(--fg);
  margin-top: 8px;
  text-align: center;
}

/* Figure cards (animals + planets share a layout) */
.figure-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

.figure-card {
  width: 150px;
  min-height: 200px;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18px 12px 14px;
}

.figure-card .figure-glyph {
  font-size: 40px;
  line-height: 1;
  margin-bottom: 10px;
}

.figure-card .figure-name {
  font-family: 'Instrument Serif', serif;
  font-size: 17px;
  color: var(--fg);
  text-align: center;
  line-height: 1.2;
}

.figure-card .figure-detail {
  font-family: 'Newsreader', serif;
  font-size: 12.5px;
  font-style: italic;
  color: var(--fg-soft);
  margin-top: 6px;
  text-align: center;
}

.figure-card .figure-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--muted);
  margin-top: auto;
  padding-top: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  text-align: center;
}

/* Secondary info row: chips for nakshatra/celtic/mayan/temperament */
.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  padding: 5px 12px;
  border: 1px solid var(--line);
  border-radius: 20px;
  letter-spacing: 0.04em;
}

.chip strong {
  color: var(--accent);
  font-weight: 500;
}

/* Vimshottari dasha bar — 120-year timeline with current segment highlighted */
.dasha-wrap {
  margin-top: 22px;
}

.dasha-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: var(--muted);
  margin-bottom: 8px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.dasha-bar {
  display: flex;
  width: 100%;
  height: 26px;
  border: 1px solid var(--line);
  border-radius: 2px;
  overflow: hidden;
}

.dasha-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--muted);
  background: var(--bg-alt);
  border-right: 1px solid var(--line);
  text-align: center;
  padding: 0 4px;
  white-space: nowrap;
  overflow: hidden;
  letter-spacing: 0.04em;
}

.dasha-seg:last-child { border-right: none; }

.dasha-seg.current {
  background: var(--accent);
  color: var(--bg);
  font-weight: 500;
}

.dasha-here {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--accent);
  text-align: center;
  margin-top: 8px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.profection-badge {
  display: inline-block;
  margin-top: 18px;
  padding: 8px 16px;
  border: 1px solid var(--line);
  border-radius: 20px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.06em;
}

.profection-badge strong {
  color: var(--accent);
  font-weight: 500;
}

/* ─── Disclosure wrappers (PR #19 density pass) ─── */

details.more-rows {
  border-bottom: 1px solid var(--line);
}

details.more-rows > summary {
  cursor: pointer;
  padding: 12px 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.14em;
  list-style: none;
  transition: color 160ms ease;
}

details.more-rows > summary::-webkit-details-marker { display: none; }
details.more-rows > summary::marker { content: ''; }

details.more-rows > summary:hover { color: var(--accent); }
details.more-rows[open] > summary { color: var(--accent); padding-bottom: 6px; }

details.more-rows > summary .chev {
  display: inline-block;
  margin-right: 8px;
  transition: transform 160ms ease;
}

details.more-rows[open] > summary .chev { transform: rotate(90deg); }

/* Footnote disclosures below the domain sections — Monte Carlo + Three Lenses */
details.footnote {
  margin: 48px 0 24px;
  padding: 0;
}

details.footnote > summary {
  cursor: pointer;
  padding: 18px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.18em;
  list-style: none;
  text-align: center;
  transition: color 160ms ease;
}

details.footnote > summary::-webkit-details-marker { display: none; }
details.footnote > summary::marker { content: ''; }

details.footnote > summary:hover { color: var(--accent); }
details.footnote[open] > summary { color: var(--accent); border-bottom-color: var(--accent); }

details.footnote > .footnote-body {
  padding-top: 12px;
}

/* Coherence stat demoted to bottom-of-page badge */
.coherence-bottom {
  margin: 40px 0 16px;
  padding: 16px 0;
  border-top: 1px solid var(--line);
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted-faint);
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.coherence-bottom .score {
  color: var(--accent);
  font-family: 'Instrument Serif', serif;
  font-size: 16px;
  letter-spacing: 0;
  text-transform: none;
  margin: 0 4px;
}

/* ─── PR #20 hierarchy pass ─── */

/* Bridging header between visual block and receipt rows.
   Marks the tier transition: hero above, receipts below. */
.receipt-header {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--muted);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin: 8px 0 16px;
  padding: 10px 0 9px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  text-align: center;
}

/* Verdict line at top of Convergence domain — answers
   "so what actually converges most strongly here?" before the table. */
.convergence-verdict {
  margin: 0 0 28px;
  padding: 20px 24px;
  background: var(--bg-alt);
  border-left: 3px solid var(--accent);
  border-radius: 2px;
}

.convergence-verdict .verdict-lead {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-bottom: 12px;
}

.convergence-verdict .verdict-axes {
  font-family: 'Newsreader', serif;
  font-size: 15.5px;
  color: var(--fg);
  line-height: 1.9;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.convergence-verdict .verdict-axis {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-right: 10px;
}

.convergence-verdict strong {
  color: var(--accent);
  font-family: 'Instrument Serif', serif;
  font-size: 22px;
  font-weight: 400;
  margin-right: 10px;
  letter-spacing: 0;
}

.convergence-verdict .verdict-count {
  font-family: 'Newsreader', serif;
  font-style: italic;
  font-size: 13px;
  color: var(--muted);
}

/* Astro animals secondary info — consolidated inline band replacing
   the previous floating chip-row. Reduces collage feel. */
.animal-aux {
  margin-top: 18px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  font-family: 'Newsreader', serif;
  font-size: 13.5px;
  color: var(--fg-soft);
  line-height: 1.8;
}

.animal-aux .aux-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.animal-aux .aux-value {
  color: var(--fg);
  font-weight: 500;
}

.animal-aux .aux-sep {
  color: var(--line-strong);
  margin: 0 10px;
}

/* Tension pull-quote redesign — strip the decorative opening quote
   (previously rendered via ::before with no closing mate, which made
   the box look unfinished). Replace with a clean left-bordered callout. */
.tension {
  margin: 32px 0 40px !important;
  padding: 24px 28px 22px 28px !important;
  border-left: 3px solid var(--accent);
  border-radius: 2px;
  background: var(--bg-alt);
}

.tension::before { content: none !important; }

.tension.aligned { border-left-color: var(--muted); }

.tension .label { margin-bottom: 10px !important; }

.tension .sentence {
  font-size: clamp(17px, 2.6vw, 22px) !important;
  line-height: 1.5 !important;
}
"""

CSS = _UNIFIED_CSS + VISUAL_CSS


# ────────────────────────────────────────────────────────────────────
# Constants — glyphs and meaning tables. Lifted from html_reading.py
# without modification; stable mappings that have shipped in prod.
# ────────────────────────────────────────────────────────────────────

_TAROT_GLYPHS = {
    "The Fool": "🌀", "The Magician": "✦", "The High Priestess": "☽",
    "The Empress": "♛", "The Emperor": "♔", "The Hierophant": "⛧",
    "The Lovers": "❦", "The Chariot": "⚡", "Strength": "∞",
    "The Hermit": "⚹", "Wheel of Fortune": "☸", "Justice": "⚖",
    "The Hanged Man": "⊗", "Death": "☠", "Temperance": "⏳",
    "The Devil": "⛧", "The Tower": "↯", "The Star": "✧",
    "The Moon": "☾", "The Sun": "☀", "Judgement": "♆",
    "The World": "◎",
}

_TAROT_NUMERALS = {
    "The Fool": "0", "The Magician": "I", "The High Priestess": "II",
    "The Empress": "III", "The Emperor": "IV", "The Hierophant": "V",
    "The Lovers": "VI", "The Chariot": "VII", "Strength": "VIII",
    "The Hermit": "IX", "Wheel of Fortune": "X", "Justice": "XI",
    "The Hanged Man": "XII", "Death": "XIII", "Temperance": "XIV",
    "The Devil": "XV", "The Tower": "XVI", "The Star": "XVII",
    "The Moon": "XVIII", "The Sun": "XIX", "Judgement": "XX",
    "The World": "XXI",
}

_ANIMAL_GLYPHS = {
    "Rat": "🐀", "Ox": "🐂", "Tiger": "🐅", "Rabbit": "🐇",
    "Dragon": "🐉", "Snake": "🐍", "Horse": "🐎", "Goat": "🐐",
    "Monkey": "🐒", "Rooster": "🐓", "Dog": "🐕", "Pig": "🐖",
}

# The six-cell signature is the canonical gist of numerology as a tradition.
# Archetype labels follow Cheiro/Balliett consensus readings.
_ROOT_MEANINGS = {
    1: "The Initiator", 2: "The Diplomat", 3: "The Communicator",
    4: "The Builder", 5: "The Liberator", 6: "The Nurturer",
    7: "The Seeker", 8: "The Executive", 9: "The Humanitarian",
    11: "The Visionary", 22: "The Master Builder", 33: "The Master Teacher",
}


# ────────────────────────────────────────────────────────────────────
# Visual block renderers — one per domain. Each returns "" when its
# source data is missing, so the domain section degrades to the
# analytical table alone.
# ────────────────────────────────────────────────────────────────────

def _num_cell(value, label: str) -> str:
    """Single cell of the Numeric Signature grid."""
    if value is None or str(value).strip() in ("", "—", "-", "?"):
        v = "—"
        meaning = ""
    else:
        v = str(value)
        meaning = ""
        try:
            v_int = int(v)
            if v_int in _ROOT_MEANINGS:
                meaning = _ROOT_MEANINGS[v_int]
        except (ValueError, TypeError):
            pass
    meaning_html = f'<div class="num-meaning">{_esc(meaning)}</div>' if meaning else ""
    return f"""
      <div class="num-cell">
        <div class="num-value">{_esc(v)}</div>
        <div class="num-label">{_esc(label)}</div>
        {meaning_html}
      </div>"""


def render_numerology_signature(core: Dict[str, Any], abjad_data: Dict[str, Any]) -> str:
    """The six anchor numbers: Life Path, Expression, Soul Urge, Personality,
    Birthday, Abjad Root. Skipped entirely if core_numbers is missing."""
    if not core or not isinstance(core, dict):
        return ""
    lp = core.get("life_path")
    expr = core.get("expression")
    su = core.get("soul_urge")
    pers = core.get("personality")
    bday = core.get("birthday")
    # Abjad Root: prefer engine-computed abjad_kabir.root, fall back to
    # core_numbers.abjad_first reduced to a root if needed.
    abjad_root = None
    if isinstance(abjad_data, dict):
        abjad_root = abjad_data.get("root")
    if abjad_root is None:
        abjad_root = core.get("abjad_first")

    cells = [
        _num_cell(lp, "Life Path"),
        _num_cell(expr, "Expression"),
        _num_cell(su, "Soul Urge"),
        _num_cell(pers, "Personality"),
        _num_cell(bday, "Birthday"),
        _num_cell(abjad_root, "Abjad Root"),
    ]
    return f"""
    <section class="visual-block">
      <div class="block-title">Your Numeric Signature</div>
      <div class="num-sig-grid">{"".join(cells)}</div>
    </section>
    """


def _tarot_card_html(card_name: str, label: str) -> str:
    """Render a single tarot card. Returns empty string if no card name."""
    if not card_name or not isinstance(card_name, str):
        return ""
    glyph = _TAROT_GLYPHS.get(card_name, "✦")
    numeral = _TAROT_NUMERALS.get(card_name, "")
    numeral_html = f'<div class="tarot-numeral">{_esc(numeral)}</div>' if numeral else ""
    label_html = f'<div class="tarot-label">{_esc(label)}</div>' if label else ""
    return f"""
      <div class="tarot-card">
        {numeral_html}
        <div class="tarot-glyph">{glyph}</div>
        <div class="tarot-name">{_esc(card_name)}</div>
        {label_html}
      </div>"""


def _playing_card_html(cardology_data: Dict[str, Any]) -> str:
    """Render the cardology playing card. Returns empty string if no birth_card."""
    if not cardology_data or not cardology_data.get("birth_card"):
        return ""
    suit = cardology_data.get("suit", "")
    rank = cardology_data.get("rank", "")
    suit_sym = {"Clubs": "♣", "Hearts": "♥", "Diamonds": "♦", "Spades": "♠"}.get(suit, "♣")
    suit_color = "red" if suit in ("Hearts", "Diamonds") else "black"
    return f"""
      <div class="playing-card">
        <div class="playing-suit {suit_color}">{suit_sym}</div>
        <div class="playing-rank">{_esc(rank)} of {_esc(suit)}</div>
        <div class="playing-label">Birth Card</div>
      </div>"""


def render_name_cards(results_idx: Dict[str, Dict]) -> str:
    """Your Cards: birth-card + shadow-card (tarot_birth), expression-card
    (tarot_name), and cardology playing card. Whichever subset is present
    renders; the block is only skipped if ALL four are absent."""
    tarot_birth = results_idx.get("tarot_birth", {}).get("data", {}) or {}
    tarot_name = results_idx.get("tarot_name", {}).get("data", {}) or {}
    cardology = results_idx.get("cardology", {}).get("data", {}) or {}

    cards = []
    if tarot_birth.get("primary_card_name"):
        cards.append(_tarot_card_html(tarot_birth["primary_card_name"], "Birth Card"))
    if tarot_birth.get("secondary_card_name"):
        cards.append(_tarot_card_html(tarot_birth["secondary_card_name"], "Shadow Card"))
    if tarot_name.get("expression_card_name"):
        cards.append(_tarot_card_html(tarot_name["expression_card_name"], "Expression"))
    playing = _playing_card_html(cardology)
    if playing:
        cards.append(playing)

    cards = [c for c in cards if c]
    if not cards:
        return ""

    return f"""
    <section class="visual-block">
      <div class="block-title">Cards Derived from Your Name</div>
      <div class="card-row">{"".join(cards)}</div>
    </section>
    """


def _animal_card_html(animal_name: str, element: str, polarity: str, pillar_label: str) -> str:
    if not animal_name:
        return ""
    glyph = _ANIMAL_GLYPHS.get(animal_name, "✦")
    elem_parts = [p for p in (element, polarity) if p]
    elem_str = " · ".join(elem_parts)
    detail_html = f'<div class="figure-detail">{_esc(elem_str)}</div>' if elem_str else ""
    return f"""
      <div class="figure-card">
        <div class="figure-glyph">{glyph}</div>
        <div class="figure-name">{_esc(animal_name)}</div>
        {detail_html}
        <div class="figure-label">{_esc(pillar_label)}</div>
      </div>"""


def render_astro_animals(animal: Dict[str, Any]) -> str:
    """Your Animals: BaZi year + day pillars as animal cards, with a
    supporting chip row for nakshatra animal, celtic tree, mayan sign,
    and temperament. Skipped if no primary year animal."""
    if not animal or not isinstance(animal, dict):
        return ""
    year_animal = animal.get("year_animal") or animal.get("animal")
    if not year_animal:
        return ""

    year_element = animal.get("year_element") or animal.get("element")
    year_polarity = animal.get("polarity")
    day_animal = animal.get("day_animal")
    day_element = animal.get("day_element")

    cards = [_animal_card_html(year_animal, year_element, year_polarity, "Year · Public Self")]
    if day_animal and day_animal != year_animal:
        cards.append(_animal_card_html(day_animal, day_element, None, "Day · True Self"))

    # Secondary symbols — consolidated into one inline band below the
    # primary animals. Previously four floating chips; the chip shapes
    # created a "collage" feel (PR #20 hierarchy pass).
    aux_defs = [
        ("Vedic", animal.get("nakshatra_animal")),
        ("Celtic", animal.get("celtic_tree")),
        ("Mayan", animal.get("mayan_sign")),
        ("Temperament", animal.get("temperament_type")),
    ]
    aux_parts = [
        f'<span class="aux-label">{_esc(label)}</span> '
        f'<span class="aux-value">{_esc(value)}</span>'
        for label, value in aux_defs
        if value
    ]
    if aux_parts:
        sep = ' <span class="aux-sep">·</span> '
        aux_row_html = f'<div class="animal-aux">{sep.join(aux_parts)}</div>'
    else:
        aux_row_html = ""

    return f"""
    <section class="visual-block">
      <div class="block-title">Your Animals</div>
      <div class="figure-row">{"".join(cards)}</div>
      {aux_row_html}
    </section>
    """


def _planet_card_html(glyph_str: str, name: str, status: str, sub: str) -> str:
    if not name:
        return ""
    sub_html = f'<div class="figure-detail">{sub}</div>' if sub else ""
    return f"""
      <div class="figure-card">
        <div class="figure-glyph" style="color:var(--accent);">{glyph_str}</div>
        <div class="figure-name">{_esc(name)}</div>
        <div class="figure-detail" style="color:var(--muted);">{_esc(status)}</div>
        {sub_html}
      </div>"""


def _dasha_bar_html(timeline: List[Dict], current_dasha: str, vedic_range: str) -> str:
    """Vimshottari 120-year timeline as a proportional bar with the current
    mahadasha segment highlighted. Skipped if no timeline data."""
    if not timeline or not current_dasha:
        return ""
    total = sum((seg.get("years") or 0) for seg in timeline) or 1
    segs = []
    for seg in timeline:
        p = seg.get("planet", "?")
        yrs = seg.get("years") or 0
        glyph = PLANET_GLYPHS.get(p, "")
        width_pct = (yrs / total) * 100
        cls = "dasha-seg current" if p == current_dasha else "dasha-seg"
        label = f"{glyph} {p}" if width_pct > 6 else glyph
        segs.append(f'<div class="{cls}" style="flex:{yrs}">{_esc(label)}</div>')
    here_text = f"Currently in {current_dasha}" + (f" ({vedic_range})" if vedic_range else "")
    return f"""
    <div class="dasha-wrap">
      <div class="dasha-label">Vimshottari Dasha Timeline</div>
      <div class="dasha-bar">{"".join(segs)}</div>
      <div class="dasha-here">{_esc(here_text)}</div>
    </div>"""


def render_astro_planets(planet: Dict[str, Any]) -> str:
    """Your Planets: joy planet, firdaria period, current Vedic mahadasha,
    birth nakshatra ruler — plus the 120-year Vimshottari bar and the
    current profection-year badge. Skipped only if neither a joy planet
    nor a firdaria is present."""
    if not planet or not isinstance(planet, dict):
        return ""
    has_joy = bool(planet.get("primary_joy_planet"))
    has_firdaria = bool(planet.get("firdaria_major"))
    if not has_joy and not has_firdaria:
        return ""

    # Joy card
    joy_planet = planet.get("primary_joy_planet") or "—"
    joy_glyph = PLANET_GLYPHS.get(joy_planet, "✦")
    joy_details = (planet.get("joy_details") or {}).get(joy_planet, {}) or {}
    joy_house = joy_details.get("joy_house")
    joy_rationale = joy_details.get("rationale", "") or ""
    if " — " in joy_rationale:
        joy_rationale = joy_rationale.split(" — ", 1)[1]
    joy_sub = f"House {joy_house} — {joy_rationale}" if joy_house else joy_rationale

    cards = [_planet_card_html(joy_glyph, joy_planet, "In Joy", joy_sub)]


    # Firdaria card
    firdaria_major = planet.get("firdaria_major") or ""
    firdaria_sub = planet.get("firdaria_sub") or ""
    if firdaria_major:
        firdaria_combined = planet.get("firdaria_combined") or f"{firdaria_major}/{firdaria_sub}"
        firdaria_range = planet.get("firdaria_period_range") or ""
        glyph_major = PLANET_GLYPHS.get(firdaria_major, "")
        glyph_sub = PLANET_GLYPHS.get(firdaria_sub, "")
        firdaria_glyph = f"{glyph_major}{glyph_sub}"
        firdaria_sub_text = f"Period {firdaria_range}" if firdaria_range else "Current phase"
        cards.append(_planet_card_html(
            firdaria_glyph, firdaria_combined, "Firdaria", firdaria_sub_text
        ))

    # Vedic current mahadasha
    vedic_dasha = planet.get("vedic_current_dasha") or ""
    vedic_start = planet.get("vedic_dasha_start")
    vedic_end = planet.get("vedic_dasha_end")
    vedic_range = ""
    if vedic_start is not None and vedic_end is not None:
        try:
            vedic_range = f"age {float(vedic_start):.0f}–{float(vedic_end):.0f}"
        except (TypeError, ValueError):
            vedic_range = ""
    if vedic_dasha:
        cards.append(_planet_card_html(
            PLANET_GLYPHS.get(vedic_dasha, ""),
            vedic_dasha, "Vedic Mahadasha", vedic_range
        ))

    # Birth-nakshatra ruler
    birth_ruler = planet.get("nakshatra_ruler") or ""
    nak_name = planet.get("nakshatra_name") or ""
    if birth_ruler:
        cards.append(_planet_card_html(
            PLANET_GLYPHS.get(birth_ruler, ""),
            birth_ruler, "Birth Ruler", nak_name
        ))

    # Vimshottari bar + profection badge
    timeline = planet.get("vedic_timeline") or []
    bar_html = _dasha_bar_html(timeline, vedic_dasha, vedic_range)

    prof_house = planet.get("profection_house")
    prof_info = planet.get("profection_info") or ""
    prof_html = ""
    if prof_house:
        prof_html = (
            f'<div style="text-align:center;">'
            f'<div class="profection-badge">Profection · '
            f'<strong>House {_esc(prof_house)}</strong> · {_esc(prof_info)}'
            f'</div></div>'
        )

    return f"""
    <section class="visual-block">
      <div class="block-title">Your Planets</div>
      <div class="figure-row">{"".join(cards)}</div>
      {bar_html}
      {prof_html}
    </section>
    """


# ────────────────────────────────────────────────────────────────────
# Domain wrapper — replicates unified_view.render_domain but takes the
# full output dict so it can inject the visual block between the
# domain header and the analytical table.
#
# Reimplementing instead of monkey-patching keeps unified_view untouched
# and the seam explicit. ~30 lines of near-duplication is worth the
# zero-regression-risk to /reading/{id}/unified.
# ────────────────────────────────────────────────────────────────────

def _render_convergence_verdict(synth: Dict[str, Any]) -> str:
    """One-sentence verdict at the top of the Convergence domain.

    Reads the top entries from number / element / timing convergences
    and composes a scannable verdict line. PR #20: answers "so what
    actually converges most strongly here?" before the receipts.
    """
    if not synth or not isinstance(synth, dict):
        return ""
    parts = []
    number_convs = synth.get("number_convergences") or []
    if number_convs and isinstance(number_convs, list) and number_convs[0].get("number") is not None:
        top = number_convs[0]
        num = top["number"]
        sys_ct = top.get("system_count", 0)
        grp_ct = top.get("group_count", 0)
        parts.append(
            f'<span class="verdict-axis">Number</span> '
            f'<strong>{_esc(str(num))}</strong> '
            f'<span class="verdict-count">{sys_ct} systems · {grp_ct} cultural groups</span>'
        )
    elem_convs = synth.get("element_convergences") or []
    if elem_convs and isinstance(elem_convs, list) and elem_convs[0].get("element"):
        top = elem_convs[0]
        elem = top["element"]
        sys_ct = top.get("system_count", 0)
        grp_ct = top.get("group_count", 0)
        parts.append(
            f'<span class="verdict-axis">Element</span> '
            f'<strong>{_esc(elem)}</strong> '
            f'<span class="verdict-count">{sys_ct} systems · {grp_ct} groups</span>'
        )
    time_convs = synth.get("timing_convergences") or []
    if time_convs and isinstance(time_convs, list) and time_convs[0].get("number") is not None:
        top = time_convs[0]
        num = top["number"]
        sys_ct = top.get("system_count", 0)
        grp_ct = top.get("group_count", 0)
        parts.append(
            f'<span class="verdict-axis">Timing</span> '
            f'<strong>{_esc(str(num))}</strong> '
            f'<span class="verdict-count">{sys_ct} systems · {grp_ct} groups</span>'
        )
    if not parts:
        return ""
    return (
        '<div class="convergence-verdict">'
        '<div class="verdict-lead">These traditions converge most strongly on:</div>'
        '<div class="verdict-axes">' + "".join(parts) + "</div>"
        "</div>"
    )


def _visual_block_for_domain(domain_id: str, output: Dict[str, Any]) -> str:
    """Dispatch to the correct renderer for this domain, or empty string."""
    if domain_id == "numerology":
        profile = output.get("profile", {}) or {}
        core = profile.get("core_numbers", {}) or {}
        results_idx = {r["id"]: r for r in output.get("results", []) if "id" in r}
        abjad_data = (results_idx.get("abjad_kabir", {}) or {}).get("data", {}) or {}
        return render_numerology_signature(core, abjad_data)

    if domain_id == "name_intelligence":
        results_idx = {r["id"]: r for r in output.get("results", []) if "id" in r}
        return render_name_cards(results_idx)

    if domain_id == "astro_timing":
        animal = extract_animal_profile(output)
        planet = extract_planetary_profile(output)
        return render_astro_animals(animal) + render_astro_planets(planet)

    if domain_id == "convergence":
        # PR #20: verdict sentence in place of a visual block.
        # Answers "so what actually converges most strongly here?" before
        # the user wades into the receipt rows.
        synth = output.get("synthesis", {}) or {}
        return _render_convergence_verdict(synth)

    return ""


def render_domain_merged(
    domain_id: str,
    results: List[Dict[str, Any]],
    output: Dict[str, Any],
    subject: str = "",
    subject_ar: str = "",
    visible_rows: int = 6,
) -> str:
    """Render one domain section: visual block + analytical table.

    PR #19 density pass: first `visible_rows` rows show inline, any
    additional rows are hidden behind a "Show all N signals" disclosure.
    Cap lowered from 12 to 6 — with the visual block already carrying
    substantial weight at the top of the section, 6 analytical rows is
    where the reader still has capacity for the signal.

    Mirrors unified_view.render_domain's row logic otherwise.
    """
    label = DOMAIN_LABELS[domain_id]
    subtitle = DOMAIN_SUBTITLES[domain_id]
    visual_html = _visual_block_for_domain(domain_id, output)

    domain_results = [r for r in results if r.get("domain") == domain_id]
    tier_order = {"HERO": 0, "STANDARD": 1, "COMPRESSED": 2}
    domain_results.sort(key=lambda r: (
        tier_order.get(r.get("tier", "COMPRESSED"), 3),
        r.get("id", ""),
    ))

    rows: List[str] = []
    for r in domain_results:
        display_value = _resolve_display(r, subject, subject_ar)
        if display_value is None:
            continue
        rid = r.get("id", "")
        if rid in _ID_LABEL_REWRITES:
            name = _ID_LABEL_REWRITES[rid]
        else:
            name = r.get("name", rid)
            if " (" in name and name.endswith(")"):
                name = name.split(" (", 1)[0]
        display_value = _clean_value(display_value)
        value_html = _esc(display_value)

        interp = r.get("interpretation")
        interp_clean = interp.strip() if isinstance(interp, str) else ""
        has_interp = bool(interp_clean) and interp_clean.lower() != "none" and len(interp_clean) >= 20

        if has_interp:
            rows.append(
                f'<details class="row">'
                f'<summary>'
                f'<span class="name">{_esc(name)}</span>'
                f'<span class="value">{value_html}</span>'
                f'<span class="caret" aria-hidden="true">›</span>'
                f'</summary>'
                f'<div class="interp-panel">{_esc(interp_clean)}</div>'
                f'</details>'
            )
        else:
            rows.append(
                f'<div class="plain-row">'
                f'<span class="name">{_esc(name)}</span>'
                f'<span class="value">{value_html}</span>'
                f'<span class="caret-placeholder" aria-hidden="true"></span>'
                f'</div>'
            )

    # PR #19: split into always-visible + overflow-in-disclosure.
    # No hard cap — every qualifying row is reachable, just not
    # always pre-rendered on the page.
    if not rows:
        body_rows = '<div class="domain-empty">No signals to surface in this domain yet.</div>'
        receipt_header_html = ""
    else:
        visible = rows[:visible_rows]
        hidden = rows[visible_rows:]
        body_rows = "".join(visible)
        if hidden:
            body_rows += (
                f'<details class="more-rows">'
                f'<summary><span class="chev">›</span>'
                f'Show all {len(rows)} signals · +{len(hidden)} more'
                f'</summary>'
                f'{"".join(hidden)}'
                f'</details>'
            )
        # PR #20: bridging label between the hero visual and the
        # receipt rows. Explicit tier marker: the block above is the
        # synthesized signal, the rows below are the per-tradition
        # receipts that support it.
        receipt_header_html = (
            '<div class="receipt-header">How each tradition reads this</div>'
            if visual_html.strip() else ""
        )

    return f"""
    <section class="domain">
      <div class="domain-header">
        <div>
          <h2>{label}</h2>
          <div class="subtitle">{subtitle}</div>
        </div>
      </div>
      {visual_html}
      {receipt_header_html}
      {body_rows}
    </section>
    """


# ────────────────────────────────────────────────────────────────────
# Top-level entry point
# ────────────────────────────────────────────────────────────────────

def render_merged_html(output: Dict[str, Any]) -> str:
    """Render the merged view as a complete HTML document.

    Page order (same as unified_view, with merged-domain sections in
    place of the plain analytical domains):

      1. Header
      2. Portrait (reading + hierarchy triangle)
      3. Coherence stat
      4. Patterns detected
      5. Civilizational theses
      6. Primary tension
      7. Evidence intro
      8. Domain sections — each with its visual block + analytical table
      9. Convergence counts (Monte Carlo)
      10. Footer
    """
    profile = output.get("profile", {}) or {}
    unified = output.get("unified", {}) or {}
    synth = output.get("synthesis", {}) or {}
    results = output.get("results", []) or []
    subject = profile.get("subject", "") or ""
    subject_ar = profile.get("arabic", "") or ""

    # PR #19 density pass: top of the page is the reading, not scaffolding.
    # Removed from top flow: coherence stat, three civilizational lenses,
    # evidence-intro paragraph. Those still render but now sit below the
    # domain sections as disclosures.
    body_parts = [
        render_header(profile),
        render_portrait(output),
        render_tension(unified),
        render_patterns(output),
    ]

    # Four domain sections — each with visual block + up to 6 rows +
    # overflow disclosure for the rest.
    for domain_id in DOMAIN_ORDER:
        body_parts.append(render_domain_merged(
            domain_id, results, output, subject=subject, subject_ar=subject_ar
        ))

    # Demoted footnotes. All three still render, but closed by default.
    convergences_html = render_convergences(synth)
    if convergences_html:
        body_parts.append(
            '<details class="footnote">'
            '<summary>Monte Carlo Receipts &nbsp;·&nbsp; Evidence behind the convergence</summary>'
            f'<div class="footnote-body">{convergences_html}</div>'
            '</details>'
        )

    theses_html = render_theses(output)
    if theses_html:
        body_parts.append(
            '<details class="footnote">'
            '<summary>Three Civilizational Lenses &nbsp;·&nbsp; Islamic · Kabbalistic · Chinese</summary>'
            f'<div class="footnote-body">{theses_html}</div>'
            '</details>'
        )

    # Coherence score demoted to a single-line bottom badge — a QC metric,
    # not part of the reading. render_coherence returns "" when score is
    # absent, which naturally hides the badge too.
    coh = unified.get("coherence", {}) or {}
    score = coh.get("score")
    label_c = coh.get("label")
    if score and isinstance(score, (int, float)) and score > 0 and label_c and str(label_c).strip() not in ("", "—", "None"):
        body_parts.append(
            '<div class="coherence-bottom">'
            f'Coherence <span class="score">{int(score)}</span> · {_esc(label_c)}'
            '</div>'
        )

    subject_title = _esc(subject).title()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SIRR · {subject_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital,wght@0,400;1,400&family=Newsreader:ital,wght@0,300;0,400;0,500;1,300;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>
  <main class="container">
    {"".join(body_parts)}
    <footer>
      SIRR ENGINE · SWISS EPHEMERIS · MONTE CARLO BASELINE N=10,000
    </footer>
  </main>
</body>
</html>
"""
