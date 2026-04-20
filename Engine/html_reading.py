#!/usr/bin/env python3
"""
SIRR Visual Reading v6 — All-Card Gallery
==========================================
Every module is a card. Every card shows its value beautifully.
No prose essays. Grouped by tradition.

Usage:
    python html_reading.py output.json output_reading_en.md [--out file.html]
"""
from __future__ import annotations
import json, sys, re, uuid, html as html_mod
from pathlib import Path
from datetime import datetime
from presentation import (
    resolve_display, format_primary_value, _is_name_echo, clean_value,
    ID_VALUE_BUILDERS, ID_LABEL_REWRITES, ALWAYS_HIDE_IDS,
    HIDE_EXACT_VALUES, PLACEHOLDER_RE, META_SKIP, _PRIMARY_SKIP,
)
# Import helpers from reading_generator, bypassing its anthropic dependency
import importlib, importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "reading_generator",
    str(Path(__file__).parent / "reading_generator.py"),
    submodule_search_locations=[],
)
# Patch anthropic import before loading
import types as _types
_fake_anthropic = _types.ModuleType("anthropic")
_fake_anthropic.Anthropic = None
sys.modules.setdefault("anthropic", _fake_anthropic)
_rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rg)
extract_animal_profile = _rg.extract_animal_profile
extract_planetary_profile = _rg.extract_planetary_profile
PLANET_GLYPHS = _rg.PLANET_GLYPHS

# ── Tradition groupings (display order) ──
TRADITION_MAP = {
    "Islamic / Arabic": [
        "abjad_kabir", "abjad_saghir", "abjad_wusta", "abjad_maghribi",
        "elemental_letters", "luminous_dark", "solar_lunar", "wafq", "hijri",
        "manazil", "geomancy", "taksir", "bast_kasr", "istikhara_adad",
        "zakat_huruf", "jafr", "buduh", "persian_abjad", "tasyir", "zairja",
        "arabic_roots", "arabic_morphology", "name_semantics", "arabic_phonetics",
        "arabic_letter_nature", "abjad_visual_architecture", "calligraphy_structure",
        "divine_breath", "letter_position_encoding", "arabic_rhetoric",
        "hijri_calendar_encoding", "larger_awfaq", "qibla_as_axis",
        "prayer_times_as_timing",
    ],
    "Western Numerology": [
        "attitude", "bridges", "challenges", "chaldean", "compound",
        "cornerstone", "essence", "hidden_passion", "karmic_debt",
        "life_purpose", "maturity", "personal_year", "pinnacles",
        "subconscious_self", "enneagram_dob", "steiner_cycles", "latin_ordinal",
        "enneagram_deeper", "balance_number", "rational_thought",
        "inclusion_table", "special_letters", "period_cycles", "transit_letters",
        "yearly_essence_cycle", "minor_numbers", "planes_of_expression",
    ],
    "Western Astrology": [
        "natal_chart", "house_system", "aspects", "decan", "dwad",
        "profection", "sabian", "firdaria", "temperament", "declinations",
        "midpoints", "harmonic_charts", "solar_arc", "solar_return",
        "progressions", "fixed_stars", "uranian", "astrocartography",
        "draconic_chart", "solar_return_deep", "electional_windows",
        "rectification", "horary_timing", "muhurta", "synastry",
        "prenatal_syzygy",
    ],
    "Vedic": [
        "nakshatra", "vedic_tithi", "vedic_yoga", "vimshottari",
        "yogini_dasha", "ashtottari_dasha", "shadbala", "ashtakavarga",
        "shodashavarga", "kalachakra_dasha", "chara_dasha", "sarvatobhadra",
        "kp_system", "nadi_amsa", "sudarshana", "prashna_natal",
        "kala_sarpa_check", "panchamahabhuta", "ayurvedic_constitution",
        "mantra_seed_syllable", "vedic_gem_prescription", "jaimini_karakas",
        "jaimini_argala", "jaimini_navamsha", "kp_sublords",
        "tamil_panchapakshi", "vedic_arudha_pada", "vedic_upapada_lagna",
        "vedic_pushkara_navamsha",
    ],
    "Chinese": [
        "bazi_pillars", "bazi_growth", "bazi_daymaster", "bazi_luck_pillars",
        "bazi_hidden_stems", "bazi_ten_gods", "bazi_combos", "bazi_shensha",
        "chinese_zodiac", "flying_star", "nayin", "nine_star_ki",
        "lo_shu_grid", "iching", "bazhai", "meihua", "zi_wei_dou_shu",
        "qimen", "liu_ren", "taiyi", "bazi_10_year_forecast",
        "zi_wei_deeper", "four_pillars_balance", "chinese_jian_chu",
        "bazi_san_he_san_hui", "zwds_si_hua_palace",
    ],
    "Hellenistic": [
        "essential_dignities", "sect", "arabic_parts", "antiscia",
        "reception", "zodiacal_releasing", "dorothean_chronocrators",
        "bonification", "primary_directions", "almuten", "tajika",
    ],
    "Hebrew / Kabbalistic": [
        "hebrew_gematria", "hebrew_calendar", "atbash", "albam", "avgad",
        "notarikon", "tree_of_life", "gematria_word_matches",
        "sephirotic_path_analysis", "solomonic_correspondences",
        "hebrew_aiq_beker", "hebrew_mispar_variants",
    ],
    "Tarot": [
        "tarot_birth", "tarot_year", "tarot_name", "cardology",
        "tarot_greer_birth_cards", "greer_zodiac_card",
    ],
    "Gematria Battery": [
        "greek_isopsephy", "coptic_isopsephy", "armenian_gematria",
        "georgian_gematria", "agrippan", "thelemic_gematria",
        "trithemius", "mandaean_gematria", "malwasha",
    ],
    "Calendar / Cycle": [
        "julian", "biorhythm", "day_ruler", "planetary_hours", "god_of_day",
    ],
    "Scripture": [
        "quranic_figures", "torah_figures", "nt_figures", "cross_scripture",
    ],
    "African": [
        "ifa", "ethiopian_asmat", "akan_kra_din",
        "african_day_name_extended", "igbo_market_day",
    ],
    "Celtic / Norse": ["celtic_tree", "ogham", "birth_rune"],
    "Tibetan": ["tibetan_mewa", "tibetan_parkha", "tibetan_elements"],
    "Mesoamerican": ["mayan", "dreamspell", "tonalpohualli"],
    "Southeast Asian": ["pawukon", "primbon", "weton", "planetary_joy", "mahabote"],
    "Japanese": ["onmyodo"],
    "Polynesian": ["maramataka"],
    "Egyptian": ["egyptian_decan"],
    "Babylonian": ["babylonian_horoscope"],
    "Zoroastrian": ["zoroastrian_day_yazata"],
    "Western Esoteric": [
        "rose_cross_sigil", "planetary_kameas", "ars_magna",
        "gd_correspondences", "hermetic_alignment", "hermetic_element_balance",
        "roman_chronogram", "cheiro_extensions",
    ],
    "Human Design / Gene Keys": ["human_design", "gene_keys"],
    "Scientific": ["circadian_medicine", "seasonal_psychology", "chronobiology"],
    "Structural / Comparative": [
        "digit_patterns", "lineage_computation", "name_weight",
        "sonority_curve", "void_matrix", "barzakh_coefficient",
        "execution_pattern_analysis", "minimum_viable_signature",
    ],
    "Bridge / Consensus": [
        "element_consensus", "timing_consensus",
        "planetary_ruler_consensus", "archetype_consensus",
    ],
}

