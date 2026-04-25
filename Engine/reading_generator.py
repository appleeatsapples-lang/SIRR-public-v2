#!/usr/bin/env python3
"""
SIRR AI Reading Generator
========================
Takes engine output.json → Claude API → personalized narrative reading.

The engine computes. The AI interprets. The customer reads.

Usage:
    python reading_generator.py                          # Default: output.json
    python reading_generator.py output_famous_jung.json  # Specific output
    python reading_generator.py output.json --lang ar    # Arabic reading

Requires: ANTHROPIC_API_KEY environment variable
"""
from __future__ import annotations
import json
import sys
import os
from pathlib import Path
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("Install the Anthropic SDK: pip install anthropic")
    sys.exit(1)


# ── Animal & Element Symbolism Lookups ───────────────────────────────────────

ANIMAL_CLASHES = {
    "Rat": "Horse", "Ox": "Goat", "Tiger": "Monkey",
    "Rabbit": "Rooster", "Dragon": "Dog", "Snake": "Pig",
    "Horse": "Rat", "Goat": "Ox", "Monkey": "Tiger",
    "Rooster": "Rabbit", "Dog": "Dragon", "Pig": "Snake",
}

ANIMAL_ALLIES = {
    "Rat": ["Dragon", "Monkey"], "Ox": ["Snake", "Rooster"],
    "Tiger": ["Horse", "Dog"], "Rabbit": ["Goat", "Pig"],
    "Dragon": ["Rat", "Monkey"], "Snake": ["Ox", "Rooster"],
    "Horse": ["Tiger", "Dog"], "Goat": ["Rabbit", "Pig"],
    "Monkey": ["Rat", "Dragon"], "Rooster": ["Ox", "Snake"],
    "Dog": ["Tiger", "Horse"], "Pig": ["Rabbit", "Goat"],
}

ANIMAL_SECRET = {
    "Rat": "Ox", "Ox": "Rat", "Tiger": "Pig", "Pig": "Tiger",
    "Rabbit": "Dog", "Dog": "Rabbit", "Dragon": "Rooster",
    "Rooster": "Dragon", "Snake": "Monkey", "Monkey": "Snake",
    "Horse": "Goat", "Goat": "Horse",
}

ELEMENT_CYCLE = {
    "Wood":  {"produces": "Fire",  "controls": "Earth", "weakened_by": "Fire",  "controlled_by": "Metal"},
    "Fire":  {"produces": "Earth", "controls": "Metal", "weakened_by": "Earth", "controlled_by": "Water"},
    "Earth": {"produces": "Metal", "controls": "Water", "weakened_by": "Metal", "controlled_by": "Wood"},
    "Metal": {"produces": "Water", "controls": "Wood",  "weakened_by": "Water", "controlled_by": "Fire"},
    "Water": {"produces": "Wood",  "controls": "Fire",  "weakened_by": "Wood",  "controlled_by": "Earth"},
}

ANIMAL_GIFTS = {
    "Rat":     ("Strategic intelligence, sees opportunities first", "Hoarding, over-calculating, difficulty trusting"),
    "Ox":      ("Endurance, reliability, steady accumulation",     "Stubbornness, resistance to change, rigidity"),
    "Tiger":   ("Courage, charisma, natural leadership",            "Recklessness, impatience, dominance"),
    "Rabbit":  ("Diplomacy, aesthetic sense, intuition",            "Avoidance, indecisiveness, conflict aversion"),
    "Dragon":  ("Vision, ambition, transformative power",           "Arrogance, overreach, inability to be ordinary"),
    "Snake":   ("Wisdom, depth, strategic patience",                "Jealousy, secrecy, emotional coldness"),
    "Horse":   ("Freedom, enthusiasm, raw energy",                  "Restlessness, unreliability, burnout"),
    "Goat":    ("Creativity, empathy, artistic vision",             "Dependency, anxiety, impracticality"),
    "Monkey":  ("Cleverness, adaptability, problem-solving",        "Manipulation, restlessness, superficiality"),
    "Rooster": ("Precision, honesty, systematic thinking",          "Criticism, perfectionism, abrasiveness"),
    "Dog":     ("Loyalty, justice, principled action",              "Anxiety, judgmentalism, pessimism"),
    "Pig":     ("Generosity, sensuality, idealism",                 "Naivety, excess, difficulty with boundaries"),
}


def extract_animal_profile(output_data: dict) -> dict:
    """Extract the person's animal & element signature from engine output.

    Pulls from chinese_zodiac, bazi_pillars, bazi_hidden_stems, bazi_daymaster,
    nakshatra, nine_star_ki, celtic_tree, mayan, and temperament modules.
    """
    idx = {r["id"]: r.get("data", {}) for r in output_data.get("results", [])}

    cz = idx.get("chinese_zodiac", {})
    bazi = idx.get("bazi_pillars", {})
    bh = idx.get("bazi_hidden_stems", {})
    bdm = idx.get("bazi_daymaster", {})
    nak = idx.get("nakshatra", {})
    nsk = idx.get("nine_star_ki", {})
    ct = idx.get("celtic_tree", {})
    may = idx.get("mayan", {})
    temp = idx.get("temperament", {})

    def pillar_field(p: dict, field: str):
        if isinstance(p, dict):
            return p.get(field)
        return None

    year_p = bazi.get("year_pillar", {}) if isinstance(bazi.get("year_pillar"), dict) else {}
    month_p = bazi.get("month_pillar", {}) if isinstance(bazi.get("month_pillar"), dict) else {}
    day_p = bazi.get("day_pillar", {}) if isinstance(bazi.get("day_pillar"), dict) else {}
    hour_p = bazi.get("hour_pillar", {}) if isinstance(bazi.get("hour_pillar"), dict) else {}

    animal = cz.get("animal")
    gift, shadow = ANIMAL_GIFTS.get(animal, ("", ""))

    return {
        # Primary Chinese zodiac (year-based)
        "animal": animal,
        "element": cz.get("stem_element"),
        "polarity": cz.get("stem_polarity"),
        "fixed_element": cz.get("branch_element"),
        "trine_group": cz.get("trine_group"),
        "gift": gift,
        "shadow": shadow,

        # BaZi four pillars (animal per pillar)
        "year_animal": pillar_field(year_p, "animal"),
        "year_element": pillar_field(year_p, "stem_element"),
        "month_animal": pillar_field(month_p, "animal"),
        "month_element": pillar_field(month_p, "stem_element"),
        "day_animal": pillar_field(day_p, "animal"),
        "day_element": pillar_field(day_p, "stem_element"),
        "hour_animal": pillar_field(hour_p, "animal"),

        # Day Master
        "day_master_element": bdm.get("day_master_element"),
        "day_master_polarity": bdm.get("day_master_polarity"),
        "day_master_strength": bdm.get("classification"),

        # Hidden elements distribution
        "hidden_elements": bh.get("hidden_element_distribution", {}),

        # Relationships (computed from lookup)
        "enemy": ANIMAL_CLASHES.get(animal),
        "allies": ANIMAL_ALLIES.get(animal, []),
        "secret_friend": ANIMAL_SECRET.get(animal),

        # Vedic animal
        "nakshatra_animal": nak.get("animal"),
        "nakshatra_name": nak.get("nakshatra_name"),
        "nakshatra_deity": nak.get("deity"),
        "nakshatra_symbol": nak.get("symbol"),

        # Nine Star Ki
        "ki_year_element": nsk.get("year_element"),
        "ki_month_element": nsk.get("month_element"),

        # Celtic tree
        "celtic_tree": ct.get("tree"),
        "celtic_meaning": ct.get("meaning"),

        # Mayan tzolkin
        "mayan_sign": may.get("tzolkin"),

        # Temperament
        "temperament_element": temp.get("primary_element"),
        "temperament_type": temp.get("primary_temperament"),
    }


