"""
SYNTHESIS ENGINE — Cross-System Convergence Detector
This is SIRR's moat. No single tradition can see what this module sees.

Rules:
1. Only counts agreement from LOCKABLE certainties (COMPUTED_STRICT, LOOKUP_FIXED)
2. Applies independence groups — agreement within a group counts as ONE vote
3. Requires >= 3 systems AND >= 2 independence groups for a RESONANCE claim
4. Tags every claim with its evidence chain
5. Uses CONVERGENCE_FIELDS whitelist — only extracts numbers from meaningful fields,
   preventing inflation from magic-square outputs and frequency tables
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
from sirr_core.types import SystemResult

LOCKABLE = {"COMPUTED_STRICT", "LOOKUP_FIXED"}

# ── CORE 25 MODULE SET ──
# Slim high-signal panel used by sirr_core_25.py. Mirror of CORE_25_LAYERS
# in sirr_core_25.py and the list in MASTER_CONTEXT.md. When synthesize()
# is called with core25_mode=True, convergence detection is restricted to
# exactly these 25 modules and the cluster-primary + cluster-secondary
# panels are surfaced as explicit top-level keys in the output.
CORE_25_CLUSTER_PRIMARY = frozenset({
    "subconscious_self",
    "solar_return",
    "solar_lunar",
    "zi_wei_dou_shu",
    "luminous_dark",
    "arabic_parts",
    "ifa",
    "personal_year",
    "pinnacles",
    "planes_of_expression",
    "mandaean_gematria",
    "lo_shu_grid",
    "ethiopian_asmat",
    "abjad_kabir",
})
CORE_25_CLUSTER_SECONDARY = frozenset({
    "zairja",
    "buduh",
    "atbash",
    "agrippan",
    "thelemic_gematria",
    "armenian_gematria",
    "tarot_greer_birth_cards",
    "enneagram_dob",
    "sarvatobhadra",
    "sect",
    "essential_dignities",
})
CORE_25_MODULES = CORE_25_CLUSTER_PRIMARY | CORE_25_CLUSTER_SECONDARY

# ── Load Monte Carlo baselines (stratified by name length) ──
# Multiple baselines are kept on disk. We load every one we can find and
# pick the right one per-profile at synthesize() time via _select_baseline.
# This lets a "full nasab" profile be compared against a long-name baseline
# instead of the (unfair) short-name default.
_ENGINE_DIR = Path(__file__).parent.parent

_BASELINE_SOURCES: Dict[str, List[Path]] = {
    # Default — trained on 3-word names
    "default": [
        _ENGINE_DIR / "reports" / "monte_carlo_results.json",
        _ENGINE_DIR / "monte_carlo_baseline.json",
        _ENGINE_DIR / "monte_carlo" / "monte_carlo_baseline.json",
    ],
    # Length-matched — trained on 8-word nasab chains
    "long_names": [
        _ENGINE_DIR / "monte_carlo" / "monte_carlo_long_names.json",
    ],
}

def _load_first_available(paths: List[Path]):
    for p in paths:
        if p.exists():
            try:
                return json.loads(p.read_text()), str(p)
            except Exception:
                continue
    return None, None

_BASELINES: Dict[str, Dict[str, Any]] = {}
for _stratum, _paths in _BASELINE_SOURCES.items():
    _data, _src = _load_first_available(_paths)
    if _data:
        _BASELINES[_stratum] = {"data": _data, "source": _src}

# Back-compat alias: legacy code reading _BASELINE (module global) still works,
# pointing at the default stratum. Per-call selection uses _select_baseline().
_BASELINE = _BASELINES.get("default", {}).get("data")


def _select_baseline(profile) -> tuple:
    """Pick the most appropriate baseline for a profile's name length.

    Returns (baseline_dict_or_None, stratum_label, source_path_or_None).

    Rule: profiles with 7+ name words (full nasab territory) use the
    long-names baseline when available. Everything else uses default.
    """
    # No profile or no long_names baseline → default
    if profile is None or "long_names" not in _BASELINES:
        d = _BASELINES.get("default")
        if d:
            return d["data"], "default", d["source"]
        return None, "default", None

    subject = getattr(profile, "subject", "") or ""
    word_count = len([w for w in subject.split() if w.strip()])

    if word_count >= 7:
        e = _BASELINES["long_names"]
        return e["data"], "long_names", e["source"]

    d = _BASELINES.get("default")
    if d:
        return d["data"], "default", d["source"]
    return None, "default", None

# Load lineage rubric for derivedness weighting
# Modules with derivedness > 0.7 are excluded from convergence vote counting
# to prevent inflated agreement from correlated upstream outputs.
_LINEAGE_PATH = Path(__file__).parent.parent / "data" / "gemini_mapping_tables.json"
_HIGH_DERIVEDNESS: set[str] = set()
if _LINEAGE_PATH.exists():
    try:
        _tables = json.loads(_LINEAGE_PATH.read_text())
        _rubric = _tables.get("lineage_rubric", {}).get("modules", {})
        _HIGH_DERIVEDNESS = {mid for mid, info in _rubric.items()
                            if info.get("derivedness", 0) > 0.7}
    except Exception:
        pass

# ── CONVERGENCE FIELD WHITELIST ──
# Only these data keys per module carry meaningful convergence signal.
# Prevents inflation from magic squares, frequency tables, and grid dumps.
# Key = module_id, Value = set of data field names to extract numbers from.
# None = use all fields (legacy behavior, for simple modules).
CONVERGENCE_FIELDS = {
    # Flying star: only center + current year star, NOT all 9 sectors
    "flying_star": {"birth_year_star", "current_year_star"},
    # Lo Shu: only missing digits matter for gap analysis, not grid values
    "lo_shu_grid": {"missing", "concentrated"},
    # Abjad: root is the signal, not digit frequencies or letter counts
    "abjad_kabir": {"root"},
    "abjad_saghir": {"root", "dominant_digit"},
    "abjad_wusta": {"root"},
    "abjad_maghribi": {"root"},
    # Hebrew: root is the signal
    "hebrew_gematria": {"gematria_root"},
    # Mandaean: root is the signal
    "mandaean_gematria": {"gematria_root"},
    "malwasha": set(),  # categorical output (protective name), not numeric
    "prashna_natal": {"prashna_root"},  # Vedic horary Moon nakshatra root (APPROX — today at noon)
    "rectification": set(),  # diagnostic infrastructure, not convergence-eligible
    "horary_timing": set(),  # diagnostic timing context, not convergence-eligible
    "jaimini_karakas": set(),  # Jaimini significators — categorical, not convergence-eligible
    "jaimini_argala": set(),  # Jaimini argala — categorical house analysis
    "jaimini_navamsha": set(),  # D9 chart — categorical divisional chart
    "astrocartography": set(),  # geographic line data, not convergence-eligible
    "kp_sublords": set(),  # KP sub-lord hierarchy, not convergence-eligible
    "draconic_chart": set(),  # draconic positions, not convergence-eligible
    "solar_return_deep": set(),  # interpretive deep read, not convergence-eligible
    "electional_windows": set(),  # timing windows, not convergence-eligible
    "muhurta": set(),  # daily muhurta timing, not convergence-eligible
    "synastry": set(),  # cross-chart comparison, not convergence-eligible
    "avgad": {"avgad_root"},  # avgad_root only — original_root duplicates base gematria
    "atbash": {"atbash_root"},
    "albam": {"albam_root"},
    # Notarikon: roots only
    "notarikon": {"arabic_root", "latin_root"},
    # Bridges: tension values are the signal, not the inputs
    "bridges": {"bridges", "max_tension"},
    # Challenges: challenge values only
    "challenges": {"challenge_1", "challenge_2", "challenge_3", "challenge_4"},
    # Pinnacles: pinnacle values only
    "pinnacles": {"pinnacle_1", "pinnacle_2", "pinnacle_3", "pinnacle_4"},
    # Personal year: the computed values
    "personal_year": {"personal_year", "personal_month", "personal_day"},
    # Compound: reduced values from the compound meanings
    "compound": None,  # compound has nested dicts, use all
    # BaZi pillars: no raw numbers to extract (elements, not digits)
    "bazi_pillars": set(),  # skip number extraction, use element extraction only
    "bazi_daymaster": {"support_count", "drain_count"},  # Five Element balance counts
    "bazi_luck_pillars": set(),  # timeline data, not convergence-eligible
    # Mayan: tzolkin number and G-Lord
    "mayan": {"tzolkin_number", "tzolkin_sign_index"},
    # Cardology: solar_value
    "cardology": {"solar_value"},
    # Hijri: day/month
    "hijri": {"birth_day", "birth_month"},
    # Hebrew calendar: day
    "hebrew_calendar": {"hebrew_day", "hebrew_month_number"},
    # Nine Star Ki: star values
    "nine_star_ki": {"year_star", "month_star"},
    # Subconscious: score
    "subconscious_self": {"score"},
    # Hidden passion: the passion number and frequency
    "hidden_passion": {"hidden_passion", "frequency"},
    # Vimshottari: current age data only
    "vimshottari": set(),  # timeline has too many numbers; elements matter more
    # Nakshatra: nakshatra number and pada
    "nakshatra": {"nakshatra_number", "pada"},
    # Manazil: manzil number
    "manazil": {"manzil_number"},
    # Decan: decan number
    "decan": {"decan"},
    # Profection: house number
    "profection": {"house"},
    # Elemental letters: skip (percentages, not convergence-eligible ints)
    "elemental_letters": set(),
    # Solar/lunar: counts
    "solar_lunar": {"solar_count", "lunar_count"},
    # Luminous/dark: counts
    "luminous_dark": {"luminous_count", "dark_count"},
    # Phase 2: Dimensional expansion
    "chaldean": {"chaldean_root"},  # Root number is the signal
    "ifa": {"closed_marks", "open_marks"},  # Binary mark counts
    "egyptian_decan": {"decan_number"},  # Which of 36 decans

    # ── P2: CONVERGENCE WHITELIST COMPLETION (62 modules) ──

    # Gematria battery: root only — NOT letter breakdowns or raw totals
    "agrippan": {"root"},
    "armenian_gematria": {"root"},
    "coptic_isopsephy": {"root"},
    "georgian_gematria": {"root"},
    "greek_isopsephy": {"root"},
    "thelemic_gematria": {"root"},
    "trithemius": {"cipher_root"},
    "latin_ordinal": {"ordinal_root", "reverse_root"},
    "ethiopian_asmat": {"root"},

    # BaZi sub-modules: categorical (element extraction handles elements)
    "bazi_combos": set(),       # Structural relationships, no convergence numbers
    "bazi_growth": set(),       # Phase names are categorical
    "bazi_hidden_stems": set(), # Element distribution, pillar objects
    "bazi_ten_gods": set(),     # God names are categorical
    "bazi_shensha": {"star_count"},  # Count of special stars found

    # Calendar/cycle systems: meaningful position numbers only
    "chinese_zodiac": {"sexagenary_position"},  # 1-60 cycle position
    "dreamspell": {"kin", "tone_number", "seal_number"},
    "tonalpohualli": {"trecena", "day_sign_index"},
    "tibetan_mewa": {"mewa_number"},
    "bazhai": {"gua_number"},
    "nayin": {"sexagenary_position"},  # 1-60 sexagenary cycle
    "pawukon": set(),           # Wuku names are categorical
    "primbon": {"neptu_sum"},   # Reduced Javanese sum
    "steiner_cycles": {"cycle_number"},

    # Tarot: card numbers only — NOT raw sums or letter breakdowns
    "tarot_birth": {"primary_card_number", "secondary_card_number"},
    "tarot_name": {"expression_card_number", "soul_card_number"},
    "tarot_year": {"card_number"},

    # Western numerology: reduced/final numbers only
    "attitude": {"reduced"},
    "enneagram_dob": {"enneagram_type"},
    "essence": {"reduced"},
    "maturity": {"maturity_number"},
    "karmic_debt": {"count"},
    "life_purpose": {"birth_day_reduced", "millman_final"},
    "dwad": {"dwad_number"},

    # Islamic Ilm al-Huruf: reduced results — NOT grids or intermediate sums
    "bast_kasr": {"hidden_root"},
    "buduh": {"center_offset"},
    "istikhara_adad": {"mod_4", "mod_7", "mod_9", "mod_12"},
    "jafr": {"seed_offset"},
    "taksir": {"depth"},
    "zakat_huruf": set(),       # Zakat values are tradition-specific intermediates
    "quranic_figures": set(),  # Corpus-level structural analysis, no per-subject convergence fields
    "torah_figures": set(),    # Corpus-level structural analysis, no per-subject convergence fields
    "nt_figures": set(),       # Corpus-level structural analysis, no per-subject convergence fields
    "cross_scripture": set(),  # Cross-tradition intersection, no per-subject convergence fields
    # Arabic Linguistic Sciences
    "arabic_roots": {"root_abjad_root"},  # Root letters abjad reduction
    "arabic_morphology": set(),  # Categorical: voice/class distribution, no convergence numbers
    "name_semantics": set(),  # Categorical: semantic clusters, no convergence numbers
    "arabic_phonetics": set(),  # Categorical: makhraj distribution, no convergence numbers
    "arabic_letter_nature": set(),  # Categorical: element/planet/sign distribution, overlap with elemental_letters
    # Wave 1 — Structural Arabic Deepening
    "digit_patterns": {"digit_sum_root", "reverse_root"},
    "lineage_computation": set(),  # Sequence analysis, no single convergence number
    "hijri_calendar_encoding": {"year_digit_root", "full_digit_root", "combined_root"},
    "calligraphy_structure": set(),  # Categorical: visual letter properties
    "divine_breath": set(),  # Categorical: breath zone distribution
    "letter_position_encoding": {"weight_root"},
    "abjad_visual_architecture": set(),  # Categorical: dot/void/interruption metrics
    "name_weight": set(),  # Categorical: syllable weight distribution
    "arabic_rhetoric": set(),  # Categorical: rhetorical figure detection
    "sonority_curve": set(),  # Categorical: sonority contour shape
    "larger_awfaq": set(),  # Magic square grids, no convergence number
    "qibla_as_axis": set(),  # Directional, no convergence number
    "prayer_times_as_timing": set(),  # Timing periods, categorical
    "chronobiology": set(),  # Seasonal/circadian, categorical
    "void_matrix": set(),  # Comparative: absence analysis
    "barzakh_coefficient": set(),  # Comparative: fixed/kinetic ratio
    "hermetic_alignment": set(),  # Comparative: cross-axis agreement
    "execution_pattern_analysis": set(),  # Comparative: void/expression compound
    "minimum_viable_signature": set(),  # Comparative: irreducible facts

    # Categorical-only: skip number extraction, element extraction handles them
    "ars_magna": set(),         # Dignity categories, not numbers
    "birth_rune": set(),        # Rune name, meaning
    "celtic_tree": set(),       # Tree name, meaning
    "cornerstone": set(),       # Letter names
    "day_ruler": set(),         # Planet/element names
    "firdaria": set(),          # Planet names, period ranges
    "gd_correspondences": set(),  # Echoes core numbers (redundant)
    "god_of_day": set(),        # Deity name
    "ogham": set(),             # Tree names, stroke patterns
    "planetary_hours": {"birth_hour", "hours_from_sunrise"},  # Temporal position values
    "planetary_kameas": {"kamea_order", "name_position_in_kamea"},  # Rose Cross square position
    "temperament": set(),       # Temperament labels, quality names
    "tree_of_life": set(),      # Sephirah names (echoes core numbers)

    # Infrastructure: no convergence signal
    "biorhythm": set(),         # Percentages, cycle positions
    "julian": set(),            # Raw JDN, not convergence-eligible
    "wafq": set(),              # Magic square (derived from abjad, redundant)

    # Other specific modules
    "geomancy": {"index"},            # Figure index 1-16
    "iching": {"hexagram_number"},    # 1-64 (partially captured in 1-33 range)
    "sabian": set(),                  # Symbol text, interpretive content
    "meihua": {"moving_line"},        # Line position 1-6
    "rose_cross_sigil": {"unique_petals"},  # Count of unique petal positions
    "vedic_tithi": {"tithi_number"},  # 1-30
    "vedic_yoga": {"yoga_number"},    # 1-27

    # Ephemeris Phase 1: Foundation
    "natal_chart": set(),  # Big Three are categorical strings, not numeric — source module for downstream
    "house_system": {"mc_house"},     # MC house position
    "aspects": {"aspect_count"},      # Total aspect count only

    # Ephemeris Phase 2: High-value systems
    "essential_dignities": {"total_score", "dignified_count", "debilitated_count"},
    "sect": {"in_sect_count", "out_sect_count"},  # Hellenistic dignity counts
    "arabic_parts": {"fortune_house", "spirit_house"},  # House positions only
    "solar_return": {"sun_house"},                        # Return Sun's house is key convergence value
    "progressions": set(),                                # Timing data, categorical — no numeric convergence
    "fixed_stars": {"conjunction_count", "royal_conjunction_count"},

    # ── FINAL 2: added Feb 27, 2026 ──
    "planetary_joy": {"joy_count"},           # Count of planets in natal joy position
    "weton": {"total_neptu", "weton_cycle_position"},  # Javanese neptu sum + 210-day cycle

    # ── Modules 112-113: added Feb 27, 2026 ──
    "akan_kra_din": set(),                    # Categorical (day name, archetype) — no numeric convergence
    "persian_abjad": {"root"},                # Abjad root is the convergence signal

    # ── Modules 114-116: added Feb 27, 2026 ──
    "antiscia": {"conjunction_count"},        # Shadow conjunction count
    "yogini_dasha": set(),                    # Timeline data, categorical — no numeric convergence
    "ashtottari_dasha": {"rahu_house"},        # Rahu's natal house position

    # ── Modules 117-118: Birth-time-gated, added Feb 27, 2026 ──
    "zi_wei_dou_shu": {"lunar_month", "lunar_day"},  # Lunar calendar positions
    "shadbala": set(),  # Planet names are categorical strings; scores are unique floats

    # ── Modules 119-130: Ephemeris Phase 3, added Feb 27, 2026 ──
    "almuten": {"almuten_score"},                         # Chart winner's cumulative dignity score
    "reception": {"mutual_reception_count"},              # Count of mutual receptions
    "declinations": {"parallel_count", "contraparallel_count", "oob_count"},  # Aspect counts
    "midpoints": {"activation_count", "unique_midpoint_count"},  # Midpoint activations
    "harmonic_charts": {"total_conjunction_count"},        # Total harmonic conjunctions
    "zodiacal_releasing": set(),                          # Timeline data, categorical
    "solar_arc": {"contact_count"},                       # Number of current SA contacts
    "dorothean_chronocrators": set(),                     # Categorical (ruler names, periods)
    "ashtakavarga": {"strongest_bindus", "weakest_bindus"},  # Extreme SAV values
    "shodashavarga": set(),                               # Categorical chart placements
    "tasyir": {"current_contact_count"},                  # Current directional hits
    "kalachakra_dasha": {"pada"},                         # Navamsha pada number (1-4)

    # ── Batch 18a: 4 new modules, added Feb 28, 2026 ──
    "bonification": {"total_bonified", "total_maltreated"},  # Count of bonified/maltreated planets
    "zairja": {"manzil_index"},                              # Composite index (abjad+ASC)%28 — abjad_sum excluded to avoid abjad_kabir duplication
    "qimen": {"ju_number"},                                  # Qi Men Dun Jia palace number (1-9)
    "liu_ren": set(),                                        # Categorical (branch names, elements) — no numeric convergence

    # ── Batch 18b: 5 new modules, added Feb 28, 2026 ──
    "primary_directions": {"total_events"},                  # Count of direction events computed
    "chara_dasha": set(),                                    # Categorical (sign names, timeline) — no numeric convergence
    "sarvatobhadra": {"vedha_count", "positive_vedhas", "negative_vedhas"},  # Vedha interaction counts
    "tajika": {"varsha_year"},                               # Tajika year number (age-based)
    "kp_system": set(),                                      # Sub-lord names are categorical

    # ── Batch 19: 3 new modules, added Feb 28, 2026 ──
    "taiyi": {"taiyi_palace", "densest_palace"},                 # Palace numbers (1-9 excl 5)
    "onmyodo": set(),                                            # Categorical (element names, directions, day qualities)
    "uranian": {"picture_count"},                                # Count of planetary pictures within orb

    # ── Batch 20: 2 new modules, added Feb 28, 2026 ──
    "nadi_amsa": set(),                                              # Categorical (tattwa names, nadi groups)
    "maramataka": {"lunar_day"},                                     # Numeric lunar day 1-30

    # ── Batch 21a: Babylonian sidereal, added Feb 28, 2026 ──
    "babylonian_horoscope": {"lunar_day"},                           # Numeric lunar day 1-30

    # ── Batch 21b: Vedic triple-wheel timing, added Mar 1, 2026 ──
    "sudarshana": {"active_house"},                                  # Numeric house 1-12 (same as profection)

    # ── Round 2: 3 new modules, added Mar 4, 2026 ──
    "mahabote": {"remainder", "birth_planet_house"},                 # Year-cycle remainder + birth planet house position
    "human_design": set(),                                           # Categorical (type/authority/profile names) — no numeric convergence
    "gene_keys": set(),                                              # Categorical (shadow/gift/siddhi names) — no numeric convergence

    # ── Round 4: Cross-tradition expansion, added Apr 2026 ──
    # Vedic (5)
    "kala_sarpa_check": {"ksy_present"},                              # Boolean: yoga present or not
    "panchamahabhuta": set(),                                         # Categorical (element names) — no numeric convergence
    "ayurvedic_constitution": set(),                                  # Categorical (dosha names) — no numeric convergence
    "mantra_seed_syllable": {"nakshatra_index", "pada"},              # Numeric nakshatra + pada
    "vedic_gem_prescription": set(),                                  # Categorical (gem/planet names) — no numeric convergence

    # Chinese (3)
    "bazi_10_year_forecast": set(),                                   # Categorical (period quality, element names) — no numeric convergence
    "zi_wei_deeper": set(),                                           # Categorical (star names) — no numeric convergence
    "four_pillars_balance": set(),                                    # Categorical (element balance) — no numeric convergence

    # Hebrew (3)
    "gematria_word_matches": {"root"},                                # Digital root of Hebrew gematria value
    "sephirotic_path_analysis": set(),                                # META — categorical sephirot names
    "solomonic_correspondences": set(),                               # META — categorical (angel/planet names)

    # African (1)
    "african_day_name_extended": set(),                               # Categorical (day names) — no numeric convergence

    # Western (2)
    "enneagram_deeper": set(),                                        # META — categorical (type/wing/group names)
    "hermetic_element_balance": set(),                                # Categorical (element balance) — no numeric convergence

    # Scientific (2)
    "circadian_medicine": set(),                                      # Categorical (organ, chronotype) — no numeric convergence
    "seasonal_psychology": set(),                                     # Categorical (temperament tendency) — no numeric convergence

    # Bridge (4)
    "element_consensus": set(),                                       # Bridge — synthesis-level, no convergence feed
    "timing_consensus": set(),                                        # Bridge — synthesis-level, no convergence feed
    "planetary_ruler_consensus": set(),                                # Bridge — synthesis-level, no convergence feed
    "archetype_consensus": set(),                                     # META bridge — synthesis-level, no convergence feed

    # ── Round 5 Wave 1: Decoz layer, added Apr 2026 ──
    "balance_number": {"balance_number"},                                # Single-digit balance root
    "rational_thought": {"rational_thought"},                            # Single-digit rational thought root
    "inclusion_table": {"missing_digits", "dominant_digits"},            # Missing + dominant digit lists
    "special_letters": {"first_vowel_value", "first_consonant_value"},   # Pythagorean values
    "period_cycles": set(),                                              # Period numbers are structural, not convergence
    "transit_letters": set(),                                            # Age-dependent letter cycling — categorical
    "yearly_essence_cycle": {"essence_number"},                          # Reduced essence root
    "minor_numbers": set(),                                              # NEEDS_INPUT unless current_name provided

    # ── Round 5 Wave 2: Tarot + Esoteric + Hellenistic, added Apr 2026 ──
    "tarot_greer_birth_cards": {"constellation_root", "hidden_factor_numbers"},  # Constellation root + hidden factor (personality/soul excluded — duplicate of tarot_birth)
    "greer_zodiac_card": {"zodiac_card_number"},                         # Major Arcana card number from Sun sign
    "prenatal_syzygy": set(),                                            # Categorical: syzygy type/sign, not convergence-eligible
    "cheiro_extensions": {"compound_number", "compound_root"},           # Cheiro compound number + root
    "roman_chronogram": {"chronogram_total", "chronogram_root"},         # Roman numeral letter sum + root
    "hebrew_aiq_beker": {"chamber_root", "dominant_chamber"},            # AIQ BKR chamber root + dominant chamber

    # ── Round 5 Wave 3: Cross-tradition, added Apr 2026 ──
    "tibetan_parkha": set(),                                             # Categorical: parkha name/element/direction
    "tibetan_elements": set(),                                           # Categorical: lo/srog element names
    "tamil_panchapakshi": set(),                                         # Categorical: bird name
    "chinese_jian_chu": set(),                                           # Categorical: officer name/quality
    "igbo_market_day": set(),                                            # Categorical: market day name/element
    "zoroastrian_day_yazata": set(),                                     # Categorical: yazata name/element
    "vedic_arudha_pada": set(),                                          # Categorical: arudha sign
    "vedic_upapada_lagna": set(),                                        # Categorical: upapada sign
    "vedic_pushkara_navamsha": set(),                                    # Boolean: pushkara status
    "bazi_san_he_san_hui": set(),                                        # Structural: combo presence (boolean/count)
    "zwds_si_hua_palace": set(),                                         # Categorical: star names per transformation
    "hebrew_mispar_variants": {"gadol_root", "siduri_root", "boneeh_root", "hakadmi_root"},  # 4 gematria roots

    # ── Round 5 Wave 4: Planes of Expression, added Apr 2026 ──
    "planes_of_expression": {"physical_root", "mental_root", "emotional_root", "intuitive_root"},  # 4 plane roots
}

# Which independence group does each system belong to?
# Groups represent what INPUT the module primarily depends on.
SYSTEM_TO_GROUP = {
    # === Arabic name (profile.arabic → Abjad/letter values) ===
    "abjad_kabir": "arabic_name",
    "abjad_saghir": "arabic_name",
    "abjad_wusta": "arabic_name",
    "abjad_maghribi": "arabic_name",
    "avgad": "arabic_name",
    "bast_kasr": "arabic_name",
    "buduh": "arabic_name",
    "elemental_letters": "arabic_name",
    "ethiopian_asmat": "arabic_name",
    "hebrew_gematria": "arabic_name",  # Arabic→Hebrew transliteration
    "mandaean_gematria": "mandaean_name",  # Arabic→Mandaean transliteration (independent 24-letter system)
    "istikhara_adad": "arabic_name",
    "jafr": "arabic_name",
    "luminous_dark": "arabic_name",
    "notarikon_ar": "arabic_name",
    "solar_lunar": "arabic_name",
    "taksir": "arabic_name",
    "tartib": "arabic_name",
    "zakat_huruf": "arabic_name",
    "arabic_letter_nature": "arabic_name",  # al-Buni Ṭabāʾiʿ al-Ḥurūf (letter natures) — added 2026-04-17

    # === Latin name (profile.subject → letter values/ciphers) ===
    "agrippan": "latin_name",
    "albam": "latin_name",
    "armenian_gematria": "latin_name",
    "ars_magna": "latin_name",
    "atbash": "latin_name",
    "coptic_isopsephy": "latin_name",
    "cornerstone": "latin_name",
    "georgian_gematria": "latin_name",
    "greek_isopsephy": "latin_name",
    "hidden_passion": "latin_name",
    "latin_ordinal": "latin_name",
    "notarikon_la": "latin_name",
    "ogham": "latin_name",
    "pythagorean": "latin_name",
    "rose_cross_sigil": "latin_name",
    "subconscious_self": "latin_name",
    "tarot_name": "latin_name",
    "thelemic_gematria": "latin_name",
    "trithemius": "latin_name",

    # === Chaldean name (different letter-value system) ===
    "chaldean": "chaldean_name",

    # === Birth digits (profile.dob → pure digit math) ===
    "attitude": "birth_digits",
    "biorhythm": "birth_digits",
    "birthday": "birth_digits",
    "bridges": "birth_digits",
    "challenges": "birth_digits",
    "compound": "birth_digits",
    "enneagram_dob": "birth_digits",
    "essence": "birth_digits",
    "karmic_debt": "birth_digits",
    "life_path": "birth_digits",
    "life_purpose": "birth_digits",
    "lo_shu": "birth_digits",
    "lo_shu_grid": "birth_digits",
    "maturity": "birth_digits",
    "personal_year": "birth_digits",
    "pinnacles": "birth_digits",
    "tarot_birth": "birth_digits",

    # === Birth calendar (profile.dob → calendar conversion/cycle) ===
    "bazhai": "chinese_calendar",
    "bazi_combos": "chinese_calendar",
    "bazi_hidden_stems": "chinese_calendar",
    "bazi_pillars": "chinese_calendar",
    "bazi_daymaster": "chinese_calendar",
    "bazi_luck_pillars": "chinese_calendar",
    "bazi_shensha": "chinese_calendar",
    "bazi_ten_gods": "chinese_calendar",
    "birth_rune": "germanic_celtic_calendar",
    "cardology": "hellenistic_day",
    "celtic_tree": "germanic_celtic_calendar",
    "chinese_year": "chinese_calendar",
    "chinese_zodiac": "chinese_calendar",
    "day_of_week": "hellenistic_day",
    "day_ruler": "hellenistic_day",
    "decan": "hellenistic_day",
    "dreamspell": "mayan_calendar",
    "dwad": "solar_cycle",
    "firdaria": "hellenistic_day",
    "flying_star": "chinese_calendar",
    "geomancy": "hellenistic_day",
    "god_of_day": "hellenistic_day",
    "hebrew_calendar": "hebrew_calendar_family",
    "hijri": "hijri_calendar",
    "iching": "hellenistic_day",
    "julian": "jdn_infrastructure",
    "mayan": "mayan_calendar",
    "nayin": "chinese_calendar",
    "nine_star_ki": "chinese_calendar",
    "pawukon": "indo_javanese_calendar",
    "primbon": "indo_javanese_calendar",
    "profection": "hellenistic_day",
    "sabian": "hellenistic_day",
    "solar_degree": "solar_cycle",
    "tibetan_mewa": "tibetan_calendar",
    "tonalpohualli": "mayan_calendar",

    # === Astronomical (needs ephemeris data) ===
    "ascendant": "astronomical",
    "arabic_parts": "astronomical",
    "aspects": "astronomical",
    "egyptian_decan": "astronomical",
    "essential_dignities": "astronomical",
    "house_system": "astronomical",
    "manazil": "astronomical",
    "moon_phase": "astronomical",
    "nakshatra": "astronomical",
    "natal_chart": "astronomical",
    "sect": "astronomical",
    "solar_return": "astronomical",
    "progressions": "astronomical",
    "fixed_stars": "astronomical",

    # === Birth time (requires profile.birth_time_local) ===
    "bazi_hour": "birth_time",
    "meihua": "birth_time",
    "planetary_hour": "birth_time",
    "planetary_hours": "birth_time",

    # === Approximate astronomical ===
    "vedic_tithi": "approx",
    "vedic_yoga": "approx",
    "vimshottari": "approx",

    # === Derived/composite (multiple inputs or other modules) ===
    "bazi_growth": "derived",
    "gd_correspondences": "derived",
    "notarikon": "derived",          # Uses both Arabic + Latin names
    "planetary_kameas": "derived",   # Uses DOB weekday + Latin name
    "steiner_cycles": "derived",     # Uses DOB + today (age-dependent)
    "tarot_year": "derived",         # Uses DOB month/day + current year
    "temperament": "derived",
    "tree_of_life": "derived",
    "wafq": "derived",

    # === Independent frameworks ===
    "ifa": "african_binary",
    "akan_kra_din": "african_calendar",    # DOB weekday only
    "planetary_joy": "astronomical",     # Natal planet-house joy positions
    "weton": "indo_javanese_calendar",           # Javanese 210-day calendar cycle

    # === Persian script extension ===
    "persian_abjad": "arabic_name",      # Arabic script → extended abjad values

    # === Astronomical (ephemeris-dependent) ===
    "antiscia": "astronomical",          # Natal planet longitudes → shadow degrees
    "yogini_dasha": "astronomical",      # Sidereal Moon nakshatra → 36-year cycle
    "ashtottari_dasha": "astronomical",  # Sidereal Moon + Rahu house → 108-year cycle

    # ── Modules 117-118: Birth-time-gated ──
    "zi_wei_dou_shu": "birth_time",          # Lunar calendar + birth hour → palace placement
    "shadbala": "astronomical",               # Sidereal planetary positions → strength scores

    # ── Modules 119-130: Ephemeris Phase 3 ──
    "almuten": "astronomical",               # Dignity accumulation across natal chart
    "reception": "astronomical",             # Mutual reception from natal planet signs
    "declinations": "astronomical",          # Equatorial declinations from natal positions
    "midpoints": "astronomical",             # Midpoint structures from natal positions
    "harmonic_charts": "astronomical",       # Harmonic multiples of natal positions
    "zodiacal_releasing": "astronomical",    # Timing from Lot of Fortune/Spirit
    "solar_arc": "astronomical",             # Solar arc from progressed Sun
    "dorothean_chronocrators": "astronomical",  # Triplicity rulers from sect light sign
    "ashtakavarga": "astronomical",          # Vedic benefic points from sidereal positions
    "shodashavarga": "astronomical",         # Vedic divisional charts from sidereal positions
    "tasyir": "astronomical",               # Islamic primary directions
    "kalachakra_dasha": "astronomical",      # Vedic nakshatra-pada timing system

    # ── Batch 18a: 4 new modules, added Feb 28, 2026 ──
    "bonification": "astronomical",           # Hellenistic planetary conditions from natal chart
    "zairja": "derived",                      # Composite: Arabic name abjad + natal ASC degree
    "qimen": "birth_time",                    # Qi Men Dun Jia: Sun longitude + hour branch
    "liu_ren": "birth_time",                  # Da Liu Ren: Sun longitude + day/hour pillars

    # ── Batch 18b: 5 new modules, added Feb 28, 2026 ──
    "primary_directions": "astronomical",     # Spherical trig from natal positions + latitude
    "chara_dasha": "astronomical",            # Sidereal Lagna + planet signs → sign-based timing
    "sarvatobhadra": "astronomical",          # Sidereal nakshatras from natal positions
    "tajika": "astronomical",                 # Solar return chart from natal Sun longitude
    "kp_system": "astronomical",              # Sidereal sub-lords from natal positions

    # ── Batch 19: 3 new modules, added Feb 28, 2026 ──
    "taiyi": "chinese_calendar",                 # Year-based 72-year cycle (no ephemeris)
    "onmyodo": "chinese_calendar",               # Year/month/day stem-branch cycle (no ephemeris)
    "uranian": "astronomical",                 # TNP longitudes + natal planet midpoints

    # ── Batch 20: 2 new modules, added Feb 28, 2026 ──
    "nadi_amsa": "astronomical",                 # Sidereal planet longitudes → D-150 micro-divisions
    "maramataka": "oceanic_lunar_calendar",              # DOB → synodic lunar day (no ephemeris)

    # ── Batch 21a: Babylonian sidereal, added Feb 28, 2026 ──
    "babylonian_horoscope": "astronomical",      # Natal longitudes → Babylonian sidereal conversion

    # ── Batch 21b: Vedic triple-wheel timing, added Mar 1, 2026 ──
    "sudarshana": "astronomical",                # Sidereal Lagna/Sun/Moon + age → triple-wheel progression

    # ── Round 2: 3 new modules, added Mar 4, 2026 ──
    "mahabote": "hellenistic_day",                # Pure arithmetic from DOB year/weekday
    "human_design": "astronomical",              # Rave Mandala from ephemeris positions
    "gene_keys": "derived",                      # 100% derived from human_design gate assignments

    # ── Round 2b: Mandaean baptismal oracle, added Mar 5, 2026 ──
    "malwasha": "mandaean_name",                    # Mother's name + DOB → Mandaean transliteration axis
    "prashna_natal": "astronomical",                # Today's sky → ephemeris group (APPROX)

    # ── Round 4: Cross-tradition expansion, added Apr 2026 ──
    # Vedic (5)
    "kala_sarpa_check": "astronomical",              # Natal planet longitudes → boolean check
    "panchamahabhuta": "astronomical",               # Natal planet positions → Vedic elements
    "ayurvedic_constitution": "astronomical",        # Natal planet positions → dosha mapping
    "mantra_seed_syllable": "astronomical",          # Sidereal Moon → nakshatra → bija syllable
    "vedic_gem_prescription": "astronomical",        # Ascendant/Moon lords → gem recommendation

    # Chinese (3)
    "bazi_10_year_forecast": "chinese_calendar",       # BaZi pillar sequence → 10-year periods
    "zi_wei_deeper": "chinese_calendar",               # Year stem → Four Transformations
    "four_pillars_balance": "chinese_calendar",        # BaZi stems/branches → element count

    # Hebrew (3)
    "gematria_word_matches": "arabic_name",          # Arabic → Hebrew transliteration → gematria
    "sephirotic_path_analysis": "derived",           # META: derives from LP/expression/abjad
    "solomonic_correspondences": "derived",          # META: derives from natal chart + weekday

    # African (1)
    "african_day_name_extended": "african_calendar",   # DOB weekday + JDN → day names

    # Western (2)
    "enneagram_deeper": "derived",                   # META: derives from enneagram_dob + core numbers
    "hermetic_element_balance": "derived",           # Aggregates natal + temperament + decan elements

    # Scientific (2)
    "circadian_medicine": "birth_time",              # Birth hour → organ clock
    "seasonal_psychology": "hellenistic_day",         # Birth month → season → correlates

    # Bridge (4)
    "element_consensus": "derived",                  # Bridge: aggregates element modules
    "timing_consensus": "derived",                   # Bridge: aggregates timing modules
    "planetary_ruler_consensus": "derived",           # Bridge: aggregates ruler modules
    "archetype_consensus": "derived",                # META bridge: aggregates archetype modules

    # ── Round 5 Wave 1: Decoz layer, added Apr 2026 ──
    "balance_number": "latin_name",                   # First initials of Latin name components
    "rational_thought": "latin_name",                 # First name Pythagorean + birthday number (mixed, but primarily name)
    "inclusion_table": "latin_name",                  # Full Latin name letter frequency
    "special_letters": "latin_name",                  # First vowel/consonant of first name
    "period_cycles": "birth_digits",                  # Month/day/year digit reduction
    "transit_letters": "derived",                     # Name letters + age (name × time composite)
    "yearly_essence_cycle": "derived",                # Sum of transit letters (name × time composite)
    "minor_numbers": "latin_name",                    # Current/short name Pythagorean (NEEDS_INPUT if absent)

    # ── Round 5 Wave 2: Tarot + Esoteric + Hellenistic, added Apr 2026 ──
    "tarot_greer_birth_cards": "birth_digits",        # DOB digit sum → constellation (same input as tarot_birth)
    "greer_zodiac_card": "astronomical",              # Sun sign → card (ephemeris when available, DOB fallback)
    "prenatal_syzygy": "astronomical",                # Swiss Ephemeris Sun/Moon positions
    "cheiro_extensions": "chaldean_name",             # Chaldean letter values (same group as chaldean module)
    "roman_chronogram": "latin_name",                 # Latin name letter selection
    "hebrew_aiq_beker": "arabic_name",                # Arabic→Hebrew transliteration → chamber reduction

    # ── Round 5 Wave 3: Cross-tradition, added Apr 2026 ──
    "tibetan_parkha": "tibetan_calendar",               # Birth year + gender → parkha trigram
    "tibetan_elements": "tibetan_calendar",             # Birth year digits → element cycle
    "tamil_panchapakshi": "astronomical",             # Sidereal Moon → nakshatra → bird
    "chinese_jian_chu": "chinese_calendar",             # Solar month/day branch → officer
    "igbo_market_day": "african_calendar",              # DOB mod 4 → market day
    "zoroastrian_day_yazata": "zoroastrian_calendar",       # Fasli calendar day → yazata
    "vedic_arudha_pada": "astronomical",              # Natal chart: ascendant lord position
    "vedic_upapada_lagna": "astronomical",            # Natal chart: 12th lord position
    "vedic_pushkara_navamsha": "astronomical",        # Natal chart: Moon/Asc degree ranges
    "bazi_san_he_san_hui": "chinese_calendar",          # BaZi pillar branches → combo detection
    "zwds_si_hua_palace": "chinese_calendar",           # Year stem → star transformations
    "hebrew_mispar_variants": "arabic_name",          # Arabic→Hebrew → 4 gematria methods

    # ── Round 5 Wave 4: Planes of Expression, added Apr 2026 ──
    "planes_of_expression": "latin_name",             # Latin name letter-to-plane assignment

    # ── Sacred-mode upgrade #5 (Apr 17, 2026): fill unmapped timing modules ──
    "hijri_calendar_encoding": "hijri_calendar",      # Hijri year/month/day digit encoding
    "electional_windows":      "astronomical",        # Ephemeris-based elective timing windows
    "muhurta":                 "astronomical",        # Vedic auspicious timing from ephemeris
    "prayer_times_as_timing":  "astronomical",        # Islamic prayer times from sun position
    "solar_return_deep":       "astronomical",        # Annual return chart deep-read

    # Arabic-linguistic modules surfacing in number_convergences as 'unknown'
    "arabic_roots":             "arabic_name",        # Arabic triliteral root extraction
    "letter_position_encoding": "arabic_name",        # Arabic letter position weights
    "digit_patterns":           "birth_digits",       # DOB digit sum/reverse roots
}


def _extract_numbers(result: SystemResult) -> List[int]:
    """Extract significant numbers from a result for convergence checking.
    Uses CONVERGENCE_FIELDS whitelist to prevent inflation from magic squares,
    frequency tables, and grid dumps."""
    numbers = []
    d = result.data
    allowed = CONVERGENCE_FIELDS.get(result.id)  # None = all fields, set() = skip

    if allowed is not None and len(allowed) == 0:
        return []  # Module explicitly excluded from number extraction

    for key, val in d.items():
        if allowed is not None and key not in allowed:
            continue
        if isinstance(val, int) and 1 <= val <= 33:
            numbers.append(val)
        if isinstance(val, dict):
            for k2, v2 in val.items():
                if allowed is not None and key not in allowed:
                    continue
                if isinstance(v2, int) and 1 <= v2 <= 33:
                    numbers.append(v2)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, int) and 1 <= item <= 33:
                    numbers.append(item)
    return numbers


# Per-module whitelist of fields containing genuine element values.
# Mirrors ELEMENT_FIELD_WHITELIST in axis_reducer.py.
_ELEMENT_FIELDS: dict[str, set[str]] = {
    # ── Chinese sexagenary family ──
    "bazi_daymaster":      {"day_master_element"},
    "bazi_ten_gods":       {"day_master_element"},
    "chinese_zodiac":      {"stem_element"},
    "nayin":               {"element"},
    "bazhai":              {"gua_element"},
    "taiyi":               {"taiyi_palace_element"},
    "onmyodo":             {"birth_element"},
    "nine_star_ki":        {"year_element", "month_element"},
    # ── Added 2026-04-17 (sacred-mode upgrade #2): coverage expansion ──
    "four_pillars_balance":     {"dominant_element", "weakest_element"},

    # ── Tibetan ──
    "tibetan_mewa":        {"mewa_element", "parkha_element"},
    "tibetan_elements":    {"lo_element", "srog_element"},    # NEW — distinct system
    "tibetan_parkha":      {"parkha_element"},                # NEW — gender-dependent trigram

    # ── Vedic ──
    "nakshatra":           {"element"},
    "panchamahabhuta":     {"dominant_english", "weakest_english"},  # NEW — Vedic 5 elements

    # ── Arabic / Islamic ──
    "elemental_letters":   {"dominant_element", "secondary_element"},
    "arabic_letter_nature": {"dominant_element"},              # NEW — al-Buni letter natures
    "manazil":             {"element"},                         # NEW — lunar mansion element

    # ── Hellenistic / Western classical ──
    "temperament":         {"primary_element", "secondary_element"},
    "egyptian_decan":      {"element"},                         # NEW — decan elemental quality
    "dorothean_chronocrators": {"element"},                     # NEW — triplicity ruler element
    "day_ruler":           {"element"},                         # NEW — planetary day ruler element

    # ── African / Afro-Arabian ──
    "akan_kra_din":        {"element"},                         # NEW — West African soul-name
    "igbo_market_day":     {"igbo_element"},                    # NEW — Igbo 4-day cycle
    "zoroastrian_day_yazata": {"yazata_element"},               # NEW — Persian yazata element

    # ── Derived / synthesis-level ──
    "hermetic_element_balance": {"dominant_element", "weakest_element"},  # NEW — aggregator
    "circadian_medicine":  {"birth_organ_element", "season_element"},     # NEW — TCM organ clock

    # ── Sacred-mode upgrade #4 (Apr 17, 2026): flat additions ──
    "zairja":              {"dominant_element"},                # Ibn Khaldun combinatorial oracle
    "liu_ren":             {"dominant_element"},                # Da Liu Ren 12-branch plate
}

_ELEMENT_NAMES = {"water", "fire", "earth", "air", "wood", "metal"}


# ── Sacred-mode upgrade #4 (Apr 17, 2026): nested element field walker ──
# For modules where element data lives one or two levels deep inside dicts.
# Paths are dotted: "day_pillar.stem_element" resolves to data["day_pillar"]["stem_element"].
# High-derivedness modules (gd_correspondences, bazi_hidden_stems) are intentionally
# excluded — they would double-count against their upstream signals.
_NESTED_ELEMENT_FIELDS: dict[str, list[str]] = {
    "bazi_pillars":   ["day_pillar.stem_element"],              # Day Master — Chinese identity element
    "ifa":            ["left_leg.element", "right_leg.element"],  # Ifá odu elemental sides
    "istikhara_adad": ["mod_4.element"],                         # The mod-4 element attribution
}


def _resolve_dotted(data, path: str):
    """Walk a dotted path through nested dicts; return None if any segment missing."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _extract_elements(result: SystemResult) -> List[str]:
    """Extract element references from whitelisted fields (flat + nested)."""
    allowed_flat   = _ELEMENT_FIELDS.get(result.id)
    allowed_nested = _NESTED_ELEMENT_FIELDS.get(result.id, [])

    if allowed_flat is None and not allowed_nested:
        return []

    elements = []

    # Flat fields (depth 0)
    if allowed_flat is not None:
        for key, val in result.data.items():
            if key not in allowed_flat:
                continue
            if isinstance(val, str):
                val_lower = val.lower()
                for elem in _ELEMENT_NAMES:
                    if elem in val_lower:
                        elements.append(elem.capitalize())

    # Nested fields (dotted paths, depth ≥ 1)
    for path in allowed_nested:
        val = _resolve_dotted(result.data, path)
        if isinstance(val, str):
            val_lower = val.lower()
            for elem in _ELEMENT_NAMES:
                if elem in val_lower:
                    elements.append(elem.capitalize())

    return list(set(elements))


