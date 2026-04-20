"""Challenge Cycles — COMPUTED_STRICT"""
from __future__ import annotations
from sirr_core.types import InputProfile, SystemResult
from sirr_core.utils import reduce_number

def compute(profile: InputProfile, constants: dict) -> SystemResult:
    # Challenge cycle inputs: month, day, year reduced to single digits.
    # Juno Jordan / Florence Campbell methodology operates on 1-9 components
    # so the resulting challenges (computed as absolute differences) are
    # always 0-9. Master numbers (11, 22, 33) do NOT appear in challenge
    # analysis under this tradition — they're an LP/Expression concept.
    # Hence keep_masters=() here is intentional, not a regression.
    m = reduce_number(profile.dob.month, keep_masters=())
    d = reduce_number(profile.dob.day, keep_masters=())
    y = reduce_number(profile.dob.year, keep_masters=())

    c1 = abs(m - d)
    c2 = abs(d - y)
    c3 = abs(c1 - c2)
    c4 = abs(m - y)

    meanings = {
        0: "All-or-nothing; must find own way",
        1: "Independence vs dependence",
        2: "Partnership, patience, diplomacy",
        3: "Self-expression, scattered energy",
        4: "Discipline, structure, foundation",
        5: "Freedom vs responsibility",
        6: "Domestic duty, perfectionism",
        7: "Faith vs doubt, isolation",
        8: "Power, money, authority issues",
    }

    return SystemResult(
        id="challenges",
        name="Challenge Cycles (4)",
        certainty="COMPUTED_STRICT",
        data={
            "components": f"M={m}, D={d}, Y={y}",
            "challenge_1": c1, "challenge_1_ages": "0-33",
            "challenge_1_meaning": meanings.get(c1, ""),
            "challenge_2": c2, "challenge_2_ages": "34-42",
            "challenge_2_meaning": meanings.get(c2, ""),
            "challenge_3": c3, "challenge_3_ages": "43-51",
            "challenge_3_meaning": meanings.get(c3, ""),
            "challenge_4": c4, "challenge_4_ages": "52+",
            "challenge_4_meaning": meanings.get(c4, ""),
            "lifelong_pattern": c4 == c2 == c3,
            "repeated_number": c2 if c2 == c3 == c4 else None
        },
        interpretation=None,
        constants_version=constants["version"],
        references=["Standard numerological challenge cycle formula",
                    "SOURCE_TIER:C — Modern system. Algorithms popularized by Juno Jordan, Florence Campbell (20th c.). No classical Pythagorean textual algorithm documented."],
        question="Q6_GROWTH"
    )