def _classify_animal_relationship(animal_a: str, animal_b: str) -> str:
    """Return 'allies' | 'enemies' | 'secret_friends' | 'same' | 'neutral'."""
    if not animal_a or not animal_b:
        return "neutral"
    if animal_a == animal_b:
        return "same"
    if animal_b in ANIMAL_ALLIES.get(animal_a, []):
        return "allies"
    if ANIMAL_CLASHES.get(animal_a) == animal_b:
        return "enemies"
    if ANIMAL_SECRET.get(animal_a) == animal_b:
        return "secret_friends"
    return "neutral"


def _compute_element_interaction(elem_a: str, elem_b: str) -> dict:
    """Return the Wu Xing interaction type from elem_a TO elem_b."""
    if not elem_a or not elem_b:
        return {"type": "unknown", "description": ""}
    if elem_a == elem_b:
        return {"type": "resonance", "description": f"{elem_a} = {elem_b}: identical frequency"}
    cyc = ELEMENT_CYCLE.get(elem_a, {})
    if cyc.get("produces") == elem_b:
        return {"type": "nurturing", "description": f"{elem_a} produces {elem_b}: feeds energy naturally"}
    if cyc.get("controls") == elem_b:
        return {"type": "dominance", "description": f"{elem_a} controls {elem_b}: overrides the other"}
    if cyc.get("weakened_by") == elem_b:
        return {"type": "drain", "description": f"{elem_b} exhausts {elem_a}"}
    if cyc.get("controlled_by") == elem_b:
        return {"type": "submission", "description": f"{elem_b} controls {elem_a}: the other overrides"}
    return {"type": "neutral", "description": f"{elem_a} and {elem_b} do not form a direct Wu Xing relation"}


def _find_cross_mirrors(a: dict, b: dict) -> list:
    """Find cases where one person's Day animal appears as other's Year animal."""
    mirrors = []
    if a.get("day_animal") and a.get("day_animal") == b.get("year_animal"):
        mirrors.append({
            "type": "a_day_equals_b_year",
            "animal": a["day_animal"],
            "meaning": "A's core self carries the animal B wears publicly",
        })
    if b.get("day_animal") and b.get("day_animal") == a.get("year_animal"):
        mirrors.append({
            "type": "b_day_equals_a_year",
            "animal": b["day_animal"],
            "meaning": "B's core self carries the animal A wears publicly",
        })
    return mirrors


def _find_shared_animals(a: dict, b: dict) -> list:
    """Return any animals that appear in both people's pillar set."""
    pillars_a = {a.get(k) for k in ("year_animal", "month_animal", "day_animal", "hour_animal") if a.get(k)}
    pillars_b = {b.get(k) for k in ("year_animal", "month_animal", "day_animal", "hour_animal") if b.get(k)}
    return sorted(pillars_a & pillars_b)


def compute_animal_dyad(profile_a: dict, profile_b: dict) -> dict:
    """Compute the animal & element interaction between two engine outputs.

    profile_a and profile_b are full engine output dicts (not pre-extracted).
    """
    a = extract_animal_profile(profile_a)
    b = extract_animal_profile(profile_b)

    return {
        "person_a": {
            "animal": a.get("animal"),
            "element": a.get("element"),
            "day_master_element": a.get("day_master_element"),
            "day_master_strength": a.get("day_master_strength"),
            "day_animal": a.get("day_animal"),
        },
        "person_b": {
            "animal": b.get("animal"),
            "element": b.get("element"),
            "day_master_element": b.get("day_master_element"),
            "day_master_strength": b.get("day_master_strength"),
            "day_animal": b.get("day_animal"),
        },
        "animal_relationship": _classify_animal_relationship(a.get("animal"), b.get("animal")),
        "element_interaction": _compute_element_interaction(
            a.get("day_master_element"), b.get("day_master_element")
        ),
        "strength_dynamic": f"{a.get('day_master_strength')} vs {b.get('day_master_strength')}",
        "cross_mirrors": _find_cross_mirrors(a, b),
        "shared_animals": _find_shared_animals(a, b),
        "is_enemy_pair": (
            a.get("animal") == b.get("enemy") or b.get("animal") == a.get("enemy")
        ),
    }


def build_animal_ground_truth(animal: dict) -> str:
    """Render the ANIMAL PROFILE block for Claude ground-truth injection."""
    if not animal.get("animal"):
        return ""
    allies = ", ".join(animal.get("allies", [])) or "—"
    return f"""
ANIMAL PROFILE:
- Chinese zodiac: {animal.get('element','?')} {animal.get('polarity','?')} {animal.get('animal','?')} ({animal.get('trine_group','?')})
- Fixed element (branch): {animal.get('fixed_element','?')}
- BaZi pillars: Year={animal.get('year_animal','?')}, Month={animal.get('month_animal','?')}, Day={animal.get('day_animal','?')}
- Day Master: {animal.get('day_master_polarity','?')} {animal.get('day_master_element','?')} ({animal.get('day_master_strength','?')})
- Hidden elements: {animal.get('hidden_elements') or '—'}
- Enemy sign: {animal.get('enemy','?')} — structural growth challenge
- Allies: {allies}
- Secret friend: {animal.get('secret_friend','?')}
- Vedic animal: {animal.get('nakshatra_animal','?')} ({animal.get('nakshatra_name','?')} — {animal.get('nakshatra_deity','?')})
- Celtic tree: {animal.get('celtic_tree','?')} ({animal.get('celtic_meaning','?')})
- Mayan tzolkin: {animal.get('mayan_sign','?')}
- Temperament: {animal.get('temperament_type','?')} ({animal.get('temperament_element','?')})
- Primary gift: {animal.get('gift','')}
- Primary shadow: {animal.get('shadow','')}
"""