def synthesize(
    results: List[SystemResult],
    constants: dict,
    core25_mode: bool = False,
    profile=None,
) -> Dict[str, Any]:
    """
    Run cross-system convergence analysis.
    Returns synthesis report with confidence-tagged claims.

    Parameters
    ----------
    results : List[SystemResult]
        Per-module compute results.
    constants : dict
        Loaded constants.json (for synthesis thresholds).
    core25_mode : bool, default False
        When True, restrict convergence detection to the 25 high-signal
        modules defined in CORE_25_MODULES (mirrors sirr_core_25.py).
        The returned dict gains explicit `cluster_primary_convergence`
        and `cluster_secondary_convergence` keys surfacing the calibration
        panels. When False, behavior is unchanged.
    profile : InputProfile or None, default None
        The profile being synthesized. Used to select a name-length-matched
        baseline (full-nasab profiles get compared against long-name baselines
        rather than the 3-word default). If None, default baseline is used.
    """
    # ── Select baseline by profile name length (NEW 2026-04-17) ──
    _active_baseline, _baseline_stratum, _baseline_source = _select_baseline(profile)
    synth_cfg = constants.get("synthesis", {})
    min_systems = synth_cfg.get("min_systems_for_convergence", 3)
    min_groups = synth_cfg.get("min_traditions_for_convergence", 2)

    # Only use lockable results
    lockable = [r for r in results if r.certainty in LOCKABLE]

    # ── Core 25 filter ──
    # In core25_mode, keep only the 25 modules in the Core 25 panel.
    # Independence-group and min-systems/min-groups thresholds are unchanged
    # so convergence tiers remain directly comparable to the full-engine run.
    if core25_mode:
        lockable = [r for r in lockable if r.id in CORE_25_MODULES]

    # === NUMBER CONVERGENCE ===
    number_votes = {}  # number -> list of (system_id, group)
    for r in lockable:
        # Skip highly-derived modules (derivedness > 0.7) to prevent
        # inflated convergence from correlated upstream outputs
        if r.id in _HIGH_DERIVEDNESS:
            continue
        nums = _extract_numbers(r)
        group = SYSTEM_TO_GROUP.get(r.id, "unknown")
        for n in nums:
            if n not in number_votes:
                number_votes[n] = []
            number_votes[n].append({"system": r.id, "group": group})

    number_convergences = []
    # Baseline distribution for max system_count (from Monte Carlo, name-length-matched)
    baseline_max_dist = {}
    baseline_n = 10000
    if _active_baseline:
        baseline_max_dist = _active_baseline.get("distributions", {}).get("max_system_count", {})
        baseline_n = _active_baseline.get("n", 10000)

    for num, votes in sorted(number_votes.items()):
        # ── ONE VOTE PER MODULE PER NUMBER ──
        # A module may emit multiple whitelisted fields that all equal the same
        # number (e.g. avgad's original_root + avgad_root, bridges' multiple
        # tension values). Cap at 1 vote per module_id to prevent inflation.
        seen_modules = set()
        deduped_votes = []
        for v in votes:
            if v["system"] not in seen_modules:
                deduped_votes.append(v)
                seen_modules.add(v["system"])
        votes = deduped_votes

        groups = set(v["group"] for v in votes)
        systems = [v["system"] for v in votes]
        if len(systems) >= min_systems and len(groups) >= min_groups:
            # Calculate baseline percentile
            sys_count = len(systems)
            percentile = None
            if baseline_max_dist and baseline_n:
                # What % of random profiles have their max convergence < this count?
                below = sum(v for k, v in baseline_max_dist.items() if int(k) < sys_count)
                percentile = round(below / baseline_n * 100, 1)

            # Tier assignment: baseline-calibrated
            # SIGNIFICANT = top 10th percentile OR 6+ independent groups at top 15th percentile
            # (6 groups from independent civilizations is a stronger signal than raw system count)
            is_top_10 = percentile is not None and percentile >= 90
            is_multi_tradition = len(groups) >= 5 and percentile is not None and percentile >= 85
            if len(groups) >= 3 and (is_top_10 or is_multi_tradition):
                tier = "TIER_1_SIGNIFICANT"
            elif len(groups) >= 3:
                tier = "TIER_1_RESONANCE"
            else:
                tier = "TIER_2_CONVERGENCE"

            # Build per-system group mapping (system_id -> group)
            system_groups = {v["system"]: v["group"] for v in votes}

            entry = {
                "number": num,
                "system_count": len(systems),
                "group_count": len(groups),
                "groups": list(groups),
                "systems": systems,
                "system_groups": system_groups,
                "tier": tier,
            }
            if percentile is not None:
                entry["baseline_percentile"] = percentile
            number_convergences.append(entry)

    # === ELEMENT CONVERGENCE ===
    element_votes = {}
    for r in lockable:
        # Skip highly-derived modules (same derivedness filter as numbers)
        if r.id in _HIGH_DERIVEDNESS:
            continue
        elems = _extract_elements(r)
        group = SYSTEM_TO_GROUP.get(r.id, "unknown")
        for e in elems:
            if e not in element_votes:
                element_votes[e] = []
            element_votes[e].append({"system": r.id, "group": group})

    element_convergences = []
    for elem, votes in sorted(element_votes.items()):
        groups = set(v["group"] for v in votes)
        systems = [v["system"] for v in votes]
        if len(systems) >= 2 and len(groups) >= 2:
            element_convergences.append({
                "element": elem,
                "system_count": len(systems),
                "group_count": len(groups),
                "groups": list(groups),
                "systems": systems,
                "tier": "TIER_1_RESONANCE" if len(groups) >= 3 else "TIER_2_CONVERGENCE"
            })

    # === TIMING CONVERGENCE ===
    # Sacred-mode upgrade #5 (2026-04-17): now matches integrity level of
    # number/element convergences — derivedness filter, per-module dedup,
    # group tracking, tiering. Previously a single module with multiple
    # whitelisted int-fields all equal to N would vote for N repeatedly
    # (e.g. hijri_calendar_encoding 3× on number 2).
    timing_results = [r for r in lockable if r.question == "Q4_TIMING"]
    timing_votes: Dict[int, List[Dict[str, str]]] = {}
    for r in timing_results:
        # Apply same derivedness filter as number + element convergences
        if r.id in _HIGH_DERIVEDNESS:
            continue
        group = SYSTEM_TO_GROUP.get(r.id, "unknown")
        # Per-module dedup: a module emits at most one vote per number
        voted_for: set = set()
        for key, val in r.data.items():
            if isinstance(val, int) and 1 <= val <= 12 and val not in voted_for:
                voted_for.add(val)
                timing_votes.setdefault(val, []).append({"system": r.id, "group": group})

    timing_convergences = []
    for num, votes in sorted(timing_votes.items()):
        groups = set(v["group"] for v in votes)
        systems = [v["system"] for v in votes]
        if len(systems) >= 2 and len(groups) >= 2:
            # Tier assignment (matches element convergence rules):
            # SIGNIFICANT = 4+ groups AND 6+ systems
            # RESONANCE   = 3+ groups
            # CONVERGENCE = 2+ groups
            if len(groups) >= 4 and len(systems) >= 6:
                tier = "TIER_1_SIGNIFICANT"
            elif len(groups) >= 3:
                tier = "TIER_1_RESONANCE"
            else:
                tier = "TIER_2_CONVERGENCE"
            timing_convergences.append({
                "number": num,
                "system_count": len(systems),
                "group_count": len(groups),
                "systems": systems,
                "groups": sorted(groups),
                "tier": tier,
                "meaning": f"Multiple timing systems point to {num}",
            })

    # === QUESTION COVERAGE ===
    questions_answered = {}
    for r in results:
        q = r.question or "unclassified"
        if q not in questions_answered:
            questions_answered[q] = []
        questions_answered[q].append({"id": r.id, "certainty": r.certainty})

    # === CONFIDENCE SUMMARY ===
    total_strict = sum(1 for r in results if r.certainty == "COMPUTED_STRICT")
    total_lookup = sum(1 for r in results if r.certainty == "LOOKUP_FIXED")
    total_approx = sum(1 for r in results if r.certainty in ("APPROX", "NEEDS_EPHEMERIS", "NEEDS_CORRELATION"))

    baseline_meta = None
    if _active_baseline:
        baseline_meta = {
            "n": _active_baseline.get("n"),
            "max_sys_mean": _active_baseline.get("baseline", {}).get("max_sys_mean"),
            "max_sys_median": _active_baseline.get("baseline", {}).get("max_sys_median"),
            "t1_mean": _active_baseline.get("baseline", {}).get("t1_mean"),
            "stratum": _baseline_stratum,
            "source": _baseline_source,
            "module_count": _active_baseline.get("mc_baseline_meta", {}).get("module_count"),
            "name_length_hint": _active_baseline.get("mc_baseline_meta", {}).get("name_length"),
        }

    output: Dict[str, Any] = {
        "number_convergences": number_convergences,
        "element_convergences": element_convergences,
        "timing_convergences": timing_convergences,
        "question_coverage": questions_answered,
        "confidence_summary": {
            "total_systems": len(results),
            "strict_locked": total_strict,
            "method_locked": total_lookup,
            "approximate": total_approx,
            "lockable_pct": round((total_strict + total_lookup) / max(len(results), 1) * 100, 1)
        },
        "baseline": baseline_meta,
        "resonance_count": sum(1 for nc in number_convergences if nc["tier"] in ("TIER_1_RESONANCE", "TIER_1_SIGNIFICANT")),
        "significant_count": sum(1 for nc in number_convergences if nc["tier"] == "TIER_1_SIGNIFICANT"),
        "convergence_count": len(number_convergences) + len(element_convergences)
    }

    # ── Core 25 mode: surface Root 8 (dominant) and Root 3 (LP) explicitly ──
    if core25_mode:
        def _cluster_for_root(root: int, pool: frozenset) -> Dict[str, Any]:
            """Build an explicit cluster dict for a target root (8 or 3),
            filtered to the dominant or structural Core-25 pool."""
            # Find the full number_convergence entry for this root, if any
            entry = next((nc for nc in number_convergences if nc["number"] == root), None)

            # Systems in `pool` that voted for `root` (even if below threshold)
            votes = number_votes.get(root, [])
            seen = set()
            pool_systems: List[str] = []
            pool_groups: set = set()
            for v in votes:
                if v["system"] in pool and v["system"] not in seen:
                    seen.add(v["system"])
                    pool_systems.append(v["system"])
                    pool_groups.add(v["group"])

            return {
                "root": root,
                "pool_size": len(pool),
                "system_count": len(pool_systems),
                "group_count": len(pool_groups),
                "systems": pool_systems,
                "groups": sorted(pool_groups),
                "reaches_threshold": (
                    entry is not None
                    and len(pool_systems) >= min_systems
                    and len(pool_groups) >= min_groups
                ),
                "convergence_entry": entry,  # Full number_convergence entry (global), or None
            }

        output["core25_mode"] = True
        output["core25_modules_run"] = len(lockable)
        output["cluster_primary_convergence"] = _cluster_for_root(8, CORE_25_CLUSTER_PRIMARY)
        output["cluster_secondary_convergence"] = _cluster_for_root(3, CORE_25_CLUSTER_SECONDARY)

    return output