# Tradition accent colors (border-left color)
TRADITION_COLORS = {
    "Islamic / Arabic": "#2D8B5E",
    "Western Numerology": "#B8860B",
    "Western Astrology": "#6E63C8",
    "Vedic": "#C9644C",
    "Chinese": "#B22222",
    "Hellenistic": "#6E63C8",
    "Hebrew / Kabbalistic": "#3D7AB8",
    "Tarot": "#8B4C8B",
    "Gematria Battery": "#4DB8B8",
    "Calendar / Cycle": "#B8860B",
    "Scripture": "#2D8B5E",
    "African": "#C9A84C",
    "Celtic / Norse": "#5E8B3D",
    "Tibetan": "#B85C4C",
    "Mesoamerican": "#8B6914",
    "Southeast Asian": "#4C8B7A",
    "Japanese": "#B22222",
    "Polynesian": "#3D7AB8",
    "Egyptian": "#C9A84C",
    "Babylonian": "#8B6914",
    "Zoroastrian": "#C9644C",
    "Western Esoteric": "#6E63C8",
    "Human Design / Gene Keys": "#4DB8B8",
    "Scientific": "#5E8B3D",
    "Structural / Comparative": "#7A7060",
    "Bridge / Consensus": "#B8860B",
}

# Tradition icon glyphs
TRADITION_ICONS = {
    "Islamic / Arabic": "ع",
    "Western Numerology": "∑",
    "Western Astrology": "☉",
    "Vedic": "ॐ",
    "Chinese": "卦",
    "Hellenistic": "☿",
    "Hebrew / Kabbalistic": "א",
    "Tarot": "🃏",
    "Gematria Battery": "Σ",
    "Calendar / Cycle": "⏳",
    "Scripture": "📖",
    "African": "ꕥ",
    "Celtic / Norse": "ᚠ",
    "Tibetan": "☸",
    "Mesoamerican": "𝌆",
    "Southeast Asian": "🏵",
    "Japanese": "陰",
    "Polynesian": "🌊",
    "Egyptian": "𓂀",
    "Babylonian": "𒀭",
    "Zoroastrian": "🔥",
    "Western Esoteric": "✦",
    "Human Design / Gene Keys": "⬡",
    "Scientific": "🧬",
    "Structural / Comparative": "◈",
    "Bridge / Consensus": "⟐",
}


def _esc(s):
    """HTML-escape a string."""
    if s is None:
        return ""
    return html_mod.escape(str(s))


def _truncate_interp(text: str, max_sentences: int = 2) -> str:
    """Truncate interpretation to max_sentences."""
    if not text:
        return ""
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = " ".join(sentences[:max_sentences])
    if len(result) > 200:
        result = result[:197] + "..."
    return result


def _extract_primary_value(data: dict, result: dict = None, subject: str = "", subject_ar: str = "") -> tuple[str, str]:
    """Extract the primary display value and its type from module data.
    Returns (value_string, value_type) where type is one of:
    number, element, symbol, status, timing, text

    Uses shared presentation.resolve_display() when a full result dict is
    available, falling back to local extraction for type classification.
    """
    if not data:
        return ("—", "text")

    # Use shared resolve_display if we have the full result
    if result is not None:
        resolved = resolve_display(result, subject, subject_ar)
        if resolved is None:
            return ("—", "text")
        # Classify the resolved value by type
        return (_classify_value(resolved, data), )[-1] if False else (clean_value(resolved), _classify_type(resolved, data))

    # Fallback: direct extraction from data dict (backward compat)
    return _extract_primary_from_data(data)


def _classify_type(value: str, data: dict) -> str:
    """Classify a display value into a card type for CSS styling."""
    v = value.strip()
    # Number check
    try:
        float(v)
        return "number"
    except (ValueError, TypeError):
        pass

    # Element keywords
    elements = {"fire", "water", "earth", "air", "metal", "wood", "yin water",
                "yang fire", "yin fire", "yang water", "yang earth", "yin earth",
                "yang metal", "yin metal", "yang wood", "yin wood"}
    if v.lower() in elements:
        return "element"

    # Timing keywords
    timing = {"contractive", "expansive", "mixed", "high", "low", "dormant",
              "challenging", "favorable", "neutral"}
    if v.lower() in timing:
        return "timing"

    # Boolean status
    if v in ("Yes", "No"):
        return "status"

    return "text"


def _extract_primary_from_data(data: dict) -> tuple[str, str]:
    """Direct extraction from data dict (legacy fallback)."""
    # Number roots/reduced values
    for key in ("root", "reduced", "gematria_root", "total_root",
                "life_path", "root_number", "chamber_root"):
        if key in data and data[key] is not None:
            return (str(data[key]), "number")

    # Elements
    for key in ("dominant_element", "element", "consensus_element",
                "primary_element", "lo_element"):
        if key in data and data[key] is not None:
            return (str(data[key]), "element")

    # Signs, symbols, animals
    for key in ("sign", "animal", "bird", "tree", "rune", "card",
                "odu", "combined_odu", "primary_card_name", "birth_card",
                "nakshatra_name", "trigram", "hexagram_name",
                "mayan_sign", "day_sign", "tonalli", "sun_sign",
                "rising_sign", "zodiac_animal"):
        if key in data and data[key] is not None:
            val = data[key]
            if isinstance(val, dict):
                continue
            return (str(val), "symbol")

    # Timing/period
    for key in ("period", "phase", "current_period", "period_quality",
                "consensus_timing", "firdaria_combined"):
        if key in data and data[key] is not None:
            return (str(data[key]), "timing")

    # Boolean/status
    for key in ("present", "active", "is_meji", "has_kala_sarpa",
                "is_pushkara"):
        if key in data:
            val = data[key]
            if isinstance(val, bool):
                return ("Yes" if val else "No", "status")

    # Day master (BaZi)
    if "day_master" in data:
        return (str(data["day_master"]), "symbol")

    # Total/sum values
    for key in ("total", "total_gematria", "total_value", "abjad_total",
                "raw_sum", "score"):
        if key in data and data[key] is not None:
            val = data[key]
            if isinstance(val, (int, float)):
                return (str(int(val) if isinstance(val, float) and val == int(val) else val), "number")

    # Planet
    for key in ("planet", "ruler", "consensus_planet"):
        if key in data and data[key] is not None:
            return (str(data[key]), "symbol")

    return ("—", "text")