def build_dyad_animal_ground_truth(dyad: dict, name_a: str, name_b: str) -> str:
    """Render the ANIMAL DYAD block for Claude ground-truth injection."""
    pa = dyad.get("person_a", {})
    pb = dyad.get("person_b", {})
    ei = dyad.get("element_interaction", {})
    mirrors = dyad.get("cross_mirrors", [])
    mirror_lines = "\n".join(f"  - {m['type']}: {m['animal']} — {m['meaning']}" for m in mirrors) or "  none"
    shared = ", ".join(dyad.get("shared_animals", [])) or "none"
    return f"""
ANIMAL DYAD:
- {name_a}: {pa.get('element','?')} {pa.get('animal','?')} (Day Master: {pa.get('day_master_element','?')} {pa.get('day_master_strength','?')}, Day animal: {pa.get('day_animal','?')})
- {name_b}: {pb.get('element','?')} {pb.get('animal','?')} (Day Master: {pb.get('day_master_element','?')} {pb.get('day_master_strength','?')}, Day animal: {pb.get('day_animal','?')})
- Animal relationship: {dyad.get('animal_relationship','neutral')}
- Element cycle ({pa.get('day_master_element','?')} → {pb.get('day_master_element','?')}): {ei.get('type','?')} — {ei.get('description','')}
- Strength dynamic: {dyad.get('strength_dynamic','?')}
- Cross-pillar mirrors:
{mirror_lines}
- Shared animals across pillars: {shared}
- Enemy pair: {dyad.get('is_enemy_pair', False)}
"""


# ── Planetary Symbolism Lookups ──────────────────────────────────────────────

PLANET_GIFTS = {
    "Sun":     ("Identity, authority, vitality, purpose",                   "Pride, ego inflation, burnout",              "Fire",        "Self, visibility"),
    "Moon":    ("Emotion, intuition, nurturing, memory",                    "Moodiness, dependency, oversensitivity",     "Water",       "Inner life, comfort"),
    "Mercury": ("Communication, analysis, adaptability",                    "Overthinking, anxiety, scattered focus",     "Air",         "Mind, trade, speech"),
    "Venus":   ("Love, beauty, pleasure, harmony, values",                  "Indulgence, vanity, avoidance",              "Earth/Water", "Relationships, art"),
    "Mars":    ("Action, courage, drive, initiative",                       "Anger, aggression, impatience",              "Fire",        "Will, competition"),
    "Jupiter": ("Expansion, wisdom, generosity, faith",                     "Excess, overconfidence, self-righteousness", "Fire/Air",    "Growth, teaching"),
    "Saturn":  ("Discipline, structure, endurance, mastery",                "Restriction, fear, rigidity, isolation",     "Earth",       "Limits, time, karma"),
    "Rahu":    ("Ambition, worldly desire, innovation",                     "Obsession, illusion, insatiability",         "Shadow",      "What you chase"),
    "Ketu":    ("Detachment, spiritual insight, release",                   "Confusion, loss, disconnection",             "Shadow",      "What you release"),
}

PLANET_GLYPHS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Rahu": "☊", "Ketu": "☋",
}


def extract_planetary_profile(output_data: dict) -> dict:
    """Extract the person's planetary timing & rulership signature from engine output.

    Pulls from firdaria, vimshottari, planetary_joy, profection, nakshatra,
    bazi_daymaster, god_of_day, and almuten modules.
    """
    idx = {r["id"]: r.get("data", {}) for r in output_data.get("results", [])}

    firdaria = idx.get("firdaria", {})
    vimshottari = idx.get("vimshottari", {})
    joy = idx.get("planetary_joy", {})
    profection = idx.get("profection", {})
    nak = idx.get("nakshatra", {})
    bdm = idx.get("bazi_daymaster", {})
    god = idx.get("god_of_day", {})
    almuten = idx.get("almuten", {})

    in_joy = joy.get("in_joy", []) or []
    near_joy = joy.get("near_joy", []) or []
    primary_joy = in_joy[0] if in_joy else (near_joy[0] if near_joy else None)

    return {
        # Current timing — Firdaria (Hellenistic / medieval Islamic)
        "firdaria_major": firdaria.get("major_planet"),
        "firdaria_sub": firdaria.get("sub_planet"),
        "firdaria_combined": firdaria.get("combined"),
        "firdaria_period_range": firdaria.get("period_range"),
        "firdaria_quality": firdaria.get("period_quality"),

        # Current timing — Vimshottari (Vedic)
        "vedic_current_dasha": vimshottari.get("current_maha_dasha"),
        "vedic_dasha_start": vimshottari.get("current_dasha_start_age"),
        "vedic_dasha_end": vimshottari.get("current_dasha_end_age"),
        "vedic_years_remaining": vimshottari.get("years_remaining"),
        "vedic_birth_ruler": vimshottari.get("birth_nakshatra_ruler"),
        "vedic_timeline": vimshottari.get("timeline", []),

        # Planetary joy (which planet is at home)
        "planets_in_joy": in_joy,
        "planets_near_joy": near_joy,
        "primary_joy_planet": primary_joy,
        "joy_headline": joy.get("headline"),
        "joy_details": joy.get("planets", {}),

        # Profection year
        "profection_house": profection.get("house"),
        "profection_info": profection.get("house_info"),

        # Nakshatra birth ruler
        "nakshatra_ruler": nak.get("ruler"),
        "nakshatra_name": nak.get("nakshatra_name"),

        # BaZi element bridge
        "day_master": bdm.get("day_master_element"),
        "day_master_polarity": bdm.get("day_master_polarity"),
        "day_master_strength": bdm.get("classification"),

        # Day deity
        "birth_deity": god.get("deity"),

        # Almuten (medieval planetary governor)
        "almuten": almuten.get("almuten"),
    }


