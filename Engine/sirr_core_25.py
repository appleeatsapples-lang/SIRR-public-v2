"""
SIRR Core 25 — Slim Runner

Executes ONLY the 25 high-signal modules selected via signal analysis
(SIGNAL_SCORE = primary_hit - baseline_dominance_rate, positive only,
capped at 2-3 per independence group).

Two clusters (calibration-panel):
  CLUSTER PRIMARY   — 14 modules — dominant-signal panel (calibration-run)
  CLUSTER SECONDARY — 11 modules — structural/life-path panel (calibration-run)

Dependency order:
  1. natal_chart  — infrastructure, feeds 6 astronomical modules
  2. 19 independent name / DOB / calendar modules
  3. 6 astronomical modules that consume natal_chart_data

Input : fixtures/synthetic_profile.json (default) or any profile fixture
Output: output_core25.json
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

from sirr_core.types import InputProfile, SystemResult
from sirr_core.utils import date_to_iso

# Infrastructure
from modules import natal_chart

# Cluster primary — 14 modules
from modules import (
    subconscious_self,
    solar_return,
    solar_lunar,
    zi_wei_dou_shu,
    luminous_dark,
    arabic_parts,
    ifa,
    personal_year,
    pinnacles,
    planes_of_expression,
    mandaean_gematria,
    lo_shu_grid,
    ethiopian_asmat,
    abjad_kabir,
)

# Cluster secondary — 11 modules
from modules import (
    zairja,
    buduh,
    atbash,
    agrippan,
    thelemic_gematria,
    armenian_gematria,
    tarot_greer_birth_cards,
    enneagram_dob,
    sarvatobhadra,
    sect,
    essential_dignities,
)


CORE_25_LAYERS = {
    "cluster_primary": [
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
    ],
    "cluster_secondary": [
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
    ],
}

INDEPENDENCE_GROUPS = {
    "subconscious_self": "latin_name",
    "solar_return": "astronomical",
    "solar_lunar": "arabic_name",
    "zi_wei_dou_shu": "birth_time",
    "luminous_dark": "arabic_name",
    "arabic_parts": "astronomical",
    "ifa": "african_binary",
    "personal_year": "birth_digits",
    "pinnacles": "birth_digits",
    "planes_of_expression": "latin_name",
    "mandaean_gematria": "mandaean_name",
    "lo_shu_grid": "birth_digits",
    "ethiopian_asmat": "birth_calendar",
    "abjad_kabir": "arabic_name",
    "zairja": "astronomical",
    "buduh": "arabic_name",
    "atbash": "arabic_name",
    "agrippan": "latin_name",
    "thelemic_gematria": "latin_name",
    "armenian_gematria": "latin_name",
    "tarot_greer_birth_cards": "birth_digits",
    "enneagram_dob": "birth_digits",
    "sarvatobhadra": "astronomical",
    "sect": "astronomical",
    "essential_dignities": "astronomical",
}


# ─────────────────────────────────────────────────────────────────────
# FRONTEND CONTRACT (sirr_v8.jsx)
# ─────────────────────────────────────────────────────────────────────
# The frontend at SIRR_CORE/03_EXPERIENCE/sirr_v8.jsx consumes
# output_core25.json against the scaffold at
# SIRR_CORE/02_ENGINE/output_core25.scaffold.json.
#
# Contract:
#   • `results` is an OBJECT keyed by canonical tradition id (not an array)
#   • Each result carries `root` (per-result) and `data`
#   • Inside `data`, the scaffold-mandated field names must be present
#   • Extra fields the engine already emits are preserved untouched
#     (the frontend ignores unknowns)
#
# `MODULE_ROOT` is the calibration-run expected root per module. These
# integers are fixed panel calibration values, not per-subject expectations.
# `_normalize_data_for_scaffold` adds scaffold-named fields alongside
# whatever the module already returned — it never deletes engine fields,
# so other downstream consumers (synthesis.py, reading_composer, etc.)
# keep working.
# ─────────────────────────────────────────────────────────────────────

MODULE_ROOT: dict[str, int] = {
    **{mid: 8 for mid in CORE_25_LAYERS["cluster_primary"]},
    **{mid: 3 for mid in CORE_25_LAYERS["cluster_secondary"]},
}


# Ba(2), Dal(4), Waw(6), Ha(8) — BDWH letters keyed by their abjad value.
# Used by abjad_kabir normalization to derive the scaffold `letter` field
# from the module's computed root.
_BDWH_BY_VALUE = {2: "ب", 3: "ج", 4: "د", 5: "ه", 6: "و", 7: "ز", 8: "ح", 9: "ط"}


def _normalize_data_for_scaffold(tradition_id: str, data: dict) -> dict:
    """Add scaffold-mandated field names to a module's data block.

    Returns a new dict containing every field the engine already produced
    PLUS any scaffold-required fields the module doesn't emit directly.
    Existing fields are never removed. Shape mismatches (e.g. pinnacle_1
    with key ``value``/``ages`` vs scaffold's ``p1`` with ``val``/``ages``)
    are reconciled by adding the scaffold key alongside the original.

    The per-id branches below are a contract between this orchestrator
    and 02_ENGINE/output_core25.scaffold.json — if the scaffold changes,
    update the corresponding branch here.
    """
    out = dict(data)  # shallow copy; never mutate module's return value

    if tradition_id == "abjad_kabir":
        # scaffold: total, words, letter
        if "words" not in out and "word_sums" in out:
            out["words"] = out["word_sums"]
        if "letter" not in out:
            root = out.get("root")
            out["letter"] = _BDWH_BY_VALUE.get(root, "")

    elif tradition_id == "solar_return":
        # scaffold: sun_house, rising, moon, year
        if "rising" not in out and "return_rising" in out:
            out["rising"] = out["return_rising"]
        if "moon" not in out and "return_moon_sign" in out:
            out["moon"] = out["return_moon_sign"]
        if "year" not in out and "return_year" in out:
            out["year"] = out["return_year"]

    elif tradition_id == "ifa":
        # scaffold: odu, right, left, open, closed
        if "odu" not in out and "combined_odu" in out:
            out["odu"] = out["combined_odu"]
        if "right" not in out:
            right_leg = out.get("right_leg") or {}
            out["right"] = right_leg.get("binary", "")
        if "left" not in out:
            left_leg = out.get("left_leg") or {}
            out["left"] = left_leg.get("binary", "")
        if "open" not in out and "open_marks" in out:
            out["open"] = out["open_marks"]
        if "closed" not in out and "closed_marks" in out:
            out["closed"] = out["closed_marks"]

    elif tradition_id == "buduh":
        # scaffold: square, constant
        if "square" not in out and "personal_square" in out:
            out["square"] = out["personal_square"]
        if "constant" not in out and "magic_constant" in out:
            out["constant"] = out["magic_constant"]

    elif tradition_id == "subconscious_self":
        # scaffold: present, missing
        if "present" not in out and "digits_present" in out:
            out["present"] = out["digits_present"]
        if "missing" not in out and "digits_missing" in out:
            out["missing"] = out["digits_missing"]

    elif tradition_id == "arabic_parts":
        # scaffold: fortune (formatted), spirit (formatted), fortune_house, spirit_house
        lots = out.get("lots") or {}
        if "fortune" not in out:
            fortune_lot = lots.get("Fortune") or {}
            out["fortune"] = fortune_lot.get("formatted", "")
        if "spirit" not in out:
            spirit_lot = lots.get("Spirit") or {}
            out["spirit"] = spirit_lot.get("formatted", "")

    elif tradition_id == "solar_lunar":
        # scaffold: solar, lunar, type
        if "solar" not in out and "solar_count" in out:
            out["solar"] = out["solar_count"]
        if "lunar" not in out and "lunar_count" in out:
            out["lunar"] = out["lunar_count"]
        out.setdefault("type", "solar_lunar")

    elif tradition_id == "personal_year":
        # scaffold: year, month, day
        # NB: engine already has a `personal_year` key; we override with
        # the scaffold's short-form `year` for frontend consumption.
        if "year" not in out and "personal_year" in out:
            out["year"] = out["personal_year"]
        if "month" not in out and "personal_month" in out:
            out["month"] = out["personal_month"]
        if "day" not in out and "personal_day" in out:
            out["day"] = out["personal_day"]

    elif tradition_id == "mandaean_gematria":
        # scaffold: total
        if "total" not in out and "total_gematria" in out:
            out["total"] = out["total_gematria"]

    elif tradition_id == "pinnacles":
        # scaffold: p1..p4 each {val, ages}, current
        for idx in (1, 2, 3, 4):
            src = out.get(f"pinnacle_{idx}")
            if src and f"p{idx}" not in out:
                out[f"p{idx}"] = {
                    "val": src.get("value"),
                    "ages": src.get("ages"),
                }
        if "current" not in out and "current_pinnacle" in out:
            out["current"] = out["current_pinnacle"]

    elif tradition_id == "atbash":
        # scaffold: original, transformed, root
        if "original" not in out and "original_sum" in out:
            out["original"] = out["original_sum"]
        if "transformed" not in out and "atbash_sum" in out:
            out["transformed"] = out["atbash_sum"]
        if "root" not in out and "atbash_root" in out:
            out["root"] = out["atbash_root"]

    elif tradition_id == "agrippan":
        # scaffold: total, root, letters
        if "letters" not in out and "letter_count" in out:
            out["letters"] = out["letter_count"]

    elif tradition_id == "luminous_dark":
        # scaffold: luminous, dark, type
        if "luminous" not in out and "luminous_count" in out:
            out["luminous"] = out["luminous_count"]
        if "dark" not in out and "dark_count" in out:
            out["dark"] = out["dark_count"]
        out.setdefault("type", "luminous_dark")

    elif tradition_id == "sect":
        # scaffold: sect, benefic, malefic_contrary, in_sect, out_sect
        if "sect" not in out and "chart_sect" in out:
            out["sect"] = out["chart_sect"]
        if "benefic" not in out and "benefic_of_sect" in out:
            out["benefic"] = out["benefic_of_sect"]
        if "in_sect" not in out and "in_sect_count" in out:
            out["in_sect"] = out["in_sect_count"]
        if "out_sect" not in out and "out_sect_count" in out:
            out["out_sect"] = out["out_sect_count"]

    elif tradition_id == "ethiopian_asmat":
        # scaffold: angel, angel_idx (total already matches)
        if "angel" not in out and "guardian_angel" in out:
            out["angel"] = out["guardian_angel"]
        if "angel_idx" not in out and "angel_mod7" in out:
            out["angel_idx"] = out["angel_mod7"]

    elif tradition_id == "enneagram_dob":
        # scaffold: type
        if "type" not in out and "enneagram_type" in out:
            out["type"] = out["enneagram_type"]

    elif tradition_id == "planes_of_expression":
        # scaffold: physical/mental/emotional/intuitive as {count, root},
        # plus dominant
        for plane in ("physical", "mental", "emotional", "intuitive"):
            if plane not in out:
                count_key = f"{plane}_count"
                root_key = f"{plane}_root"
                if count_key in out and root_key in out:
                    out[plane] = {
                        "count": out[count_key],
                        "root": out[root_key],
                    }
        if "dominant" not in out and "dominant_plane" in out:
            out["dominant"] = out["dominant_plane"]

    elif tradition_id == "zairja":
        # scaffold: manzil, letter, chord, elements
        if "manzil" not in out and "starting_manzil" in out:
            out["manzil"] = out["starting_manzil"]
        if "letter" not in out and "starting_letter" in out:
            out["letter"] = out["starting_letter"]
        if "chord" not in out and "chord_sequence" in out:
            out["chord"] = out["chord_sequence"]
        if "elements" not in out and "elemental_sequence" in out:
            out["elements"] = out["elemental_sequence"]

    elif tradition_id == "tarot_greer_birth_cards":
        # scaffold: personality_num, soul_num, hidden_num
        if "personality_num" not in out and "personality_card" in out:
            out["personality_num"] = out["personality_card"]
        if "soul_num" not in out and "soul_card" in out:
            out["soul_num"] = out["soul_card"]
        if "hidden_num" not in out:
            hidden_nums = out.get("hidden_factor_numbers") or []
            out["hidden_num"] = hidden_nums[0] if hidden_nums else None

    elif tradition_id == "sarvatobhadra":
        # scaffold: vedhas, positive, negative, moon_rashi, tithi
        if "vedhas" not in out and "vedha_count" in out:
            out["vedhas"] = out["vedha_count"]
        if "positive" not in out and "positive_vedhas" in out:
            out["positive"] = out["positive_vedhas"]
        if "negative" not in out and "negative_vedhas" in out:
            out["negative"] = out["negative_vedhas"]
        if "tithi" not in out and "natal_tithi_name" in out:
            out["tithi"] = out["natal_tithi_name"]

    elif tradition_id == "essential_dignities":
        # scaffold: mercury {sign, score}, sun {sign, score}, dignified, debilitated
        dignities = out.get("dignities") or {}
        if "mercury" not in out:
            merc = dignities.get("Mercury") or {}
            out["mercury"] = {"sign": merc.get("sign"), "score": merc.get("score")}
        if "sun" not in out:
            sun = dignities.get("Sun") or {}
            out["sun"] = {"sign": sun.get("sign"), "score": sun.get("score")}
        if "dignified" not in out and "dignified_count" in out:
            out["dignified"] = out["dignified_count"]
        if "debilitated" not in out and "debilitated_count" in out:
            out["debilitated"] = out["debilitated_count"]

    return out


def _build_result_entry(r: SystemResult) -> dict:
    """Shape a SystemResult into the frontend contract entry.

    Adds per-result `root` and normalizes `data` against the scaffold.
    Preserves every envelope field the module emits (certainty, name,
    interpretation, references, question, constants_version, ar_interpretation).
    """
    envelope = dict(r.__dict__)
    envelope["data"] = _normalize_data_for_scaffold(r.id, envelope.get("data") or {})
    envelope["root"] = MODULE_ROOT.get(r.id)
    return envelope


def load_constants(path: str | None = None) -> dict:
    if path is None:
        path = str(Path(__file__).parent / "constants.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reduce_core(n: int) -> int:
    """Reduce to single digit or master number (11, 22, 33)."""
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


def _compute_name_length_tier(subject: str, arabic: str) -> str:
    """Determine SHORT / MEDIUM / LONG tier from whitespace word count.

    Uses the longer of (Latin subject, Arabic name) word counts:
      2-3 words  → short
      4-6 words  → medium
      7+ words   → long

    Matches the tier boundaries used by web_backend.server.compute_name_length_tier
    and the onboarding flow in web/index.html.
    """
    def _wc(s: str) -> int:
        return len([w for w in (s or "").strip().split() if w])

    word_count = max(_wc(subject), _wc(arabic))
    if word_count >= 7:
        return "long"
    if word_count >= 4:
        return "medium"
    return "short"


def _compute_core_numbers(subject: str, dob: date) -> dict:
    """Auto-compute Pythagorean core numbers from name + DOB."""
    PYT = {'A':1,'B':2,'C':3,'D':4,'E':5,'F':6,'G':7,'H':8,'I':9,
           'J':1,'K':2,'L':3,'M':4,'N':5,'O':6,'P':7,'Q':8,'R':9,
           'S':1,'T':2,'U':3,'V':4,'W':5,'X':6,'Y':7,'Z':8}
    VOWELS = set('AEIOU')
    name = subject.upper()
    expression = _reduce_core(sum(PYT.get(c, 0) for c in name))
    soul_urge = _reduce_core(sum(PYT.get(c, 0) for c in name if c in VOWELS))
    personality = _reduce_core(sum(PYT.get(c, 0) for c in name if c not in VOWELS and c != ' '))
    m = _reduce_core(dob.month)
    d = _reduce_core(dob.day)
    y = _reduce_core(sum(int(c) for c in str(dob.year)))
    life_path = _reduce_core(m + d + y)
    birthday_number = _reduce_core(dob.day)
    return {
        "life_path": life_path,
        "expression": expression,
        "soul_urge": soul_urge,
        "personality": personality,
        "birthday_number": birthday_number,
    }


def load_profile(path: str) -> InputProfile:
    """Load profile fixture; mirror runner.py behavior for auto-compute fields."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dob = date.fromisoformat(data["dob"])
    core = _compute_core_numbers(data["subject"], dob)

    arabic_name = data.get("arabic", "").strip()
    if not arabic_name:
        from modules.transliterate import transliterate_to_arabic
        arabic_name = transliterate_to_arabic(data["subject"])

    abjad_first = data.get("abjad_first")
    if abjad_first is None:
        constants = load_constants()
        abjad_table = constants["arabic_letters"]["abjad_kabir"]
        first_word = arabic_name.split()[0] if arabic_name.strip() else ""
        abjad_first = sum(abjad_table.get(ch, 0) for ch in first_word)

    return InputProfile(
        subject=data["subject"],
        arabic=arabic_name,
        dob=dob,
        today=date.fromisoformat(data.get("today", date.today().isoformat())),
        birth_time_local=data.get("birth_time_local"),
        timezone=data.get("timezone"),
        location=data.get("location"),
        life_path=data.get("life_path") or core["life_path"],
        expression=data.get("expression") or core["expression"],
        soul_urge=data.get("soul_urge") or core["soul_urge"],
        personality=data.get("personality") or core["personality"],
        birthday_number=data.get("birthday_number") or core["birthday_number"],
        abjad_first=abjad_first,
        gender=data.get("gender"),
        variant=data.get("variant"),
        mother_name=data.get("mother_name"),
        mother_name_ar=data.get("mother_name_ar"),
        mother_dob=data.get("mother_dob"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        utc_offset=data.get("utc_offset"),
    )


def compute_core_25(profile: InputProfile, constants: dict) -> tuple[list[SystemResult], SystemResult]:
    """Run the 25 Core modules for a single profile.

    Returns (results, r_natal) where results is the 25 SystemResults and
    r_natal is the natal_chart infrastructure result (used for anchor metadata).
    Natal-chart failures degrade the 6 astronomical modules to NEEDS_EPHEMERIS
    but never raise — the run always yields 25 results.
    """
    results: list[SystemResult] = []

    # ── Infrastructure: Natal Chart (feeds 6 astronomical modules) ──
    r_natal = natal_chart.compute(profile, constants)
    ncd = r_natal.data if r_natal.certainty == "COMPUTED_STRICT" else None

    # ═════════════════════════════════════════════════════════════════
    # DOMINANT LAYER (Root 8) — 14 modules
    # ═════════════════════════════════════════════════════════════════

    # Latin-name axis
    results.append(subconscious_self.compute(profile, constants))
    results.append(planes_of_expression.compute(profile, constants))

    # Arabic-name axis
    results.append(solar_lunar.compute(profile, constants))
    results.append(luminous_dark.compute(profile, constants))
    results.append(abjad_kabir.compute(profile, constants))

    # Mandaean gnostic (fully independent from Islamic letter systems)
    results.append(mandaean_gematria.compute(profile, constants))

    # Birth-digit axis (correlated cluster — treat as one signal)
    results.append(personal_year.compute(profile, constants))
    results.append(pinnacles.compute(profile, constants))
    results.append(lo_shu_grid.compute(profile, constants))

    # Birth-calendar axis
    results.append(ethiopian_asmat.compute(profile, constants))

    # African binary oracle
    results.append(ifa.compute(profile, constants))

    # Birth-time axis
    results.append(zi_wei_dou_shu.compute(profile, constants))

    # Astronomical axis — consume natal_chart_data
    results.append(solar_return.compute(profile, constants, natal_chart_data=ncd))
    results.append(arabic_parts.compute(profile, constants, natal_chart_data=ncd))

    # ═════════════════════════════════════════════════════════════════
    # STRUCTURAL LAYER (Root 3) — 11 modules
    # ═════════════════════════════════════════════════════════════════

    # Arabic-name axis
    results.append(buduh.compute(profile, constants))
    results.append(atbash.compute(profile, constants))

    # Latin-name axis
    results.append(agrippan.compute(profile, constants))
    results.append(thelemic_gematria.compute(profile, constants))
    results.append(armenian_gematria.compute(profile, constants))

    # Birth-digit axis
    results.append(tarot_greer_birth_cards.compute(profile, constants))
    results.append(enneagram_dob.compute(profile, constants))

    # Astronomical axis — consume natal_chart_data
    results.append(zairja.compute(profile, constants, natal_chart_data=ncd))
    results.append(sarvatobhadra.compute(profile, constants, natal_chart_data=ncd))
    results.append(sect.compute(profile, constants, natal_chart_data=ncd))
    results.append(essential_dignities.compute(profile, constants, natal_chart_data=ncd))

    return results, r_natal


def run_core_25(profile_path: str, output_path: str = "output_core25.json") -> dict:
    constants = load_constants()
    profile = load_profile(profile_path)

    results, r_natal = compute_core_25(profile, constants)
    ncd = r_natal.data if r_natal.certainty == "COMPUTED_STRICT" else None

    # ── Summary tallies ──
    cert_counts: dict[str, int] = {}
    for r in results:
        cert_counts[r.certainty] = cert_counts.get(r.certainty, 0) + 1

    by_group: dict[str, list[str]] = {}
    for r in results:
        grp = INDEPENDENCE_GROUPS.get(r.id, "unknown")
        by_group.setdefault(grp, []).append(r.id)

    # ── Build output ──
    name_length_tier = _compute_name_length_tier(profile.subject, profile.arabic)

    out = {
        "engine": "sirr_core_25",
        "version": "1.0.0",
        "profile": {
            "subject": profile.subject,
            "arabic": profile.arabic,
            "dob": date_to_iso(profile.dob),
            "today": date_to_iso(profile.today),
            "birth_time_local": profile.birth_time_local,
            "timezone": profile.timezone,
            "location": profile.location,
            "variant": profile.variant,
            "name_length_tier": name_length_tier,
            "core_numbers": {
                "life_path": profile.life_path,
                "expression": profile.expression,
                "soul_urge": profile.soul_urge,
                "personality": profile.personality,
                "birthday": profile.birthday_number,
                "abjad_first": profile.abjad_first,
            },
        },
        "constants_version": constants["version"],
        "module_count": len(results),
        "layers": CORE_25_LAYERS,
        "independence_groups": INDEPENDENCE_GROUPS,
        "modules_by_group": by_group,
        "certainty_distribution": cert_counts,
        "natal_chart_anchor": {
            "certainty": r_natal.certainty,
            "available": ncd is not None,
            "sun_sign": (ncd or {}).get("sun_sign"),
            "moon_sign": (ncd or {}).get("moon_sign"),
            "rising_sign": (ncd or {}).get("rising_sign"),
            "ascendant": (ncd or {}).get("ascendant"),
            "midheaven": (ncd or {}).get("midheaven"),
        },
        # Keyed by canonical tradition id — see frontend contract above.
        # Each entry carries `root` + `data` (scaffold-normalized) plus
        # the full SystemResult envelope (certainty, name, interpretation,
        # references, question, ...).
        "results": {r.id: _build_result_entry(r) for r in results},
    }

    # ── Write JSON ──
    out_path = Path(output_path)
    if not out_path.is_absolute():
        out_path = Path(__file__).parent / out_path
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # ── Terminal summary ──
    print()
    print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SIRR Core 25 — Slim Runner")
    print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Subject     : {profile.subject}")
    print(f"  Arabic      : {profile.arabic}")
    print(f"  DOB         : {date_to_iso(profile.dob)} {profile.birth_time_local or ''}")
    print(f"  Life Path   : Root {profile.life_path}")
    print(f"  Name tier   : {name_length_tier.upper()}")
    print()
    print(f"  Modules run : {len(results)} (14 dominant Root-8 + 11 structural Root-3)")
    print(f"  Certainty   : {cert_counts}")
    print(f"  Groups      : {len(by_group)} independence groups represented")
    for grp, ids in sorted(by_group.items()):
        print(f"    • {grp:20s} [{len(ids)}] {', '.join(ids)}")
    print()
    print(f"  Output      : {out_path}")
    print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    return out


if __name__ == "__main__":
    import argparse
    default_fixture = str(Path(__file__).parent / "fixtures" / "synthetic_profile.json")
    p = argparse.ArgumentParser(description="SIRR Core 25 Slim Runner")
    p.add_argument("fixture", nargs="?", default=default_fixture,
                   help="Profile fixture JSON (default: fixtures/synthetic_profile.json)")
    p.add_argument("--output", default="output_core25.json",
                   help="Output JSON path (default: output_core25.json)")
    args = p.parse_args()
    run_core_25(args.fixture, args.output)
