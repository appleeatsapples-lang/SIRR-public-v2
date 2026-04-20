"""
SIRR Presentation Filter
=========================
Shared presentation-layer logic used by both unified_view.py (product surface)
and html_reading.py (legacy card gallery). Extracted 2026-04-18 to avoid
duplicated value-extraction and display-filtering logic.

Provides:
  - format_primary_value(result) → str
  - resolve_display(result, subject, subject_ar) → str | None
  - clean_value(v) → str
  - _is_name_echo(value, subject, subject_ar) → bool
  - All filter constants (HIDE_EXACT_VALUES, ALWAYS_HIDE_IDS, etc.)
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import re as _re


# ── Values that carry no reader meaning ──
HIDE_EXACT_VALUES = {
    "primary", "comparative", "PRIMARY", "COMPARATIVE", "Primary", "Comparative",
    "—", "-", "",
    "True", "False", "true", "false",
    "male", "female", "Male", "Female",
    # F2.2 (2026-04-20 audit): stringified null-ish hint values that
    # legacy modules sometimes emit as placeholder text. Hiding them
    # here means they’re filtered out of both unified and merged
    # tables and from the legacy is_empty check.
    "None", "none", "NONE", "N/A", "n/a", "null", "NULL", "undefined",
}

# Modules whose output has no reader-facing shape on first view
ALWAYS_HIDE_IDS = {
    "digit_patterns",
    "inclusion_table",
    "synastry",  # requires second profile
}

# Per-module label overrides
ID_LABEL_REWRITES = {
    "biorhythm":                   "Daily cycle index (modern cycle theory)",
    "execution_pattern_analysis":  "Execution pattern",
    "hermetic_element_balance":    "Elemental balance",
    "prenatal_syzygy":             "Moon phase before birth",
    "bazi_luck_pillars":           "Current luck pillar",
    "mandaean_gematria":           "Arabic-to-Mandaean cognate sum",
    "ethiopian_asmat":             "Arabic-to-Ethiopian cognate sum",
    "hebrew_gematria":             "Arabic-to-Hebrew cognate sum (Mispar Gadol)",
    "chaldean":                    "Chaldean + Balliett name numerology (modern)",
    "compound":                    "Compound number meanings (Cheiro, 20th c.)",
    "cheiro_extensions":           "Cheiro compound + color (20th c.)",
    "agrippan":                    "Agrippan ciphers (Western occult revival)",
    "thelemic_gematria":           "Thelemic ALW cipher (Crowley, 1904)",
    "gd_correspondences":          "Golden Dawn 777 correspondences (1890s)",
    "rose_cross_sigil":            "Rose Cross sigil (Golden Dawn)",
    "sephirotic_path_analysis":    "Sephirot path reading (modern application)",
    "tree_of_life":                "Tree of Life path (modern Kabbalah synthesis)",
    "hermetic_alignment":          "SIRR comparative axes (hermetic framing)",
    "quranic_figures":             "Name pattern match against Quranic figures",
    "torah_figures":               "Name pattern match against Torah figures",
    "nt_figures":                  "Name pattern match against NT figures",
    "zairja":                      "Zairja (mechanical letter device)",
    "element_consensus":           "Tradition-vote element (4 oracles)",
    "elemental_letters":           "Arabic letter-element (Al-Buni)",
    "temperament":                 "Four Temperaments (Unani / classical)",
    "bazi_daymaster":              "BaZi element (Chinese)",
}

# Per-module custom value builders
ID_VALUE_BUILDERS: Dict[str, Any] = {
    "natal_chart": lambda d: (
        " · ".join(
            str(x) for x in (d.get("sun_sign"), d.get("moon_sign"), d.get("rising_sign"))
            if isinstance(x, str) and x and not x.lower().startswith("unknown")
        )
        if any(isinstance(d.get(k), str) and d.get(k) and not d.get(k).lower().startswith("unknown")
               for k in ("sun_sign", "moon_sign", "rising_sign"))
        else ("Chart unavailable" if d.get("error") else None)
    ),
    "cheiro_extensions": lambda d: str(d.get("reduced", d.get("compound", "—"))),
    "gd_correspondences": lambda d: str(d.get("number", "—")),
    "bazi_10_year_forecast": lambda d: (
        f"{d.get('stem_element', '')} · {d.get('branch_element', '')}".strip(" ·")
        or str(d.get("stem", "—"))
    ),
    # Modules that would otherwise show JDN (2450350) as primary
    "julian": lambda d: str(d.get("julian_day", "—")),  # intentionally show JDN — that IS the module's output
    "geomancy": lambda d: str(d.get("primary_figure", d.get("figures", {}).get("judge", "—"))) if isinstance(d.get("primary_figure", d.get("figures")), (str, dict)) else "—",
    "mayan": lambda d: (
        f"{d.get('day_number', '')} {d.get('day_sign', '')}".strip()
        if d.get("day_sign") else str(d.get("tzolkin", "—"))
    ),
    # Modules that would show method-version strings
    "taiyi": lambda d: str(d.get("taiyi_palace", d.get("palace", "—"))),
    "maramataka": lambda d: f"Lunar Day: {d.get('lunar_day', '—')}",
    "onmyodo": lambda d: str(d.get("yin_yang", d.get("element", "—"))),
}

# (id, value) → human-facing rewrite
REWRITE_RULES = {
    ("archetype_consensus", "0"):      "No dominant archetype",
    ("archetype_consensus", "none"):   "No dominant archetype",
    ("archetype_consensus", "None"):   "No dominant archetype",
    ("timing_consensus",    "MIXED"):  "Mixed timing",
    ("timing_consensus",    "mixed"):  "Mixed timing",
    ("timing_consensus",    "Mixed"):  "Mixed timing",
}

# Pattern-domain display rewrites
PATTERN_DOMAIN_REWRITES = {
    "Systemic Concordance":      "Where traditions agree",
    "Structural Concentration":  "Single-signal dominance",
    "Liminal Identity":          "Born between phases",
    "Metacognitive Orientation": "Observer stance",
    "Structural Foundation":     "Divided at the root",
    "Identity Structure":        "Split identity stream",
    "Onomantic Resonance":       "Name echoes the signal",
}

# Fields to skip in last-resort scalar fallback
META_SKIP = {"scholarship_fidelity", "scholarship_note"}

# Fields to skip in primary/secondary extraction
_PRIMARY_SKIP = {
    "constants_version", "note", "module_class", "dob",
    "arabic_name", "latin_name", "coordinates",
    "julian_day", "jdn_used", "scholarship_fidelity", "scholarship_note",
    "method",
}

# Regex for unresolved f-string placeholders
PLACEHOLDER_RE = _re.compile(r'\{[a-z_][a-z0-9_]*\}')

# Regex for error-string values that should suppress the card
_ERROR_PATTERNS = [
    _re.compile(r'requir', _re.I),
    _re.compile(r'^unknown location', _re.I),
    _re.compile(r'^no second profile', _re.I),
    _re.compile(r'^no natal chart', _re.I),
    _re.compile(r'^cannot geocode', _re.I),
    _re.compile(r'^natal_chart_data required', _re.I),
    _re.compile(r'^chart unavailable', _re.I),
]

# Method-version tokens that should never be displayed as values
_METHOD_RE = _re.compile(r'_v\d+$')


def clean_value(v: str) -> str:
    """Lightweight readability cleanup on scalar display values."""
    if not isinstance(v, str):
        return v
    if "_" in v and " " not in v and len(v) < 40:
        return v.replace("_", " ")
    return v


def _is_name_echo(value: str, subject: str, subject_ar: str = "") -> bool:
    """True if the value appears to just repeat the subject's input name."""
    if not value:
        return False
    v = value.strip()
    if len(v) < 4:
        return False

    if subject_ar:
        sa = subject_ar.strip()
        if sa:
            if v == sa or sa in v or v in sa:
                return True
            if any(ch >= "\u0600" and ch <= "\u06FF" for ch in v) and " " in v and len(v) >= 10:
                sa_tokens = set(sa.split())
                v_tokens = set(v.split())
                if v_tokens and len(v_tokens & sa_tokens) / len(v_tokens) >= 0.6:
                    return True

    if subject:
        s = subject.strip().upper()
        vu = v.upper()
        s_tokens = set(s.split())
        if vu == s:
            return True
        if " " not in v and vu in s_tokens and len(vu) >= 3:
            return True
        if " " in vu and len(vu) >= 10:
            v_tokens = set(vu.split())
            if v_tokens and len(v_tokens & s_tokens) / len(v_tokens) >= 0.6:
                return True
    return False