def build_planetary_ground_truth(planet: dict) -> str:
    """Render the PLANETARY PROFILE block for Claude ground-truth injection."""
    if not planet.get("primary_joy_planet") and not planet.get("firdaria_major"):
        return ""
    joy = planet.get("primary_joy_planet") or "—"
    joy_details = planet.get("joy_details", {}) or {}
    joy_rationale = joy_details.get(joy, {}).get("rationale", "") if joy != "—" else ""
    near = ", ".join(planet.get("planets_near_joy", [])) or "—"
    firdaria = planet.get("firdaria_combined") or f"{planet.get('firdaria_major','?')}/{planet.get('firdaria_sub','?')}"
    dasha = planet.get("vedic_current_dasha") or "?"
    dasha_range = ""
    if planet.get("vedic_dasha_start") is not None and planet.get("vedic_dasha_end") is not None:
        dasha_range = f" (age {planet['vedic_dasha_start']:.1f}–{planet['vedic_dasha_end']:.1f})"
    return f"""
PLANETARY PROFILE:
- Planet in Joy: {joy} — strongest planetary energy, fully expressed{f' ({joy_rationale})' if joy_rationale else ''}
- Planet near Joy: {near}
- Current Firdaria: {firdaria} — planetary weather of this life phase
- Current Vedic Mahadasha: {dasha}{dasha_range} — long-cycle planetary season
- Birth ruler (Nakshatra): {planet.get('nakshatra_ruler','?')} ({planet.get('nakshatra_name','?')})
- Profection year: House {planet.get('profection_house','?')} — {planet.get('profection_info','')}
- Day Master: {planet.get('day_master_polarity','?')} {planet.get('day_master','?')} ({planet.get('day_master_strength','?')})
- Almuten (medieval governor): {planet.get('almuten','?')}
- Birth deity (Egyptian day ruler): {planet.get('birth_deity','?')}
"""


def compute_planetary_dyad(profile_a: dict, profile_b: dict) -> dict:
    """Compute the planetary timing interaction between two engine outputs."""
    a = extract_planetary_profile(profile_a)
    b = extract_planetary_profile(profile_b)

    a_joy = a.get("primary_joy_planet")
    b_joy = b.get("primary_joy_planet")
    a_dasha = a.get("vedic_current_dasha")
    b_dasha = b.get("vedic_current_dasha")
    a_firdaria = a.get("firdaria_major")
    b_firdaria = b.get("firdaria_major")

    return {
        "person_a": {
            "joy": a_joy,
            "firdaria": a.get("firdaria_combined"),
            "vedic_dasha": a_dasha,
            "nakshatra_ruler": a.get("nakshatra_ruler"),
            "profection_house": a.get("profection_house"),
        },
        "person_b": {
            "joy": b_joy,
            "firdaria": b.get("firdaria_combined"),
            "vedic_dasha": b_dasha,
            "nakshatra_ruler": b.get("nakshatra_ruler"),
            "profection_house": b.get("profection_house"),
        },
        "firdaria_harmony": bool(a_firdaria) and a_firdaria == b_firdaria,
        "vedic_harmony": bool(a_dasha) and a_dasha == b_dasha,
        "joy_cross": {
            "a_joy_matches_b_period": bool(a_joy) and a_joy in (b_dasha, b_firdaria),
            "b_joy_matches_a_period": bool(b_joy) and b_joy in (a_dasha, a_firdaria),
        },
        "birth_rulers": (a.get("nakshatra_ruler"), b.get("nakshatra_ruler")),
        "birth_rulers_match": (
            bool(a.get("nakshatra_ruler"))
            and a.get("nakshatra_ruler") == b.get("nakshatra_ruler")
        ),
    }


def build_dyad_planetary_ground_truth(dyad: dict, name_a: str, name_b: str) -> str:
    """Render the PLANETARY DYAD block for Claude ground-truth injection."""
    pa = dyad.get("person_a", {})
    pb = dyad.get("person_b", {})
    jc = dyad.get("joy_cross", {})
    rulers = dyad.get("birth_rulers", (None, None))
    return f"""
PLANETARY DYAD:
- {name_a}: Joy planet = {pa.get('joy','?')}, Firdaria = {pa.get('firdaria','?')}, Vedic dasha = {pa.get('vedic_dasha','?')}, Nakshatra ruler = {pa.get('nakshatra_ruler','?')}, Profection house = {pa.get('profection_house','?')}
- {name_b}: Joy planet = {pb.get('joy','?')}, Firdaria = {pb.get('firdaria','?')}, Vedic dasha = {pb.get('vedic_dasha','?')}, Nakshatra ruler = {pb.get('nakshatra_ruler','?')}, Profection house = {pb.get('profection_house','?')}
- Firdaria harmony (same major period): {dyad.get('firdaria_harmony', False)}
- Vedic harmony (same mahadasha): {dyad.get('vedic_harmony', False)}
- {name_a}'s Joy planet matches {name_b}'s current period: {jc.get('a_joy_matches_b_period', False)}
- {name_b}'s Joy planet matches {name_a}'s current period: {jc.get('b_joy_matches_a_period', False)}
- Birth rulers: {rulers[0]} ({name_a}) vs {rulers[1]} ({name_b})
- Birth rulers match: {dyad.get('birth_rulers_match', False)}
"""


# ── Dashboard Panel System Prompt (v2 — JSON output, card-ready) ─────────────