def _extract_secondary(data: dict, primary_key: str = "") -> str:
    """Extract 1-2 secondary detail strings."""
    parts = []
    skip = {"constants_version", "note", "module_class", "dob",
            "arabic_name", "latin_name", "coordinates", "julian_day",
            "jdn_used", "letter_breakdown", "word_sums", "transliterated_letters",
            "word_breakdown", "planets", "houses", "aspects_list",
            "scholarship_fidelity", "scholarship_note", "method"}
    # Also skip whatever field the primary value consumed
    if primary_key:
        skip.add(primary_key)

    # Specific secondary extractions
    if "total" in data and "root" in data and primary_key not in ("total", "root"):
        parts.append(f"Total: {data['total']}")
    if "element" in data and "dominant_element" not in data and primary_key != "element":
        parts.append(str(data["element"]))
    if "ruler" in data and "planet" not in data and primary_key != "ruler":
        parts.append(f"Ruler: {data['ruler']}")

    if parts:
        return " · ".join(parts[:2])

    # Generic: grab first 2 short scalar values we haven't used
    for key, val in data.items():
        if key in skip or len(parts) >= 2:
            break
        if isinstance(val, (str, int, float)) and val is not None:
            if isinstance(val, bool):
                continue
            sv = str(val)
            if 1 < len(sv) < 40:
                label = key.replace("_", " ").title()
                parts.append(f"{label}: {sv}")

    return " · ".join(parts[:2])


def _value_type_class(vtype: str) -> str:
    return f"card-value-{vtype}"


def generate_html(output_json_path: str, reading_md_path: str,
                  html_path: str | None = None,
                  panels_data: dict | None = None) -> str:
    data = json.loads(Path(output_json_path).read_text(encoding="utf-8"))
    # reading_md_path accepted for API compat but prose is no longer rendered

    if html_path is None:
        stem = Path(output_json_path).stem
        html_path = str(Path(output_json_path).parent / f"{stem}_reading.html")

    profile = data.get("profile", {})
    synth = data.get("synthesis", {})
    order_id = uuid.uuid4().hex[:12].upper()
    now = datetime.now()

    # Build results index
    results_list = data.get("results", [])
    results_idx = {}
    for r in results_list:
        results_idx[r["id"]] = r

    # Peak convergence
    nc = synth.get("number_convergences", [])
    peak = max(nc, key=lambda x: x.get("system_count", 0)) if nc else {}
    peak_count = peak.get("system_count", 0)
    peak_groups = peak.get("group_count", 0)

    # Meta patterns
    meta_raw = data.get("semantic_reading", {}).get("meta_patterns_fired", [])
    fired_names = [p.get("pattern_id", p.get("name", "")).replace("_", " ").title()
                   for p in meta_raw if p.get("fired")]

    # Core numbers
    core = profile.get("core_numbers", {})
    abjad_data = results_idx.get("abjad_kabir", {}).get("data", {})

    # Extract animal + planetary for top sections
    animal = extract_animal_profile(data)
    planet = extract_planetary_profile(data)

    # ── Begin HTML ──
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>SIRR — {_esc(profile.get("subject", "Reading"))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400;1,500&family=Outfit:wght@200;300;400;500&family=Noto+Sans+SC:wght@400;500&display=swap" rel="stylesheet">
</head>
<body>
'''

    # ── CSS ──
    html += '''<style>
@keyframes fadeUp { from { opacity:0; transform:translateY(24px); } to { opacity:1; transform:translateY(0); } }
@keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
@keyframes lineGrow { from { height:0; } to { height:56px; } }

:root {
  --bg:      #0A0906;
  --bg2:     #111009;
  --border:  #2A2418;
  --amber:   #B8860B;
  --amber-d: #7A5A07;
  --amber-g: rgba(184,134,11,0.06);
  --indigo:  #3D3580;
  --teal:    #2D6E6E;
  --text:    #D4C9A8;
  --text-d:  #7A7060;
  --text-f:  #3A3428;
  --gold:    #C9A84C;
}
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Cormorant Garamond',Georgia,serif; background:var(--bg); color:var(--text); -webkit-font-smoothing:antialiased; overflow-x:hidden; }
::selection { background:var(--amber-g); color:var(--text); }

.page { max-width:1100px; margin:0 auto; padding:0 32px; position:relative; }

/* ── Hero ── */
.hero { text-align:center; padding:80px 0 48px; position:relative; }
.hero-brand { font-family:'Outfit',sans-serif; font-size:10px; letter-spacing:.28em; text-transform:uppercase; color:var(--amber-d); font-weight:300; animation:fadeIn 1.2s ease .2s both; }
.hero-rule { width:36px; height:1px; background:var(--amber-d); margin:24px auto; animation:fadeIn 1s ease .5s both; }
.hero-name { font-size:clamp(26px,4.5vw,44px); font-weight:400; letter-spacing:.04em; line-height:1.2; color:var(--text); animation:fadeUp 1.2s ease .4s both; }
.hero-arabic { font-size:clamp(20px,3.5vw,32px); color:var(--indigo); direction:rtl; font-family:'Arial',sans-serif; margin:10px 0 0; opacity:.7; animation:fadeUp 1.2s ease .6s both; }
.hero-meta { font-family:'Outfit',sans-serif; font-size:11px; color:var(--text-f); letter-spacing:.15em; margin-top:20px; font-weight:300; animation:fadeIn 1s ease .8s both; }
.hero-stem { width:1px; height:0; background:linear-gradient(to bottom,var(--amber-d),transparent); margin:32px auto 0; animation:lineGrow 1.2s ease 1s both; }

/* ── Signal ── */
.signal { text-align:center; padding:20px 0 32px; opacity:0; animation:fadeIn 1.2s ease 1.2s forwards; }
.signal-number { font-family:'Outfit',sans-serif; font-size:48px; font-weight:200; color:var(--gold); line-height:1; letter-spacing:2px; }
.signal-label { font-family:'Outfit',sans-serif; font-size:11px; color:var(--text-d); margin-top:6px; letter-spacing:1.5px; font-weight:300; }
.signal-sub { font-family:'Outfit',sans-serif; font-size:10px; color:var(--text-f); margin-top:4px; letter-spacing:1px; font-weight:300; }

/* ── Core Numbers Grid ── */
.num-sig { padding:32px 0 40px; border-top:1px solid var(--border); border-bottom:1px solid var(--border); margin-bottom:40px; }
.num-sig-title { font-family:'Outfit',sans-serif; font-size:10px; letter-spacing:4px; text-transform:uppercase; color:var(--amber-d); text-align:center; margin-bottom:24px; font-weight:300; }
.num-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; max-width:520px; margin:0 auto; }
.num-cell { text-align:center; padding:14px 8px; cursor:pointer; border:1px solid transparent; border-radius:8px; transition:border-color 0.3s; }
.num-cell:hover { border-color:var(--amber); }
.num-value { font-family:'Outfit',sans-serif; font-size:32px; font-weight:200; color:var(--gold); line-height:1; }
.num-label { font-family:'Outfit',sans-serif; font-size:9px; letter-spacing:2px; text-transform:uppercase; color:var(--text-d); margin-top:8px; font-weight:300; }
.num-meaning { font-size:13px; color:var(--text-f); margin-top:4px; font-style:italic; }
@media(max-width:600px) { .num-grid { grid-template-columns:repeat(2, 1fr); } .num-value { font-size:26px; } }