def _is_error_value(v: str) -> bool:
    """True if the value is an error/missing-data string."""
    if not v:
        return False
    for pat in _ERROR_PATTERNS:
        if pat.search(v):
            return True
    return False


def format_primary_value(result: Dict[str, Any]) -> str:
    """Extract a compact display value from a module result.

    Uses four tiers of preference:
      0. Per-module custom builder (ID_VALUE_BUILDERS)
      1. Canonical scalar keys
      2. Signal-suffix keys (_root, _total, etc.)
      3. Last resort: first scalar field in data
    """
    data = result.get("data", {}) or {}
    rid = result.get("id", "")

    # Tier 0: per-module custom builder
    builder = ID_VALUE_BUILDERS.get(rid)
    if builder is not None:
        try:
            built = builder(data)
            if built and isinstance(built, str) and built.strip():
                return built.strip()
        except Exception:
            pass

    # Tier 1: canonical primary-result keys
    canonical_keys = (
        "consensus", "consensus_element", "consensus_planet",
        "consensus_archetype",
        "period_quality", "pattern", "dominant_element", "syzygy_type",
        "almuten", "coefficient", "alignment_score",
        "day_master_stem", "day_master_element", "classification",
        "value", "number", "root", "total", "reduced", "reading",
        "pillar", "sign", "element", "result",
        "gematria_root", "ordinal_root", "cipher_root",
        "chaldean_root", "pythagorean_root", "total_gematria",
        "hidden_passion", "score", "count", "karmic_lesson_count",
        "cornerstone", "total_voids", "compound",
        "lot_count", "current_luck_pillar",
    )
    for key in canonical_keys:
        if key in data and data[key] not in (None, "", [], {}):
            v = data[key]
            if isinstance(v, bool):
                continue
            if isinstance(v, dict):
                continue  # Never stringify dicts as primary
            if isinstance(v, (list, tuple)) and v:
                return ", ".join(str(x) for x in v[:3])
            return str(v)

    # Tier 2: signal-suffix keys
    signal_suffixes = ("_root", "_total", "_sum", "_score", "_count",
                       "_level", "_pct")
    for k, v in data.items():
        if any(k.endswith(s) for s in signal_suffixes):
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float, str)) and str(v):
                return str(v)

    # Tier 3: last-resort scalar fallback
    for k, v in data.items():
        if k in META_SKIP or k in _PRIMARY_SKIP:
            continue
        if isinstance(v, bool) or isinstance(v, dict):
            continue
        if isinstance(v, (int, float, str)) and str(v):
            sv = str(v)
            # Skip method-version tokens
            if _METHOD_RE.search(sv):
                continue
            if len(sv) < 60:
                return sv
    return "—"


def resolve_display(result: Dict[str, Any], subject: str, subject_ar: str = "") -> Optional[str]:
    """Return the value to display, or None if this row should be hidden."""
    rid = result.get("id", "")
    if rid in ALWAYS_HIDE_IDS:
        return None

    raw = format_primary_value(result)
    v = (raw or "").strip()

    if v in HIDE_EXACT_VALUES:
        return None
    if _is_error_value(v):
        return None
    if _is_name_echo(v, subject, subject_ar):
        return None

    # Rewrite rules
    if (rid, v) in REWRITE_RULES:
        return REWRITE_RULES[(rid, v)]

    return clean_value(v)