SYSTEM_PROMPT_DASHBOARD = """You are the reading writer for SIRR.

Your task is to transform structured symbolic findings into a compact dashboard reading made of 6 visual panels. This is not a flowing essay. It is a character-sheet style instrument: dense, direct, and readable inside cards.

OUTPUT CONTRACT
Return ONLY valid JSON.
No markdown fencing.
No preamble.
Start with {

The JSON shape must be exactly:

{
  "panels": [
    {
      "id": "dominant_thread",
      "title": "The Dominant Thread",
      "symbol": "<Arabic numeral for dominant root>",
      "color": "amber",
      "body": "..."
    },
    {
      "id": "the_split",
      "title": "The Split",
      "symbol": "♛",
      "color": "indigo",
      "body": "..."
    },
    {
      "id": "threshold",
      "title": "Threshold Birth",
      "symbol": "⊙",
      "color": "teal",
      "body": "..."
    },
    {
      "id": "witness",
      "title": "The Witness",
      "symbol": "◎",
      "color": "bronze",
      "body": "..."
    },
    {
      "id": "the_name",
      "title": "The Name",
      "symbol": "〜",
      "color": "green",
      "body": "..."
    },
    {
      "id": "current_season",
      "title": "Current Season",
      "symbol": "⏳",
      "color": "dim",
      "body": "..."
    }
  ],
  "closing_line": "One sentence. The landing. Not a summary — a mirror."
}

GLOBAL WRITING RULES
- Each panel body must be 4-6 sentences maximum.
- No filler. No scene-setting. No transitions like "Furthermore," "Additionally," or "Moreover."
- The first sentence must land immediately.
- Every sentence must carry meaning.
- Use the person's first name naturally, at most once per panel.
- Bold key identity labels when they matter: **The Synthesizer**, **Root 3**, **Threshold**, etc.
- Italicize tradition terms when used: *tajalli*, *tawafuq*, *Sandhi*, *Talawwun*.
- Never use these words in the reading body: "convergence", "module", "system", "baseline", "p-value", "percentile".
- Never predict future events.
- Never use destiny, fate, or inevitability language.
- Never issue commands or prescriptions.
- Never moralize tensions. Contradictions are structural features, not flaws.

CONSTITUTIONAL RULES
- Mirror, not crystal ball.
- Agency protection at all times.
- Include one honest sentence early in the reading: these are ancient symbolic frameworks; the analysis measures their agreement, not whether they access something objectively real.
- Contradiction transparency: opposing signals shown honestly, not smoothed over.

CONFIDENCE MAPPING
- 20+ traditions align → "Every tradition examined points to..."
- 12-19 align → "Multiple independent traditions..."
- 8-11 align → "Several traditions suggest..."
- Fewer than 8 → "Some traditions hint at..."

ANIMAL SYMBOLISM
The ground truth includes an ANIMAL PROFILE block with the person's Chinese zodiac
animal (element + polarity + animal), their BaZi four pillar animals (year / month /
day / hour), their Day Master element and strength, their enemy sign, allies, and
secret friend, plus Vedic, Celtic, and Mayan animals.

Weave animal references into the panels naturally. Recommended placement:
- **dominant_thread**: If the animal reinforces the dominant root, name it once
  (e.g. "a Fire Rat strategist"). Element modifies animal — say "Fire Rat," not
  "Rat," when element matters.
- **the_split**: If the Year animal and Day animal differ, this is THE structural
  place to name that split. Year = public mask, Day = core self. 
  publicly but a Pig privately. Describe the tension concretely.
- **the_name** or core panel: may mention the primary animal's gift and shadow
  in compressed form — one clause each, not a list.
- Never call a person "a Rat" flatly. Use "the Fire Rat pattern," "the Rat axis,"
  "what the Rat symbol brings." These are structural handles, not identities.
- Never write predictive animal language ("your Rat year brings…"). Stay mirror-only.

PLANETARY SYMBOLISM
The ground truth also includes a PLANETARY PROFILE block with the person's
Planet in Joy (strongest planetary energy, structurally at home), current
Firdaria + Vedic Mahadasha (two timing systems describing the current season),
Nakshatra birth ruler (the planet that seeded their emotional body), and
Profection house.

Weave planets into panels as follows:
- **current_season**: THIS IS THE MAIN PLANETARY HOME. Merge Firdaria + Vedic
  into ONE weather description, not two mechanical listings. "A Mercury/Sun
  Firdaria inside a Rahu Vedic season" becomes "intellectual work meeting
  recognition, inside a longer arc of worldly ambition." Describe as climate,
  never as instruction.
- **dominant_thread** or **witness**: may reference the Planet in Joy if it
  reinforces the dominant root. The Moon in Joy reinforces communicative
  (Root 3) + emotionally architectural pattern.
- **the_name**: the Nakshatra birth ruler can appear here as "the planet that
  seeded your emotional body."
- Use planet glyphs sparingly in panel bodies (☽ ☉ ☿ ♀ ♂ ♃ ♄). Don't
  decorate — only use when a single glyph adds clarity.
- NEVER predict outcomes from planetary timing. Describe atmosphere, not events.
"""

# ── Three-Tier Convergence Point ─────────────────────────────────────────────
#
# Source: Docs/engine/CONVERGENCE_TIERS_AND_ONBOARDING.md
# Locked April 11, 2026 by ChatGPT. This is deterministic production copy —
# NOT AI-generated. The block is selected by name_length_tier and injected
# verbatim into the reading.

CONVERGENCE_POINT_SHORT = """Across systems with no shared origin, the same pattern appears in a different language: your life moves best when expression serves structure.

This is the convergence point of your reading. Your path becomes clear when your expressive nature is given weight, direction, and standards. When the 3 in you leads without shape, energy disperses. Too many openings appear at once. But when the 8 takes over without the 3, life narrows past what is humanly alive.

So the work is not choosing one side. The work is union. Your speech must carry authority without becoming hard. Your standards must remain high without sealing off warmth, wit, and movement. Your strongest periods are rarely the loosest ones. They are the periods in which your voice becomes deliberate, your direction becomes visible, and your energy stops scattering itself across places that do not deserve your seriousness."""

CONVERGENCE_POINT_MEDIUM = """Across systems with no shared origin, the same pattern appears in a different language: your life moves best when expression serves structure.

With a partial nasab, the convergence is already clear enough to name. Islamic letter science, Mandaean Gnostic cosmology, Chinese palace astrology, and the African binary oracle are not variations of one method. They were built in different civilizations for different purposes. Yet here they still return the same underlying tension: expression becomes strongest when it is given form, limit, and consequence.

This is the convergence point of your reading. Not softness against strength. Not creativity against discipline. Something more exact than that. When the 3 in you leads without shape, energy disperses. Too many openings appear at once, and the center thins out. But when the 8 takes over without the 3, the opposite problem emerges: life becomes efficient, controlled, and narrowed past what is humanly alive.

So the work is not choosing one side. The work is union. Your speech must carry authority without becoming hard. Your standards must remain high without sealing off warmth, wit, and movement. Your natural intelligence is not meant to decorate your life from the outside; it is meant to become an instrument of order, persuasion, and durable impact."""

CONVERGENCE_POINT_LONG = """Across systems with no shared origin, the same pattern appears in a different language: your life moves best when expression serves structure.

With the full nasab present, the signal becomes stronger and more precise. Islamic letter science, Mandaean Gnostic cosmology, Chinese palace astrology, and the African binary oracle are not variations of one method. They were built in different civilizations for different purposes. Yet here they converge on the same pattern. 15 of 25 independent traditions. No comparable profile of matching length has reached this number.

That does not change the substance of the reading. It clarifies it. Not softness against strength. Not creativity against discipline. Something more exact than that. Your path becomes clear when your expressive nature is given weight, direction, and standards. When the 3 in you leads without shape, energy disperses. Too many openings appear at once. Too much becomes possible, and the center thins out. But when the 8 takes over without the 3, the opposite problem emerges: life becomes efficient, controlled, and narrowed past what is humanly alive.

So the work is not choosing one side. The work is union. Your speech must carry authority without becoming hard. Your standards must remain high without sealing off warmth, wit, and movement. Your natural intelligence is not meant to decorate your life from the outside; it is meant to become an instrument of order, persuasion, and durable impact.

This is why your strongest periods are rarely the loosest ones. They are the periods in which your voice becomes deliberate, your direction becomes visible, and your energy stops scattering itself across places that do not deserve your seriousness."""

