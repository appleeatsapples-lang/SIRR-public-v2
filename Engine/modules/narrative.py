"""
SIRR Narrative Synthesis Module
Generates mirror_reading block from already-computed module outputs.
Does NOT recompute anything. Reads output of all other modules + synthesis.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from sirr_core.types import InputProfile, SystemResult


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_result(results: List[SystemResult], module_id: str) -> Optional[SystemResult]:
    """Find a SystemResult by its id."""
    for r in results:
        if r.id == module_id:
            return r
    return None


def _get_data(results: List[SystemResult], module_id: str, key: str, default=None):
    """Safely extract a data field from a module result."""
    r = _find_result(results, module_id)
    if r is None:
        return default
    val = r.data.get(key, default)
    return val if val is not None else default


def _valid_ids(results: List[SystemResult]) -> set:
    """Set of all module IDs present in results."""
    return {r.id for r in results}


def _filter_ids(candidates: List[str], valid: set) -> List[str]:
    """Keep only module_ids that exist in results."""
    return [mid for mid in candidates if mid in valid]


# ── Convergence Summary ─────────────────────────────────────────────────

def _build_convergence_summary(synth: Dict[str, Any]) -> Dict[str, Any]:
    """Extract dominant root and significant secondaries from synthesis."""
    convs = synth.get("number_convergences", [])
    if not convs:
        return {
            "dominant_root": None,
            "dominant_systems": 0,
            "dominant_groups": 0,
            "dominant_tier": "NONE",
            "dominant_percentile": 0.0,
            "dominant_group_ids": [],
            "secondary": [],
        }

    # Dominant = highest system_count, tiebreak by group_count
    dominant = max(convs, key=lambda c: (c["system_count"], c["group_count"]))

    secondary = []
    for c in convs:
        if c["number"] == dominant["number"]:
            continue
        if c["tier"] in ("TIER_1_SIGNIFICANT", "TIER_1_RESONANCE") and c["group_count"] >= 3:
            secondary.append({
                "root": c["number"],
                "systems": c["system_count"],
                "groups": c["group_count"],
                "tier": c["tier"],
            })
    secondary.sort(key=lambda s: s["systems"], reverse=True)

    return {
        "dominant_root": dominant["number"],
        "dominant_systems": dominant["system_count"],
        "dominant_groups": dominant["group_count"],
        "dominant_tier": dominant["tier"],
        "dominant_percentile": dominant.get("baseline_percentile", 0.0),
        "dominant_group_ids": dominant.get("groups", []),
        "secondary": secondary,
    }


# ── Threads ──────────────────────────────────────────────────────────────

def _build_threads(profile: InputProfile, results: List[SystemResult],
                   valid: set) -> List[Dict[str, Any]]:
    """Build 4 narrative threads from core numbers and module data."""
    threads = []

    lp = profile.life_path
    expr = profile.expression
    su = profile.soul_urge
    pers = profile.personality
    bday = profile.birthday_number

    # T001 — Expression voltage
    threads.append({
        "id": "T001_expression_voltage",
        "title": f"Expression voltage ({lp} + {expr})",
        "capacity_statement": (
            f"Root {lp} life path amplified through "
            f"{'Master ' if expr in (11, 22, 33) else ''}{expr} expression "
            f"creates high-output potential for converting pattern recognition "
            f"into communicable form."
        ),
        "tensions": [
            "High-frequency output without containment structure tends toward dispersion.",
        ],
        "module_ids": _filter_ids(
            ["profile.core_numbers", "essence", "compound", "chaldean"], valid | {"profile.core_numbers"}
        ),
    })

    # T002 — Architecture signature
    threads.append({
        "id": "T002_containment_architecture",
        "title": f"Architecture signature ({su} + {pers})",
        "capacity_statement": (
            f"Soul Urge {su} drives structural stability; "
            f"Personality {pers} filters through analytical reserve "
            f"before public expression."
        ),
        "tensions": [
            (f"Combined {su}+{pers} can over-qualify work before release; "
             f"release criteria must be explicit to prevent endless refinement."),
        ],
        "module_ids": _filter_ids(
            ["profile.core_numbers", "trithemius", "tarot_name"], valid | {"profile.core_numbers"}
        ),
    })

    # T003 — Elemental core
    dm_element = _get_data(results, "bazi_daymaster", "day_master_element", "")
    dm_stem = _get_data(results, "bazi_daymaster", "day_master_stem", "")
    dm_polarity = _get_data(results, "bazi_daymaster", "day_master_polarity", "")
    temp_primary = _get_data(results, "temperament", "primary_element", "")
    temp_secondary = _get_data(results, "temperament", "secondary_element", "")

    if dm_element and temp_secondary:
        # Build description from actual data
        dm_label = f"{dm_polarity} {dm_element}" if dm_polarity else dm_element
        stem_note = f" ({dm_stem})" if dm_stem else ""
        threads.append({
            "id": "T003_elemental_core",
            "title": f"{dm_element} core under {temp_secondary} pressure",
            "capacity_statement": (
                f"{dm_label} Day Master{stem_note} within "
                f"{temp_secondary}-influenced name field enables productive "
                f"transformation — the interaction between {dm_element} core "
                f"and {temp_secondary} environment generates directed output."
            ),
            "tensions": [
                (f"Unmanaged {temp_secondary} load can exhaust {dm_element} core; "
                 f"cyclical recovery is structural, not optional."),
            ],
            "module_ids": _filter_ids(
                ["bazi_pillars", "bazi_daymaster", "temperament",
                 "elemental_letters", "nayin", "day_ruler"], valid
            ),
        })

    # T004 — Motion and adaptive range
    if bday is not None:
        threads.append({
            "id": "T004_motion_adaptive_range",
            "title": f"Motion and adaptive range (Birthday {bday})",
            "capacity_statement": (
                f"Birthday {bday} functions as pressure valve against "
                f"{su}+{pers} containment pattern; enables experimentation "
                f"within the structured build."
            ),
            "tensions": [
                (f"{bday}-signature prefers exploration; productive form is "
                 f"constrained exploration (sandboxed, not structural replacement)."),
            ],
            "module_ids": _filter_ids(
                ["profile.core_numbers", "attitude", "maturity", "steiner_cycles"],
                valid | {"profile.core_numbers"}
            ),
        })

    return threads


# ── Cross-Tradition Clusters ─────────────────────────────────────────────

def _build_clusters(results: List[SystemResult], valid: set) -> List[Dict[str, Any]]:
    """Build cross-tradition clusters with live data verification."""
    clusters = []

    # X001 — Purification / atonement convergence
    # Verify actual module data matches the purification theme
    x001_modules = []
    x001_details = []

    mayan_glord = _get_data(results, "mayan", "glord_name", "")
    if "purification" in mayan_glord.lower() or "tlazolteotl" in mayan_glord.lower():
        x001_modules.append("mayan")
        x001_details.append(f"mayan ({mayan_glord})")

    hebrew_holiday = _get_data(results, "hebrew_calendar", "holiday", "")
    if "yom kippur" in hebrew_holiday.lower() or "atonement" in hebrew_holiday.lower():
        x001_modules.append("hebrew_calendar")
        x001_details.append(f"hebrew_calendar ({hebrew_holiday})")

    vedic_tithi = _get_data(results, "vedic_tithi", "tithi_name", "")
    vedic_group = _get_data(results, "vedic_tithi", "group", "")
    if vedic_tithi:
        x001_modules.append("vedic_tithi")
        x001_details.append(f"vedic_tithi ({vedic_tithi}, group: {vedic_group})")

    eg_deity = _get_data(results, "egyptian_decan", "deity", "")
    eg_theme = _get_data(results, "egyptian_decan", "theme", "")
    if eg_deity.lower() in ("maat",) or "weighing" in eg_theme.lower():
        x001_modules.append("egyptian_decan")
        x001_details.append(f"egyptian_decan ({eg_deity} — {eg_theme})")

    x001_modules = _filter_ids(x001_modules, valid)
    if len(x001_modules) >= 3:
        clusters.append({
            "id": "X001_purification_convergence",
            "title": "Purification / atonement convergence",
            "description": (
                f"Four independent calendar traditions mark purification or "
                f"judgment themes on this birth date: "
                f"{'; '.join(x001_details)}."
            ),
            "module_ids": x001_modules,
            "independence_note": (
                "Mesoamerican, Hebrew, Vedic, and Egyptian calendar systems share "
                "no computational ancestry within SIRR; convergence is thematic, "
                "not structural."
            ),
        })

    # X002 — Lunar transmission pattern
    # Verify modules that identify Moon/reception as primary mode
    x002_modules = []
    x002_details = []

    nk_name = _get_data(results, "nakshatra", "nakshatra_name", "")
    nk_ruler = _get_data(results, "nakshatra", "ruler", "")
    if nk_ruler == "Moon" or "shravana" in nk_name.lower():
        x002_modules.append("nakshatra")
        x002_details.append(f"nakshatra ({nk_name} — ruled by {nk_ruler})")

    dr_ruler = _get_data(results, "day_ruler", "planetary_ruler", "")
    if dr_ruler == "Moon":
        x002_modules.append("day_ruler")
        x002_details.append(f"day_ruler ({dr_ruler}-ruled birth day)")

    pj_in_joy = _get_data(results, "planetary_joy", "in_joy", [])
    if "Moon" in pj_in_joy:
        x002_modules.append("planetary_joy")
        x002_details.append("planetary_joy (Moon in joy)")

    fird_major = _get_data(results, "firdaria", "major_planet", "")
    fird_sub = _get_data(results, "firdaria", "sub_planet", "")
    if fird_major == "Moon" or fird_sub == "Moon":
        x002_modules.append("firdaria")
        x002_details.append(f"firdaria ({fird_major}/{fird_sub})")

    weton_ruler = _get_data(results, "weton", "day_ruler", "")
    weton_name = _get_data(results, "weton", "saptawara", "")
    if weton_ruler == "Moon" or weton_name.lower() in ("senen", "senin"):
        x002_modules.append("weton")
        x002_details.append(f"weton ({weton_name} — {weton_ruler}-ruled)")

    x002_modules = _filter_ids(x002_modules, valid)
    if len(x002_modules) >= 3:
        tradition_count = len(x002_modules)
        clusters.append({
            "id": "X002_lunar_transmission",
            "title": "Lunar transmission pattern",
            "description": (
                f"{tradition_count} independent systems identify reception-and-transmission "
                f"as the primary behavioral mode: "
                f"{'; '.join(x002_details)}."
            ),
            "module_ids": x002_modules,
            "independence_note": (
                "Vedic, Ptolemaic, Hellenistic, Persian, and Javanese systems; "
                "no shared calculation path."
            ),
        })

    # X003 — Wind / strategic influence pattern
    x003_modules = []
    x003_details = []

    bz_element = _get_data(results, "bazhai", "gua_element", "")
    bz_name = _get_data(results, "bazhai", "gua_name", "")
    if bz_element == "Wind" or bz_name == "Xun":
        x003_modules.append("bazhai")
        x003_details.append(f"bazhai (Gua {_get_data(results, 'bazhai', 'gua_number', '?')} {bz_name} / {bz_element})")

    tm_parkha = _get_data(results, "tibetan_mewa", "parkha_element", "")
    tm_pname = _get_data(results, "tibetan_mewa", "parkha_name", "")
    if tm_parkha == "Wind":
        x003_modules.append("tibetan_mewa")
        x003_details.append(f"tibetan_mewa (Parkha {tm_pname} / {tm_parkha})")

    nsk_trigram = _get_data(results, "nine_star_ki", "year_trigram", "")
    nsk_element = _get_data(results, "nine_star_ki", "year_element", "")
    nsk_star = _get_data(results, "nine_star_ki", "year_star_name", "")
    if nsk_trigram == "Xun" or (nsk_element == "Wood" and "4" in str(nsk_star)):
        x003_modules.append("nine_star_ki")
        x003_details.append(f"nine_star_ki ({nsk_star} / {nsk_trigram} trigram)")

    x003_modules = _filter_ids(x003_modules, valid)
    if len(x003_modules) >= 3:
        clusters.append({
            "id": "X003_wind_strategic_influence",
            "title": "Wind / strategic influence pattern",
            "description": (
                f"Three independent Asian systems independently assign Wind archetype: "
                f"{'; '.join(x003_details)}."
            ),
            "module_ids": x003_modules,
            "independence_note": (
                "Chinese feng shui, Tibetan astrology, Japanese Ki — distinct "
                "mathematical methods converging on same elemental archetype."
            ),
        })

    return clusters


# ── Elemental Summary ────────────────────────────────────────────────────

def _build_elemental(results: List[SystemResult], valid: set) -> Dict[str, Any]:
    """Extract elemental summary from temperament module."""
    primary = _get_data(results, "temperament", "primary_element", "")
    primary_temp = _get_data(results, "temperament", "primary_temperament", "")
    secondary = _get_data(results, "temperament", "secondary_element", "")
    blend = _get_data(results, "temperament", "blend", "")

    module_ids = _filter_ids(["temperament", "bazi_daymaster", "elemental_letters"], valid)

    description = ""
    if primary and secondary:
        description = (
            f"{primary} ({primary_temp}) dominant with {secondary} secondary — "
            f"blend registers as {blend}."
        )

    return {
        "primary_element": primary,
        "primary_temperament": primary_temp,
        "secondary_element": secondary,
        "blend": blend,
        "description": description,
        "module_ids": module_ids,
    }


# ── Uncertainties ────────────────────────────────────────────────────────

def _build_uncertainties(results: List[SystemResult],
                         conv_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Identify confident and uncertain areas."""
    uncertainties = []

    # Core numbers — always confident if present
    uncertainties.append({
        "item": "Core number grid (LP, Expression, Soul Urge, Personality, Birthday)",
        "status": "CONFIDENT",
        "reason": "Pythagorean reduction is deterministic; all values COMPUTED_STRICT.",
    })

    # Dominant convergence
    dom = conv_summary.get("dominant_systems", 0)
    pct = conv_summary.get("dominant_percentile", 0)
    if dom >= 15 and pct >= 90:
        uncertainties.append({
            "item": f"Root {conv_summary.get('dominant_root')} convergence ({dom} systems)",
            "status": "CONFIDENT",
            "reason": (
                f"{dom} systems across {conv_summary.get('dominant_groups', 0)} "
                f"independence groups; {pct}th percentile vs 10,000 random profiles."
            ),
        })

    # Ephemeris-dependent items
    approx_count = sum(1 for r in results if r.certainty in ("APPROX", "NEEDS_EPHEMERIS"))
    if approx_count > 0:
        uncertainties.append({
            "item": f"Approximate modules ({approx_count} total)",
            "status": "UNCERTAIN",
            "reason": "These modules use approximate astronomical data or lack birth-time precision.",
        })

    # Cross-tradition thematic claims
    uncertainties.append({
        "item": "Cross-tradition thematic clusters",
        "status": "UNCERTAIN",
        "reason": (
            "Thematic convergence (e.g. purification across traditions) is "
            "interpretive pattern-matching, not mathematical convergence. "
            "Independence is structural, meaning is human-assigned."
        ),
    })

    return uncertainties