/* ── Tradition Sections ── */
.tradition-section { margin-bottom:48px; }
.tradition-header { display:flex; align-items:center; gap:12px; margin-bottom:20px; padding-bottom:12px; border-bottom:1px solid var(--border); }
.tradition-icon { font-size:22px; opacity:0.6; width:32px; text-align:center; }
.tradition-name { font-family:'Outfit',sans-serif; font-size:13px; letter-spacing:2.5px; text-transform:uppercase; color:var(--text-d); font-weight:400; }
.tradition-count { font-family:'Outfit',sans-serif; font-size:10px; color:var(--text-f); letter-spacing:1px; margin-left:auto; }

/* ── Module Card Grid ── */
.card-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:16px; }
@media(max-width:600px) { .card-grid { grid-template-columns:repeat(auto-fill, minmax(160px, 1fr)); gap:12px; } }

.mod-card {
  border:1px solid var(--border);
  border-radius:10px;
  padding:20px 16px 16px;
  background:linear-gradient(170deg, #0F0D08 0%, #1A1508 100%);
  cursor:pointer;
  transition:border-color 0.3s ease, transform 0.2s ease;
  position:relative;
  overflow:hidden;
  display:flex;
  flex-direction:column;
}
.mod-card::before {
  content:'';
  position:absolute;
  top:0; left:0; width:3px; height:100%;
  border-radius:10px 0 0 10px;
}
.mod-card:hover { border-color:var(--amber); transform:translateY(-2px); }
.mod-card-name {
  font-family:'Outfit',sans-serif;
  font-size:9px;
  letter-spacing:1.5px;
  text-transform:uppercase;
  color:var(--text-d);
  font-weight:400;
  margin-bottom:10px;
  line-height:1.3;
}
.mod-card-value {
  font-family:'Outfit',sans-serif,'Noto Sans SC',sans-serif;
  font-size:24px;
  font-weight:200;
  color:var(--gold);
  line-height:1.2;
  margin-bottom:4px;
  word-break:break-word;
}
.mod-card-value.card-value-number { font-size:32px; color:var(--gold); }
.mod-card-value.card-value-element { font-size:22px; color:#4DB8B8; }
.mod-card-value.card-value-symbol { font-size:20px; color:var(--text); }
.mod-card-value.card-value-timing { font-size:18px; color:#6E63C8; }
.mod-card-value.card-value-status { font-size:20px; }
.mod-card-value.card-value-text { font-size:18px; color:var(--text); }
.mod-card-secondary {
  font-family:'Outfit',sans-serif;
  font-size:10px;
  color:var(--text-f);
  margin-bottom:10px;
  letter-spacing:0.3px;
}
.mod-card-interp {
  font-family:'Cormorant Garamond',serif,'Noto Sans SC',sans-serif;
  font-size:14px;
  line-height:1.6;
  color:var(--text-d);
  margin-top:auto;
}

/* ── Existing card sections (animals, planets, tarot) ── */
.tarot-row { display:flex; justify-content:center; gap:16px; margin-top:20px; flex-wrap:wrap; }
.tarot-card { width:110px; height:175px; border:1px solid var(--amber-d); border-radius:8px; background:linear-gradient(170deg, #0F0D08 0%, #1A1508 100%); display:flex; flex-direction:column; align-items:center; justify-content:center; padding:14px 8px; cursor:pointer; transition:border-color 0.3s; }
.tarot-card:hover { border-color:var(--amber); }
.tarot-numeral { font-family:'Cormorant Garamond',serif; font-size:14px; font-weight:300; color:var(--amber-d); letter-spacing:3px; }
.tarot-glyph { font-size:32px; margin:10px 0; line-height:1; opacity:0.7; }
.tarot-name { font-family:'Outfit',sans-serif; font-size:8px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text-d); text-align:center; line-height:1.4; }
.tarot-label { font-family:'Outfit',sans-serif; font-size:8px; letter-spacing:1px; color:var(--text-f); margin-top:4px; text-transform:uppercase; }

.playing-card { width:110px; height:175px; border:1px solid var(--text-d); border-radius:8px; background:linear-gradient(170deg, #F5F0E6 0%, #E8E0D0 100%); display:flex; flex-direction:column; align-items:center; justify-content:center; padding:12px 8px; cursor:pointer; transition:border-color 0.3s; }
.playing-card:hover { border-color:var(--amber); }
.playing-suit { font-size:38px; line-height:1; }
.playing-suit.red { color:#B22222; }
.playing-suit.black { color:#1A1A1A; }
.playing-rank { font-family:'Cormorant Garamond',serif; font-size:20px; font-weight:600; color:#1A1A1A; margin-top:4px; }
.playing-label { font-family:'Outfit',sans-serif; font-size:8px; letter-spacing:1px; color:#8A7E6E; margin-top:6px; text-transform:uppercase; }

.animal-section { margin-top:32px; padding-top:24px; border-top:1px solid var(--border); }
.animal-section-title { font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:2.5px; text-transform:uppercase; color:var(--text-d); text-align:center; margin-bottom:18px; font-weight:300; }
.animal-row { display:flex; justify-content:center; gap:16px; flex-wrap:wrap; }
.animal-card { width:140px; min-height:190px; border:1px solid var(--amber-d); border-radius:8px; background:linear-gradient(170deg, #0F0D08 0%, #1A1508 100%); display:flex; flex-direction:column; align-items:center; justify-content:flex-start; padding:18px 10px; cursor:pointer; transition:border-color 0.3s; }
.animal-card:hover { border-color:var(--amber); }
.animal-glyph { font-size:44px; line-height:1; margin-bottom:8px; }
.animal-name { font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:2px; text-transform:uppercase; color:var(--amber); font-weight:400; text-align:center; }
.animal-element { font-family:'Cormorant Garamond',serif; font-size:13px; color:var(--text-d); margin-top:6px; font-style:italic; }
.animal-pillar-label { font-family:'Outfit',sans-serif; font-size:8px; letter-spacing:1.5px; color:var(--text-f); margin-top:8px; text-transform:uppercase; }
.animal-secondary-row { display:flex; justify-content:center; gap:10px; flex-wrap:wrap; margin-top:14px; }
.animal-chip { font-family:'Outfit',sans-serif; font-size:10px; letter-spacing:1px; color:var(--text-d); padding:5px 12px; border:1px solid var(--border); border-radius:20px; background:rgba(0,0,0,0.15); }
.animal-chip strong { color:var(--amber); font-weight:500; }

.planet-section { margin-top:32px; padding-top:24px; border-top:1px solid var(--border); }
.planet-section-title { font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:2.5px; text-transform:uppercase; color:var(--text-d); text-align:center; margin-bottom:18px; font-weight:300; }
.planet-row { display:flex; justify-content:center; gap:16px; flex-wrap:wrap; }
.planet-card { width:160px; min-height:200px; border:1px solid var(--amber-d); border-radius:8px; background:linear-gradient(170deg, #0F0D08 0%, #1A1508 100%); display:flex; flex-direction:column; align-items:center; justify-content:flex-start; padding:20px 12px; cursor:pointer; transition:border-color 0.3s; }
.planet-card:hover { border-color:var(--amber); }
.planet-glyph { font-size:48px; line-height:1; color:var(--amber); margin-bottom:6px; }
.planet-name { font-family:'Outfit',sans-serif; font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:var(--amber); font-weight:400; text-align:center; }
.planet-status { font-family:'Cormorant Garamond',serif; font-size:13px; color:var(--text-d); margin-top:8px; font-style:italic; text-align:center; }
.planet-sub { font-family:'Outfit',sans-serif; font-size:9px; letter-spacing:1px; color:var(--text-f); margin-top:8px; text-transform:uppercase; text-align:center; line-height:1.5; }
.dasha-bar-wrap { margin-top:24px; padding:0 8px; }
.dasha-bar-label { font-family:'Outfit',sans-serif; font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text-f); text-align:center; margin-bottom:8px; }
.dasha-bar { display:flex; width:100%; height:26px; border:1px solid var(--border); border-radius:4px; overflow:hidden; }
.dasha-seg { display:flex; align-items:center; justify-content:center; font-family:'Outfit',sans-serif; font-size:9px; letter-spacing:0.5px; color:var(--text-f); background:rgba(184,134,11,0.05); border-right:1px solid var(--border); text-align:center; padding:0 4px; white-space:nowrap; overflow:hidden; }
.dasha-seg:last-child { border-right:none; }
.dasha-seg.current { background:linear-gradient(180deg, rgba(184,134,11,0.35) 0%, rgba(184,134,11,0.15) 100%); color:var(--amber); font-weight:500; }
.dasha-here { font-family:'Outfit',sans-serif; font-size:8px; letter-spacing:1px; color:var(--amber); text-align:center; margin-top:5px; text-transform:uppercase; }
.profection-wrap { text-align:center; }
.profection-badge { display:inline-block; margin-top:16px; padding:8px 16px; border:1px solid var(--border); border-radius:20px; font-family:'Outfit',sans-serif; font-size:10px; letter-spacing:1.5px; color:var(--text-d); text-transform:uppercase; background:rgba(0,0,0,0.15); }
.profection-badge strong { color:var(--amber); font-weight:500; }

/* ── Pattern tags ── */
.patterns-whisper { text-align:center; padding:16px 0 32px; }
.patterns-whisper .tag { font-family:'Outfit',sans-serif; font-size:9px; letter-spacing:2px; text-transform:uppercase; color:var(--text-f); display:inline-block; margin:0 8px; font-weight:300; }

/* ── Modal ── */
.card-modal-overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.88); display:none; justify-content:center; align-items:center; z-index:1000; backdrop-filter:blur(4px); }
.card-modal-overlay.active { display:flex; }
.card-modal { max-width:520px; width:90%; max-height:80vh; overflow-y:auto; background:linear-gradient(170deg,#0F0D08 0%,#1A1508 100%); border:1px solid var(--amber-d); border-radius:12px; padding:32px 24px 24px; position:relative; animation:modalIn 0.25s ease; }
@keyframes modalIn { from { opacity:0; transform:scale(0.95) translateY(10px); } to { opacity:1; transform:scale(1) translateY(0); } }
.card-modal-close { position:absolute; top:12px; right:14px; font-size:22px; color:var(--text-f); cursor:pointer; background:none; border:none; padding:4px 8px; }
.card-modal-close:hover { color:var(--amber); }
.card-modal-title { font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:2.5px; text-transform:uppercase; color:var(--amber); text-align:center; margin-bottom:16px; font-weight:400; }
.card-modal-value { font-family:'Outfit',sans-serif; font-size:28px; font-weight:200; color:var(--gold); text-align:center; margin-bottom:12px; }
.card-modal-body { font-family:'Cormorant Garamond',serif; font-size:16px; line-height:1.75; color:var(--text); }
.card-modal-body strong { color:var(--amber); font-weight:600; }
.card-modal-data { margin-top:16px; padding-top:12px; border-top:1px solid var(--border); }
.card-modal-data-row { font-family:'Outfit',sans-serif; font-size:11px; color:var(--text-d); margin:4px 0; letter-spacing:0.3px; }
.card-modal-data-row strong { color:var(--text); font-weight:400; }

/* ── Signature / Footer ── */
.signature { text-align:center; padding:60px 0 32px; }
.sig-ornament { font-size:20px; color:var(--text-f); opacity:0.35; margin-bottom:16px; letter-spacing:8px; }
.sig-brand { font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:9px; text-transform:uppercase; color:var(--gold); font-weight:300; }
.sig-tagline { font-size:16px; color:var(--text-d); margin-top:10px; font-style:italic; font-weight:400; }
footer { border-top:1px solid var(--border); padding:20px 0 48px; text-align:center; }
footer p { font-family:'Outfit',sans-serif; font-size:9px; color:var(--text-f); line-height:2.2; max-width:400px; margin:0 auto; font-weight:300; letter-spacing:0.3px; }

@media(max-width:600px) {
  .page { padding:0 16px; }
  .hero { padding:48px 0 32px; }
  .signal-number { font-size:36px; }
  .mod-card-value { font-size:20px; }
  .mod-card-value.card-value-number { font-size:26px; }
  .tarot-card, .playing-card { width:95px; height:155px; }
  .animal-card { width:125px; min-height:170px; }
  .planet-card { width:140px; min-height:180px; }
}
</style>
'''

    # ── Hero ──
    html += f'''
<div class="page">

<div class="hero">
  <div class="hero-brand">S I R R</div>
  <div class="hero-rule"></div>
  <div class="hero-name">{_esc(profile.get("subject",""))}</div>
  <div class="hero-arabic">{_esc(profile.get("arabic",""))}</div>
  <div class="hero-meta">{_esc(profile.get("dob",""))}</div>
  <div class="hero-stem"></div>
</div>

<div class="signal">
  <div class="signal-number">{peak_count}</div>
  <div class="signal-label">traditions converge on your primary signal</div>
  <div class="signal-sub">across {peak_groups} independent tradition families</div>
</div>
'''

    # ── Core Numbers ──
    root_meanings = {
        1: "The Initiator", 2: "The Diplomat", 3: "The Communicator",
        4: "The Builder", 5: "The Liberator", 6: "The Nurturer",
        7: "The Seeker", 8: "The Executive", 9: "The Humanitarian",
        11: "The Visionary", 22: "The Master Builder", 33: "The Master Teacher",
    }

    def _num_cell(value, label):
        v = value if value else "—"
        meaning = ""
        try:
            v_int = int(v) if str(v).isdigit() else None
            if v_int and v_int in root_meanings:
                meaning = root_meanings[v_int]
        except (ValueError, TypeError):
            pass
        return f'''<div class="num-cell">
      <div class="num-value">{v}</div>
      <div class="num-label">{label}</div>
      {"<div class='num-meaning'>" + meaning + "</div>" if meaning else ""}
    </div>'''

    lp = core.get("life_path", "?")
    expr = core.get("expression", "?")
    su = core.get("soul_urge", "?")
    pers = core.get("personality", "?")
    bday = core.get("birthday", "?")
    abjad_root = abjad_data.get("root", "?")
    abjad_val = abjad_data.get("total", core.get("abjad_first", "?"))

    html += f'''
<div class="num-sig">
  <div class="num-sig-title">Your Numeric Signature</div>
  <div class="num-grid">
    {_num_cell(lp, "Life Path")}
    {_num_cell(expr, "Expression")}
    {_num_cell(su, "Soul Urge")}
    {_num_cell(pers, "Personality")}
    {_num_cell(bday, "Birthday")}
    {_num_cell(abjad_root, "Abjad Root")}
  </div>
</div>
'''

    # ── Tarot Cards (keep existing) ──
    tarot_birth_data = results_idx.get("tarot_birth", {}).get("data", {})
    tarot_name_data = results_idx.get("tarot_name", {}).get("data", {})
    cardology_data = results_idx.get("cardology", {}).get("data", {})

    _tarot_glyphs = {
        "The Fool": "🌀", "The Magician": "✦", "The High Priestess": "☽",
        "The Empress": "♛", "The Emperor": "♔", "The Hierophant": "⛧",
        "The Lovers": "❦", "The Chariot": "⚡", "Strength": "∞",
        "The Hermit": "🜨", "Wheel of Fortune": "☸", "Justice": "⚖",
        "The Hanged Man": "⊗", "Death": "☠", "Temperance": "⏳",
        "The Devil": "⛧", "The Tower": "↯", "The Star": "✧",
        "The Moon": "☾", "The Sun": "☀", "Judgement": "♆",
        "The World": "◎",
    }
    _tarot_numerals = {
        "The Fool": "0", "The Magician": "I", "The High Priestess": "II",
        "The Empress": "III", "The Emperor": "IV", "The Hierophant": "V",
        "The Lovers": "VI", "The Chariot": "VII", "Strength": "VIII",
        "The Hermit": "IX", "Wheel of Fortune": "X", "Justice": "XI",
        "The Hanged Man": "XII", "Death": "XIII", "Temperance": "XIV",
        "The Devil": "XV", "The Tower": "XVI", "The Star": "XVII",
        "The Moon": "XVIII", "The Sun": "XIX", "Judgement": "XX",
        "The World": "XXI",
    }

    def _tarot_card_html(card_name, label=""):
        glyph = _tarot_glyphs.get(card_name, "✦")
        numeral = _tarot_numerals.get(card_name, "")
        return f'''<div class="tarot-card">
      <div class="tarot-numeral">{numeral}</div>
      <div class="tarot-glyph">{glyph}</div>
      <div class="tarot-name">{_esc(card_name)}</div>
      {f'<div class="tarot-label">{_esc(label)}</div>' if label else ''}
    </div>'''

    html += '<div class="tarot-row">\n'
    html += f'  <div class="num-sig-title" style="width:100%;margin-bottom:12px">Your Cards</div>\n'
    html += f'  {_tarot_card_html(tarot_birth_data.get("primary_card_name", ""), "Birth Card")}\n'
    html += f'  {_tarot_card_html(tarot_birth_data.get("secondary_card_name", ""), "Shadow Card")}\n'
    html += f'  {_tarot_card_html(tarot_name_data.get("expression_card_name", ""), "Expression")}\n'

    if cardology_data.get("birth_card"):
        suit = cardology_data.get("suit", "")
        suit_sym = {"Clubs": "♣", "Hearts": "♥", "Diamonds": "♦", "Spades": "♠"}.get(suit, "♣")
        suit_color = "red" if suit in ("Hearts", "Diamonds") else "black"
        rank = cardology_data.get("rank", "")
        html += f'''  <div class="playing-card">
      <div class="playing-suit {suit_color}">{suit_sym}</div>
      <div class="playing-rank">{_esc(rank)} of {_esc(suit)}</div>
      <div class="playing-label">Birth Card</div>
    </div>\n'''

    html += '</div>\n\n'

    # ── Animal Section (keep existing) ──
    if animal.get("animal"):
        _animal_glyphs = {
            "Rat": "🐀", "Ox": "🐂", "Tiger": "🐅", "Rabbit": "🐇",
            "Dragon": "🐉", "Snake": "🐍", "Horse": "🐎", "Goat": "🐐",
            "Monkey": "🐒", "Rooster": "🐓", "Dog": "🐕", "Pig": "🐖",
        }

        def _animal_card(animal_name, element, polarity, pillar_label):
            glyph = _animal_glyphs.get(animal_name, "✦")
            elem_str = f"{element} · {polarity}" if element and polarity else (element or "")
            return f'''<div class="animal-card">
      <div class="animal-glyph">{glyph}</div>
      <div class="animal-name">{_esc(animal_name or "—")}</div>
      {f'<div class="animal-element">{_esc(elem_str)}</div>' if elem_str else ''}
      <div class="animal-pillar-label">{_esc(pillar_label)}</div>
    </div>'''

        year_animal = animal.get("year_animal") or animal.get("animal")
        day_animal = animal.get("day_animal")
        year_element = animal.get("year_element") or animal.get("element")
        year_polarity = animal.get("polarity")
        day_element = animal.get("day_element")

        cards_html = _animal_card(year_animal, year_element, year_polarity, "Year · Public Self")
        if day_animal and day_animal != year_animal:
            cards_html += "\n    " + _animal_card(day_animal, day_element, None, "Day · True Self")

        nak_str = animal.get("nakshatra_animal") or "—"
        celtic_str = animal.get("celtic_tree") or "—"
        mayan_str = animal.get("mayan_sign") or "—"
        temp_str = animal.get("temperament_type") or "—"

        html += f'''
<div class="animal-section">
  <div class="animal-section-title">Your Animals</div>
  <div class="animal-row">{cards_html}</div>
  <div class="animal-secondary-row">
    <div class="animal-chip">Vedic: <strong>{_esc(nak_str)}</strong></div>
    <div class="animal-chip">Celtic: <strong>{_esc(celtic_str)}</strong></div>
    <div class="animal-chip">Mayan: <strong>{_esc(mayan_str)}</strong></div>
    <div class="animal-chip">Temperament: <strong>{_esc(temp_str)}</strong></div>
  </div>
</div>
'''

    # ── Planetary Section (keep existing) ──
    if planet.get("primary_joy_planet") or planet.get("firdaria_major"):
        joy_planet = planet.get("primary_joy_planet") or "—"
        joy_glyph = PLANET_GLYPHS.get(joy_planet, "✦")
        joy_details = planet.get("joy_details", {}) or {}
        joy_info = joy_details.get(joy_planet, {}) if joy_planet != "—" else {}
        joy_house = joy_info.get("joy_house")
        joy_rationale = joy_info.get("rationale", "")
        if " — " in joy_rationale:
            joy_rationale = joy_rationale.split(" — ", 1)[1]
        joy_sub = f"House {joy_house}<br>{joy_rationale}" if joy_house else joy_rationale

        firdaria_major = planet.get("firdaria_major") or ""
        firdaria_sub = planet.get("firdaria_sub") or ""
        firdaria_glyph_major = PLANET_GLYPHS.get(firdaria_major, "")
        firdaria_glyph_sub = PLANET_GLYPHS.get(firdaria_sub, "")
        firdaria_combined = planet.get("firdaria_combined") or f"{firdaria_major}/{firdaria_sub}"
        firdaria_range = planet.get("firdaria_period_range") or ""

        vedic_dasha = planet.get("vedic_current_dasha") or ""
        vedic_glyph = PLANET_GLYPHS.get(vedic_dasha, "")
        vedic_start = planet.get("vedic_dasha_start")
        vedic_end = planet.get("vedic_dasha_end")
        vedic_range = f"age {vedic_start:.0f}–{vedic_end:.0f}" if vedic_start is not None and vedic_end is not None else ""

        birth_ruler = planet.get("nakshatra_ruler") or ""
        birth_ruler_glyph = PLANET_GLYPHS.get(birth_ruler, "")
        nak_name = planet.get("nakshatra_name") or ""

        html += '\n<div class="planet-section">\n  <div class="planet-section-title">Your Planets</div>\n  <div class="planet-row">\n'

        html += f'''    <div class="planet-card">
      <div class="planet-glyph">{joy_glyph}</div>
      <div class="planet-name">{_esc(joy_planet)}</div>
      <div class="planet-status">In Joy</div>
      <div class="planet-sub">{joy_sub}</div>
    </div>\n'''

        if firdaria_major:
            html += f'''    <div class="planet-card">
      <div class="planet-glyph">{firdaria_glyph_major}{firdaria_glyph_sub}</div>
      <div class="planet-name">{_esc(firdaria_combined)}</div>
      <div class="planet-status">Firdaria</div>
      <div class="planet-sub">{f"Period {_esc(firdaria_range)}" if firdaria_range else "Current phase"}</div>
    </div>\n'''

        if vedic_dasha:
            html += f'''    <div class="planet-card">
      <div class="planet-glyph">{vedic_glyph}</div>
      <div class="planet-name">{_esc(vedic_dasha)}</div>
      <div class="planet-status">Vedic Mahadasha</div>
      <div class="planet-sub">{_esc(vedic_range)}</div>
    </div>\n'''

        if birth_ruler:
            html += f'''    <div class="planet-card">
      <div class="planet-glyph">{birth_ruler_glyph}</div>
      <div class="planet-name">{_esc(birth_ruler)}</div>
      <div class="planet-status">Birth Ruler</div>
      <div class="planet-sub">{_esc(nak_name)}</div>
    </div>\n'''

        html += '  </div>\n'

        # Vimshottari timeline bar
        timeline = planet.get("vedic_timeline") or []
        if timeline and vedic_dasha:
            html += '  <div class="dasha-bar-wrap">\n    <div class="dasha-bar-label">Vimshottari Dasha Timeline</div>\n    <div class="dasha-bar">\n'
            total = sum((seg.get("years") or 0) for seg in timeline) or 1
            for seg in timeline:
                seg_planet = seg.get("planet", "?")
                seg_years = seg.get("years") or 0
                seg_glyph = PLANET_GLYPHS.get(seg_planet, "")
                width_pct = (seg_years / total) * 100
                is_current = seg_planet == vedic_dasha
                cls = "dasha-seg current" if is_current else "dasha-seg"
                label = f'{seg_glyph} {seg_planet}' if width_pct > 6 else seg_glyph
                html += f'      <div class="{cls}" style="flex:{seg_years}">{label}</div>\n'
            html += '    </div>\n'
            html += f'    <div class="dasha-here">Currently in {_esc(vedic_dasha)} {f"({_esc(vedic_range)})" if vedic_range else ""}</div>\n'
            html += '  </div>\n'

        prof_house = planet.get("profection_house")
        prof_info = planet.get("profection_info") or ""
        if prof_house:
            html += f'''  <div class="profection-wrap">
    <div class="profection-badge">Profection · <strong>House {prof_house}</strong> · {_esc(prof_info)}</div>
  </div>\n'''

        html += '</div>\n\n'

    # ── Pattern tags ──
    if fired_names:
        tags_html = " ".join(f'<span class="tag">{_esc(n)}</span>' for n in fired_names)
        html += f'<div class="patterns-whisper">{tags_html}</div>\n'

    # ══════════════════════════════════════════════════
    # ── TRADITION GALLERIES — the main body (NEW) ──
    # ══════════════════════════════════════════════════

    # Build module card data for ALL results, then emit by tradition
    subject_name = profile.get("subject", "")
    subject_ar = profile.get("arabic", "")
    all_card_data = {}  # module_id -> dict for modal
    for r in results_list:
        mid = r["id"]
        if mid in ALWAYS_HIDE_IDS:
            continue
        mdata = r.get("data", {})
        interp = r.get("interpretation", "") or ""

        # Suppress interpretation text with unresolved {placeholders}
        if PLACEHOLDER_RE.search(interp):
            interp = ""

        # Use shared presentation filter for primary value
        primary_val, val_type = _extract_primary_value(mdata, result=r, subject=subject_name, subject_ar=subject_ar)

        # Apply label rewrites
        display_name = ID_LABEL_REWRITES.get(mid, r.get("name", mid.replace("_", " ").title()))

        secondary = _extract_secondary(mdata)
        short_interp = _truncate_interp(interp)
        # Skip cards that would render visually empty — no value, no
        # secondary info, no interpretation snippet. These normally come
        # from modules that errored silently or have no meaningful output
        # for this particular profile. Showing an empty shell looks broken;
        # omitting it is closer to the intent.
        is_empty = (
            (not primary_val or primary_val.strip() in HIDE_EXACT_VALUES) and
            not secondary and
            not short_interp
        )
        if is_empty:
            continue
        all_card_data[mid] = {
            "name": display_name,
            "value": primary_val,
            "type": val_type,
            "secondary": secondary,
            "interp_short": short_interp,
            "interp_full": interp,
            "data": mdata,
        }

    # Track which modules we've placed
    placed = set()

    for tradition_name, module_ids in TRADITION_MAP.items():
        # Filter to modules that exist in results
        present = [mid for mid in module_ids if mid in all_card_data]
        if not present:
            continue
        placed.update(present)

        color = TRADITION_COLORS.get(tradition_name, "#7A7060")
        icon = TRADITION_ICONS.get(tradition_name, "✦")

        html += f'''
<div class="tradition-section">
  <div class="tradition-header">
    <span class="tradition-icon">{icon}</span>
    <span class="tradition-name">{_esc(tradition_name)}</span>
    <span class="tradition-count">{len(present)} modules</span>
  </div>
  <div class="card-grid">
'''
        for mid in present:
            cd = all_card_data[mid]
            display_name = cd["name"]
            val = cd["value"]
            vtype = cd["type"]
            secondary = cd["secondary"]
            short_interp = cd["interp_short"]
            type_cls = _value_type_class(vtype)

            html += f'''    <div class="mod-card" data-module="{_esc(mid)}" style="--accent:{color}">
      <div class="mod-card-name">{_esc(display_name)}</div>
      <div class="mod-card-value {type_cls}">{_esc(val)}</div>
      {f'<div class="mod-card-secondary">{_esc(secondary)}</div>' if secondary else ''}
      {f'<div class="mod-card-interp">{_esc(short_interp)}</div>' if short_interp else ''}
    </div>
'''
        html += '  </div>\n</div>\n'

    # Catch any unplaced modules
    unplaced = [mid for mid in all_card_data if mid not in placed]
    if unplaced:
        html += f'''
<div class="tradition-section">
  <div class="tradition-header">
    <span class="tradition-icon">◇</span>
    <span class="tradition-name">Other</span>
    <span class="tradition-count">{len(unplaced)} modules</span>
  </div>
  <div class="card-grid">
'''
        for mid in unplaced:
            cd = all_card_data[mid]
            color = "#7A7060"
            type_cls = _value_type_class(cd["type"])
            sec_html = f'<div class="mod-card-secondary">{_esc(cd["secondary"])}</div>' if cd["secondary"] else ""
            interp_html = f'<div class="mod-card-interp">{_esc(cd["interp_short"])}</div>' if cd["interp_short"] else ""
            html += f'''    <div class="mod-card" data-module="{_esc(mid)}" style="--accent:{color}">
      <div class="mod-card-name">{_esc(cd["name"])}</div>
      <div class="mod-card-value {type_cls}">{_esc(cd["value"])}</div>
      {sec_html}
      {interp_html}
    </div>
'''
        html += '  </div>\n</div>\n'

    # ── Signature + Footer ──
    html += f'''
<div class="signature">
  <div class="sig-ornament">&#10022; &nbsp; &#10022; &nbsp; &#10022;</div>
  <div class="sig-brand">S I R R</div>
  <div class="sig-tagline">A mirror drawn from the world's oldest symbolic traditions</div>
</div>

<footer>
  <p>
    This reading is a structural reflection, not a prediction.<br>
    What the patterns mean is yours to determine.<br><br>
    238 computations across Arabic, Vedic, Western, Chinese, Hebrew, Hellenistic,<br>
    Celtic, African, Mesoamerican, Southeast Asian, Tibetan, Japanese,<br>
    Polynesian, Egyptian, Babylonian, Zoroastrian, and Esoteric traditions.<br><br>
    {now.strftime("%B %d, %Y")} &middot; {order_id}
  </p>
</footer>

</div>
'''

    # ── JavaScript: modal system for module cards ──
    card_data_json = json.dumps(
        {mid: {
            "name": cd["name"],
            "value": cd["value"],
            "interp": cd["interp_full"],
            "data": {k: v for k, v in cd["data"].items()
                     if isinstance(v, (str, int, float, bool)) and k not in
                     ("constants_version", "note", "module_class")}
        } for mid, cd in all_card_data.items()},
        ensure_ascii=False,
    )

    html += f'''
<script>
const CARD_DATA = {card_data_json};

const modalOverlay = document.createElement('div');
modalOverlay.className = 'card-modal-overlay';
modalOverlay.innerHTML = `
  <div class="card-modal">
    <button class="card-modal-close">&times;</button>
    <div class="card-modal-title"></div>
    <div class="card-modal-value"></div>
    <div class="card-modal-body"></div>
    <div class="card-modal-data"></div>
  </div>`;
document.body.appendChild(modalOverlay);

function showModuleModal(moduleId) {{
  const m = CARD_DATA[moduleId];
  if (!m) return;
  modalOverlay.querySelector('.card-modal-title').textContent = m.name || moduleId;
  modalOverlay.querySelector('.card-modal-value').textContent = m.value || '';
  modalOverlay.querySelector('.card-modal-body').textContent = m.interp || '';
  // Data fields
  const dataDiv = modalOverlay.querySelector('.card-modal-data');
  dataDiv.innerHTML = '';
  if (m.data) {{
    for (const [k, v] of Object.entries(m.data)) {{
      const row = document.createElement('div');
      row.className = 'card-modal-data-row';
      row.innerHTML = '<strong>' + k.replace(/_/g, ' ') + ':</strong> ' + String(v);
      dataDiv.appendChild(row);
    }}
  }}
  modalOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}}

function hideModal() {{
  modalOverlay.classList.remove('active');
  document.body.style.overflow = '';
}}

modalOverlay.addEventListener('click', (e) => {{
  if (e.target === modalOverlay || e.target.classList.contains('card-modal-close')) hideModal();
}});
document.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') hideModal(); }});

// Click delegation for module cards
document.addEventListener('click', (e) => {{
  const card = e.target.closest('.mod-card');
  if (card) {{
    const moduleId = card.getAttribute('data-module');
    if (moduleId) showModuleModal(moduleId);
    return;
  }}
}});

// Apply accent color to card left borders
document.querySelectorAll('.mod-card').forEach(card => {{
  const accent = card.style.getPropertyValue('--accent');
  if (accent) {{
    card.style.borderLeftColor = accent;
    card.querySelector('::before') || null;
    // Use CSS custom property for the left border accent
  }}
}});

// Override the ::before pseudo-element color via a dynamic stylesheet
(function() {{
  const style = document.createElement('style');
  const rules = [];
  document.querySelectorAll('.mod-card').forEach((card, i) => {{
    const accent = card.style.getPropertyValue('--accent');
    if (accent) {{
      card.classList.add('mc-' + i);
      rules.push('.mc-' + i + '::before {{ background:' + accent + '; }}');
    }}
  }});
  style.textContent = rules.join('\\n');
  document.head.appendChild(style);
}})();
</script>

</body>
</html>'''

    Path(html_path).write_text(html, encoding="utf-8")
    print(f"  Saved: {html_path}")
    return html_path


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python html_reading.py <output.json> <reading.md> [--out file.html]")
        sys.exit(1)

    output_json = args[0]
    reading_md = args[1]
    html_path = None

    if "--out" in args:
        idx = args.index("--out")
        if idx + 1 < len(args):
            html_path = args[idx + 1]

    if not Path(output_json).exists():
        print(f"  Error: {output_json} not found")
        sys.exit(1)
    if not Path(reading_md).exists():
        print(f"  Error: {reading_md} not found")
        sys.exit(1)

    result = generate_html(output_json, reading_md, html_path)
    print(f"  Done. Open: {result}")


if __name__ == "__main__":
    main()