CONVERGENCE_POINT_BLOCKS = {
    "short": CONVERGENCE_POINT_SHORT,
    "medium": CONVERGENCE_POINT_MEDIUM,
    "long": CONVERGENCE_POINT_LONG,
}


def _extract_name_length_tier(data: dict) -> str | None:
    """Pull name_length_tier from engine output.

    Checks (in order):
      1. data["profile"]["name_length_tier"]              (sirr_core_25 format)
      2. data["name_length_tier"]["tier"]                 (web_backend server format)
      3. data["name_length_tier"]                         (flat string fallback)

    Returns the normalized tier string ("short"/"medium"/"long") or None.
    """
    profile = data.get("profile") or {}
    tier = profile.get("name_length_tier")
    if isinstance(tier, str) and tier.lower() in CONVERGENCE_POINT_BLOCKS:
        return tier.lower()

    nlt = data.get("name_length_tier")
    if isinstance(nlt, dict):
        t = nlt.get("tier")
        if isinstance(t, str) and t.lower() in CONVERGENCE_POINT_BLOCKS:
            return t.lower()
    elif isinstance(nlt, str) and nlt.lower() in CONVERGENCE_POINT_BLOCKS:
        return nlt.lower()

    return None


def get_convergence_point(tier: str) -> str:
    """Return the locked Convergence Point prose for a given tier.

    Raises ValueError if tier is not one of 'short' / 'medium' / 'long'.
    """
    key = (tier or "").lower()
    if key not in CONVERGENCE_POINT_BLOCKS:
        raise ValueError(
            f"Unknown name_length_tier {tier!r} — expected 'short', 'medium', or 'long'"
        )
    return CONVERGENCE_POINT_BLOCKS[key]


def inject_convergence_point(reading: str, data: dict) -> str:
    """Prepend the tier-appropriate Convergence Point block to a reading.

    If the engine output contains no recognisable tier field, the reading
    is returned unchanged.
    """
    tier = _extract_name_length_tier(data)
    if tier is None:
        return reading
    block = get_convergence_point(tier)
    return f"{block}\n\n---\n\n{reading}"


# ── Legacy prose prompt (kept for PDF/markdown fallback) ─────────────────────

SYSTEM_PROMPT = """You are the interpretive voice behind a cross-tradition identity analysis engine.

## What you receive
A JSON profile containing: a person's name (Latin + Arabic), date of birth, computed values from 17 civilizational traditions, convergence strength data, structural patterns, element signatures, and timing cycles.

## What you produce
A 1,500–2,500 word personal reading in {lang_name}. This is the product a customer pays for. It should feel like receiving a letter from someone who studied you through the lens of 17 civilizations.

## THE CRITICAL RULE: The engine is invisible
The customer NEVER sees how the engine works. No module counts, no system counts, no p-values, no percentiles, no Monte Carlo baselines, no independence groups, no convergence thresholds. These are the lab instruments — the customer sees the results, not the machinery.

Instead, the convergence data drives your WRITING CONFIDENCE:
- When 20+ systems agree on a value → write with full authority ("this is the dominant thread," "across every tradition examined")
- When 12-19 systems agree → write with strong confidence ("a clear pattern emerges," "multiple traditions independently point to")
- When 8-11 systems agree → write with moderate confidence ("several traditions recognize," "a recurring theme appears")
- When fewer agree → write with soft language ("some traditions suggest," "there are hints of")

The reader should feel the strength of the signal through the PROSE, not through numbers.

## Constitutional rules — ABSOLUTE, NON-NEGOTIABLE
1. **Mirror, not crystal ball.** Describe what the traditions reflect. NEVER predict the future. No "you will," "expect to," "this year brings."
2. **Agency protection.** NEVER use coercive language. No "you must," "your fate is," "you are destined to." The reader decides what it means.
3. **No prophecy.** All outputs are structural observations, not destiny claims.
4. **Contradiction transparency.** When traditions disagree, say so. Frame tensions as interesting, not as problems.
5. **Intellectual honesty.** State once, early: these are ancient symbolic frameworks — possibly meaningful, possibly coincidence. This analysis measures their agreement across cultures, not whether they access something objectively real.
6. **Warm precision.** Intelligent, grounded, warm. Like a thoughtful friend who studied your identity through 17 different cultural lenses. Not mystical-woo. Not clinical-cold.
7. **No technical jargon.** Never mention: modules, systems count, convergence count, independence groups, p-values, percentiles, baselines, Monte Carlo. The reader should not know the engine exists.

## Narrative structure
Weave these into flowing prose. No visible section headers.

### Opening (150-250 words)
Ground the reader. Name them. Their birth date, what season, what astronomical moment. Set the tone: this is a reflection drawn from humanity's oldest symbolic traditions. A mirror, not a fortune.

### The Dominant Thread (300-500 words)
What is the strongest signal? Describe WHAT it means, not how many systems found it. Let each tradition speak in its own voice — Arabic Hurufism, Western numerology, Vedic thought, Chinese cosmology, Hebrew Kabbalah. Show how different civilizations, separated by centuries and continents, describe the same quality. The reader should feel the weight of agreement through the richness of description, not through statistics.

### The Name (200-400 words)
What the name reveals. Expression, Soul Urge, Personality — but described as qualities, not as numbers. "The vowels of your name — the sounds you breathe — point toward..." rather than "Your Soul Urge is 4." The numbers appear naturally in context, not as data points. If there's a particularly striking name quality (Master Number, etc.), give it weight.

### The Productive Tensions (200-400 words)
Where traditions disagree. Frame as depth, not confusion. "Not every tradition sees you the same way — and the places where they part are as revealing as the places where they agree." Describe what each side of the tension looks like in lived experience.

### The Animals (200-350 words)
The person has multiple animal signs across traditions, not one. Include a dedicated paragraph about their animal symbolism. Use the ANIMAL PROFILE block in ground truth. Explain what their PRIMARY (year) animal GIVES them (its gift) and what it COSTS them (its shadow). If their Day animal differs from their Year animal, name the split explicitly — the Year animal is the public mask, the Day animal is the core self. Element modifies animal: Fire Rat ≠ Water Rat. Mention the enemy sign as a structural growth challenge (not a threat, not a villain). You may weave in the Vedic, Celtic, and Mayan animals briefly for cross-cultural texture. Animals are structural symbols, not character verdicts — never write "you ARE a Rat."

### The Planets (250-400 words)
The ground truth includes a PLANETARY PROFILE block. Weave in:
1. The person's **Planet in Joy** — which planet is structurally most at home in their chart. Name it, name its gift (what it gives them), and name its shadow (what it costs them when overexpressed). A planet "in joy" operates at full capacity, which means its shadow is amplified too.
2. Their **current planetary season** — weave Firdaria and Vedic Mahadasha into a single "weather report," not two mechanical listings. If they are in a Mercury/Sun Firdaria and a Rahu Vedic dasha, that's one paragraph about the texture of this life phase, not two paragraphs about two systems.
3. The **birth ruler** — the planet that rules their Nakshatra. This is "the planet that seeded your emotional body" — a more foundational note than current transits.
4. Optionally: how the ruling planet reinforces or complicates their Life Path / dominant root. If the numeric signal and the planetary signal agree, note it. If they contrast, name the contrast honestly.

Describe planetary periods as ATMOSPHERIC CONDITIONS, not instructions. "This is a Rahu season — worldly ambition runs hot, unconventional paths beckon" — never "you should pursue worldly ambition."

### The Present Season (150-300 words)
Current timing cycles — but described as weather, seasons, atmosphere. "You are in what several traditions describe as a contractive period — a season of consolidation rather than expansion." No specific system names unless they add cultural texture.

### The Closing (100-200 words)
The mirror metaphor. A single sentence that resonates. Not a summary — a landing.

## Formatting
- Flowing prose, no bullet points, no numbered lists
- Bold sparingly — only key identity qualities, not numbers
- Use the person's first name naturally
- No section headers in the output
- End with one sentence that lands

## What you must NEVER do
- Mention module counts, system counts, convergence counts, or any engine mechanics
- Use words: "convergence," "module," "system," "baseline," "p-value," "percentile," "Monte Carlo"
- Make predictions about career, relationships, health, or future events
- Use astrology-column language
- Recommend actions
- Use "destiny," "fate," "meant to be," "written in the stars"
- Generate content longer than 3,000 words
"""


