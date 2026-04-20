"""Life Purpose / Birth Number — COMPUTED_STRICT
Some numerologists distinguish Birth Day Number (just the day digit)
from Life Path (full DOB reduction). This module computes the pure
birth day reduction + the 'life purpose' interpretation axis.
Source: Dan Millman, The Life You Were Born to Live
"""
from __future__ import annotations
from sirr_core.types import InputProfile, SystemResult
from sirr_core.utils import reduce_number

def compute(profile: InputProfile, constants: dict) -> SystemResult:
    day = profile.dob.day
    # Birth-day reduction preserves 11 and 22 per Millman's documented
    # methodology (notation like "11/2", "22/4"). 33 is typically not
    # surfaced at the birth-day level in this system.
    reduced = reduce_number(day, keep_masters=(11, 22))

    # Millman compound: keep 2-digit form before final reduction
    compound = day if day > 9 else day
    digits = [int(d) for d in str(profile.dob.year)] + [profile.dob.month, profile.dob.day]
    millman_sum = sum(digits)
    # Keep as 2-digit "life purpose number"
    millman_lp = millman_sum if millman_sum > 9 else millman_sum

    return SystemResult(
        id="life_purpose", name="Life Purpose / Birth Day Number",
        certainty="COMPUTED_STRICT",
        data={
            "birth_day": day,
            "birth_day_reduced": reduced,
            "millman_raw": millman_sum,
            "millman_compound": millman_lp,
            # millman_final is the single-digit COMPANION to millman_compound
            # (which already preserves the 2-digit form). Intentionally
            # collapsed for downstream single-digit consumers — not a
            # master-number regression; the full compound is still present.
            "millman_final": reduce_number(millman_sum, keep_masters=()),
        },
        interpretation=None, constants_version=constants["version"],
        references=["Dan Millman life purpose system + standard birth day numerology",
                    "SOURCE_TIER:C — Modern system. Algorithms popularized by Juno Jordan, Florence Campbell (20th c.). No classical Pythagorean textual algorithm documented."],
        question="Q1_IDENTITY"
    )