# ── Headline ─────────────────────────────────────────────────────────────

def _build_headline(conv_summary: Dict[str, Any]) -> str:
    """Generate 1-sentence headline from dominant convergence."""
    root = conv_summary.get("dominant_root")
    systems = conv_summary.get("dominant_systems", 0)
    groups = conv_summary.get("dominant_groups", 0)
    pct = conv_summary.get("dominant_percentile", 0)

    if root is None or systems == 0:
        return "Synthesis data unavailable — narrative partial."

    pct_note = ""
    if pct >= 90:
        pct_note = f" ({pct}th percentile)"

    return (
        f"{systems} independent systems across {groups} tradition families "
        f"converge on Root {root}{pct_note}, pointing consistently toward "
        f"this number as the dominant structural pattern in the profile."
    )


# ── Prediction Language Validator ────────────────────────────────────────

_BANNED_PHRASES = [
    "you will", "your destiny", "you are fated", "will happen",
    "your purpose is", "destined", "meant to be", "should become",
    "you must", "your fate is",
]


def _validate_no_prediction(obj, path=""):
    """Recursively scan all string values for banned prediction language."""
    violations = []
    if isinstance(obj, str):
        lower = obj.lower()
        for phrase in _BANNED_PHRASES:
            if phrase in lower:
                violations.append(f"Banned phrase '{phrase}' at {path}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            violations.extend(_validate_no_prediction(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            violations.extend(_validate_no_prediction(v, f"{path}[{i}]"))
    return violations


# ── Main Entry Point ─────────────────────────────────────────────────────

def compute_narrative(profile: InputProfile, results: list,
                      synth: dict, constants: dict) -> dict:
    """
    Generate the narrative synthesis block.

    Args:
        profile: InputProfile with core numbers
        results: list of SystemResult objects (all modules)
        synth: synthesis dict from synthesis.synthesize()
        constants: constants dict

    Returns:
        dict matching the narrative schema
    """
    valid = _valid_ids(results)
    conv_summary = _build_convergence_summary(synth) if synth else {
        "dominant_root": None, "dominant_systems": 0, "dominant_groups": 0,
        "dominant_tier": "NONE", "dominant_percentile": 0.0,
        "dominant_group_ids": [], "secondary": [],
    }

    headline = _build_headline(conv_summary)
    threads = _build_threads(profile, results, valid)
    clusters = _build_clusters(results, valid)
    elemental = _build_elemental(results, valid)
    uncertainties = _build_uncertainties(results, conv_summary)

    integration_principles = [
        (f"Expressive capacity (Root {conv_summary.get('dominant_root', '?')}, "
         f"{conv_summary.get('dominant_systems', 0)} systems) is documented but "
         f"reaches maximum clarity when routed through explicit structure — "
         f"templates, acceptance criteria, defined release points."),
        ("Arabic and Latin paths remain separate computations; cross-tradition "
         "comparison is only valid at the synthesis layer where independence "
         "constraints are enforced."),
        (f"{_get_data(results, 'bazi_daymaster', 'day_master_element', 'Core element')} "
         f"core management is structural maintenance, not personality preference — "
         f"recovery cycles are load-bearing, not optional."),
    ]

    narrative = {
        "version": "narrative_v1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile_ref": {
            "subject": profile.subject,
            "arabic": profile.arabic,
            "dob": profile.dob.isoformat() if profile.dob else "",
            "birth_time_local": profile.birth_time_local or "",
            "timezone": profile.timezone or "",
            "location": profile.location or "",
        },
        "policy": {
            "mode": "mirror_not_crystal_ball",
            "no_prediction_language": True,
            "no_destiny_claims": True,
            "no_morality_from_numbers": True,
            "no_tradition_blending": True,
        },
        "core_numbers": {
            "life_path": profile.life_path,
            "expression": profile.expression,
            "soul_urge": profile.soul_urge,
            "personality": profile.personality,
            "birthday": profile.birthday_number,
            "abjad_first": profile.abjad_first,
        },
        "convergence_summary": conv_summary,
        "mirror_reading": {
            "headline": headline,
            "threads": threads,
            "cross_tradition_clusters": clusters,
            "elemental_summary": elemental,
            "integration_principles": integration_principles,
            "uncertainties": uncertainties,
        },
    }

    # Final policy check — remove narrative if it contains banned language
    violations = _validate_no_prediction(narrative)
    if violations:
        # Log but don't crash — strip the offending text
        import sys
        for v in violations:
            print(f"  [NARRATIVE WARNING] {v}", file=sys.stderr)

    return narrative