# ── Data extraction ──────────────────────────────────────────────────────────

def extract_reading_context(data: dict) -> dict:
    """Extract the key fields the AI needs from a full output.json."""
    profile = data.get("profile", {})
    synth = data.get("synthesis", {})
    sr = data.get("semantic_reading", {})
    psych = data.get("psychological_mirror", {})
    core = profile.get("core_numbers", {})

    # Results index
    results = data.get("results", [])
    mods = {r["id"]: r.get("data", {}) for r in results}

    # Number convergences — top 5
    nc = synth.get("number_convergences", [])
    top_conv = sorted(nc, key=lambda x: -x.get("system_count", 0))[:5]

    # Element convergences
    ec = synth.get("element_convergences", [])

    # Meta patterns
    meta = sr.get("meta_patterns_fired", [])
    fired = [p for p in meta if p.get("fired")]

    # Timing
    timing = {}
    for tid in ["personal_year", "firdaria", "vimshottari", "biorhythm",
                 "profection", "steiner_cycles"]:
        if tid in mods:
            timing[tid] = mods[tid]

    # Key tradition outputs for narrative color
    traditions = {}
    for tid in ["abjad_kabir", "chaldean", "nakshatra", "bazi_pillars",
                 "bazi_daymaster", "chinese_zodiac", "human_design",
                 "tarot_birth", "ifa", "tree_of_life", "enneagram_dob",
                 "temperament", "hebrew_gematria", "greek_isopsephy",
                 "celtic_tree", "mayan", "nine_star_ki"]:
        if tid in mods:
            traditions[tid] = mods[tid]

    return {
        "subject": profile.get("subject", "UNKNOWN"),
        "arabic": profile.get("arabic", ""),
        "dob": profile.get("dob", ""),
        "location": profile.get("location", ""),
        "variant": profile.get("variant", ""),
        "core_numbers": core,
        "convergence_summary": {
            "total_convergences": synth.get("convergence_count", 0),
            "resonances": synth.get("resonance_count", 0),
            "significant": synth.get("significant_count", 0),
            "top_convergences": top_conv,
        },
        "element_convergences": ec[:3],
        "meta_patterns": fired,
        "timing": timing,
        "traditions": traditions,
        "psychological_mirror": psych,
        "agreement_score": sr.get("agreement_score"),
        "dominant_cross_root": sr.get("dominant_cross_root"),
        "cyclic_state": sr.get("cyclic_axis_state"),
        "animal_profile": extract_animal_profile(data),
        "planetary_profile": extract_planetary_profile(data),
    }


# ── Ground truth extraction ──────────────────────────────────────────────────

def build_ground_truth(data: dict) -> str:
    """Build an explicit GROUND TRUTH block from engine output.
    
    This block is injected into Claude's user message to prevent
    hallucination of dominant roots, convergence counts, or core numbers.
    Claude MUST use these values — it cannot infer or override them.
    """
    synth = data.get("synthesis", {})
    profile = data.get("profile", {})
    sr = data.get("semantic_reading", {})
    core = profile.get("core_numbers", {})
    
    # Ranked convergences
    nc = synth.get("number_convergences", [])
    ranked = sorted(nc, key=lambda x: (-x.get("system_count", 0), -x.get("group_count", 0)))
    
    # Dominant root
    dom = ranked[0] if ranked else {"number": "?", "system_count": 0, "group_count": 0}
    
    # Convergence table
    conv_table = "\n".join(
        f"  Root {c['number']}: {c['system_count']} systems, {c['group_count']} groups"
        for c in ranked[:8]
    )
    
    # Semantic axes
    axes = sr.get("sections", [])
    axes_table = "\n".join(
        f"  {s.get('axis', '?')}: Root {s.get('dominant_root', '?')}"
        for s in axes
    )
    
    # Core numbers
    lp = core.get("life_path", "?")
    expr = core.get("expression", "?")
    su = core.get("soul_urge", "?")
    pers = core.get("personality", "?")
    bday = core.get("birthday", "?")
    abjad_first = core.get("abjad_first", "?")
    
    # Karmic debt
    results = data.get("results", [])
    karmic = {}
    for r in results:
        if r.get("id") == "karmic_debt":
            karmic = r.get("data", {})
            break
    kd_found = karmic.get("karmic_debts_found", {})
    if kd_found:
        kd_lines = "\n".join(
            f"  {pos}: KD {info['number']} — {info['meaning']}"
            for pos, info in kd_found.items()
        )
    else:
        kd_lines = "  None"

    # Tarot cards
    tarot_birth = {}
    tarot_name = {}
    for r in results:
        if r.get("id") == "tarot_birth":
            tarot_birth = r.get("data", {})
        elif r.get("id") == "tarot_name":
            tarot_name = r.get("data", {})

    # Meta patterns
    meta = sr.get("meta_patterns_fired", [])
    fired = [p.get("pattern_id", "") for p in meta if p.get("fired")]

    # Animal & element signature
    animal = extract_animal_profile(data)
    animal_block = build_animal_ground_truth(animal)

    # Planetary signature
    planet = extract_planetary_profile(data)
    planet_block = build_planetary_ground_truth(planet)

    return f"""
=== GROUND TRUTH — DO NOT OVERRIDE ===
These values are computed by the deterministic engine. You MUST use them.
Do NOT infer a different dominant root. Do NOT invent convergence patterns.

DOMINANT ROOT: Root {dom['number']} ({dom['system_count']} systems across {dom['group_count']} independence groups)
This MUST be the subject of Card 1 (The Dominant Thread).

CONVERGENCE HIERARCHY (ranked by system count, then group breadth):
{conv_table}

CORE NUMBERS:
  Life Path: {lp}
  Expression: {expr}
  Soul Urge: {su}
  Personality: {pers}
  Birthday: {bday}
  Abjad (first name): {abjad_first}

KARMIC DEBT:
{kd_lines}
{"If karmic debt exists, it MUST be mentioned in the reading. KD 16 = Tower archetype." if kd_found else ""}

TAROT BIRTH CARDS: {tarot_birth.get('pair', 'unknown')}
TAROT NAME (Expression): {tarot_name.get('expression_card_name', 'unknown')}
TAROT NAME (Soul): {tarot_name.get('soul_card_name', 'unknown')}

SEMANTIC AXIS DOMINANTS:
{axes_table}

META PATTERNS FIRED: {', '.join(fired) if fired else 'none'}
{animal_block}
{planet_block}
TOTAL CONVERGENCES: {synth.get('convergence_count', '?')}

VALIDATION: Before returning, verify:
1. Card 1 discusses Root {dom['number']} as dominant (NOT any other root)
2. Core numbers match the values above
3. No claims contradict the convergence hierarchy
4. Convergence count matches {synth.get('convergence_count', '?')}
=== END GROUND TRUTH ===
"""


# ── API call ─────────────────────────────────────────────────────────────────

def generate_reading(output_path: str, lang: str = "en") -> str:
    """Generate a narrative reading from an engine output file."""
    # Load output
    data = json.loads(Path(output_path).read_text(encoding="utf-8"))
    context = extract_reading_context(data)

    # Language
    lang_name = "English" if lang == "en" else "Arabic"

    # Build the system prompt
    system = SYSTEM_PROMPT.replace("{lang_name}", lang_name)

    # Build the user message with the extracted context
    ground_truth = build_ground_truth(data)
    user_msg = f"""Generate a SIRR reading for this person.

{ground_truth}

## Profile Data
```json
{json.dumps(context, ensure_ascii=False, indent=2, default=str)}
```

Write the complete reading now. Language: {lang_name}.
"""

    # Call Claude API
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    # P2F-PR3 §B.1: drop subject (user's name) from log line. Keep
    # operational signal (language) without the PII tail.
    print(f"  Generating {lang_name} reading...")
    print(f"  Sending to Claude API...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    reading = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost_est = (tokens_in * 3.0 / 1_000_000) + (tokens_out * 15.0 / 1_000_000)

    print(f"  Done. {tokens_out} tokens generated.")
    print(f"  Estimated cost: ${cost_est:.4f}")

    # Inject the locked three-tier Convergence Point block (SHORT / MEDIUM / LONG)
    # at the top of the reading, selected by name_length_tier.
    reading = inject_convergence_point(reading, data)

    tier = _extract_name_length_tier(data)
    if tier:
        print(f"  Convergence Point: {tier.upper()} tier block injected.")

    return reading


# ── Output ───────────────────────────────────────────────────────────────────

def generate_dashboard_panels(output_path: str, lang: str = "en") -> dict:
    """Generate 6 JSON reading panels for the dashboard format."""
    data = json.loads(Path(output_path).read_text(encoding="utf-8"))
    context = extract_reading_context(data)
    lang_name = "English" if lang == "en" else "Arabic"

    user_msg = f"""Generate a SIRR dashboard reading for this person.

{build_ground_truth(data)}

## Profile Data
```json
{json.dumps(context, ensure_ascii=False, indent=2, default=str)}
```

Return ONLY the JSON. Language: {lang_name}.
"""
    client = anthropic.Anthropic()
    # P2F-PR3 §B.1: drop subject (user's name) from log line.
    print(f"  Generating dashboard panels...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT_DASHBOARD,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    # Strip any accidental markdown fencing
    text = text.replace("```json", "").replace("```", "").strip()
    tokens_out = response.usage.output_tokens
    cost = (response.usage.input_tokens * 3.0 + tokens_out * 15.0) / 1_000_000
    print(f"  Done. {tokens_out} tokens. Cost: ${cost:.4f}")
    return json.loads(text)


def save_dashboard_panels(panels: dict, output_path: str, lang: str = "en") -> str:
    """Save panel JSON alongside the engine output."""
    base = Path(output_path).stem
    panels_path = Path(output_path).parent / f"{base}_panels_{lang}.json"
    panels_path.write_text(json.dumps(panels, ensure_ascii=False, indent=2), encoding="utf-8")
    # P2F-PR3 §B exemption: this file is invoked as a standalone CLI
    # (`python reading_generator.py output.json`) for engine devs; the
    # path it prints is operator console output, not a server runtime
    # log ingested by Railway/Datadog. Out-of-scope for the hash_oid
    # scrub. If/when this surface starts emitting to a real log
    # aggregator, scrub it then.
    print(f"  Saved panels: {panels_path}")
    return str(panels_path)



def save_reading(reading: str, output_path: str, lang: str = "en") -> str:
    """Save the reading to a text file alongside the output JSON."""
    base = Path(output_path).stem
    reading_path = Path(output_path).parent / f"{base}_reading_{lang}.md"
    reading_path.write_text(reading, encoding="utf-8")
    # P2F-PR3 §B exemption: standalone CLI output (see panels above).
    print(f"  Saved: {reading_path}")
    return str(reading_path)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Defaults
    output_path = "output.json"
    lang = "en"

    # Parse args
    for i, arg in enumerate(args):
        if arg == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
        elif arg.endswith(".json"):
            output_path = arg

    if not Path(output_path).exists():
        # P2F-PR3 §B exemption: CLI usage error message — operator's own
        # path on their own terminal, not a server runtime log.
        print(f"  Error: {output_path} not found")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Error: ANTHROPIC_API_KEY not set")
        print("  Export your key: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    reading = generate_reading(output_path, lang)
    save_reading(reading, output_path, lang)

    # Print preview
    print(f"\n{'='*60}")
    print(f"  READING PREVIEW (first 500 chars)")
    print(f"{'='*60}")
    print(reading[:500])
    print("...")


if __name__ == "__main__":
    main()
