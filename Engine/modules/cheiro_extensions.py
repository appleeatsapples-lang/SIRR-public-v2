"""Cheiro Extensions (Compound Number + Color Affinity) — LOOKUP_FIXED
Compound Number: Chaldean name total → lookup in Cheiro's 10-52 meaning table.
Color Affinity: Life Path → primary/secondary/avoid color associations.
Source: Cheiro, "Book of Numbers" (1926)
"""
from __future__ import annotations
from sirr_core.types import InputProfile, SystemResult
from sirr_core.utils import reduce_number

# Chaldean letter values (same as chaldean.py)
CHALDEAN = {
    'A': 1, 'I': 1, 'J': 1, 'Q': 1, 'Y': 1,
    'B': 2, 'K': 2, 'R': 2,
    'C': 3, 'G': 3, 'L': 3, 'S': 3,
    'D': 4, 'M': 4, 'T': 4,
    'E': 5, 'H': 5, 'N': 5, 'X': 5,
    'U': 6, 'V': 6, 'W': 6,
    'O': 7, 'Z': 7,
    'F': 8, 'P': 8,
}

# Cheiro's Compound Number meanings (10-52)
COMPOUND_MEANINGS = {
    10: {"name": "Wheel of Fortune", "nature": "fortunate", "keywords": "honor, faith, rise and fall"},
    11: {"name": "The Clenched Fist", "nature": "warning", "keywords": "hidden dangers, treachery, trials"},
    12: {"name": "The Sacrifice", "nature": "warning", "keywords": "suffering, anxiety, sacrifice for others"},
    13: {"name": "Transformation", "nature": "powerful", "keywords": "upheaval, destruction and rebuilding, power"},
    14: {"name": "Movement", "nature": "fortunate", "keywords": "change, travel, risk, magnetic communication"},
    15: {"name": "The Magician", "nature": "fortunate", "keywords": "eloquence, gifts of speech, music, art"},
    16: {"name": "The Shattered Citadel", "nature": "warning", "keywords": "accidents, defeat, strange fatality"},
    17: {"name": "The Star of the Magi", "nature": "highly fortunate", "keywords": "immortality, rise to fame, spiritual insight"},
    18: {"name": "Spiritual-Material Conflict", "nature": "difficult", "keywords": "quarrels, war, deception, bitter enemies"},
    19: {"name": "The Prince of Heaven", "nature": "highly fortunate", "keywords": "success, esteem, honor, happiness"},
    20: {"name": "The Awakening", "nature": "fortunate", "keywords": "purpose found late, call to action, new plans"},
    21: {"name": "The Crown of the Magi", "nature": "highly fortunate", "keywords": "advancement, elevation, triumph, victory"},
    22: {"name": "Submission and Caution", "nature": "warning", "keywords": "illusion, false judgment, living in a fool's paradise"},
    23: {"name": "The Royal Star of the Lion", "nature": "highly fortunate", "keywords": "success, help from superiors, protection"},
    24: {"name": "Love and Creative Power", "nature": "fortunate", "keywords": "love, assistance from opposite sex, creative gifts"},
    25: {"name": "Strength through Trial", "nature": "fortunate", "keywords": "strength gained through experience, observation"},
    26: {"name": "Partnerships", "nature": "warning", "keywords": "gravest warnings for the future, losses through partnerships"},
    27: {"name": "The Sceptre", "nature": "fortunate", "keywords": "command, authority, reward, courage"},
    28: {"name": "The Trusting Lamb", "nature": "contradictory", "keywords": "great promise then loss, opposition, ruin if not careful"},
    29: {"name": "Grace Under Pressure", "nature": "uncertain", "keywords": "uncertainties, treachery, unreliable friends"},
    30: {"name": "The Lure of the Intellectual", "nature": "neutral", "keywords": "mental superiority, retrospection, self-analysis"},
    31: {"name": "The Recluse", "nature": "isolating", "keywords": "loneliness, isolation from others, self-contained"},
    32: {"name": "Communication", "nature": "fortunate", "keywords": "magical power of words, charm, personal magnetism"},
    33: {"name": "Power and Restriction", "nature": "challenging", "keywords": "force without wisdom, domination"},
    34: {"name": "Struggle and Suffering", "nature": "difficult", "keywords": "suffering through others, self-sacrifice"},
    35: {"name": "Cautious Action", "nature": "neutral", "keywords": "slow but steady progress, careful planning"},
    36: {"name": "Dynamic Force", "nature": "powerful", "keywords": "struggle for humanitarian ideals, mental brilliance"},
    37: {"name": "Creative Power", "nature": "fortunate", "keywords": "good partnerships, love, friendship, creativity"},
    38: {"name": "Harsh Reality", "nature": "difficult", "keywords": "same as 29 but intensified, treachery, deception"},
    39: {"name": "Success and Versatility", "nature": "fortunate", "keywords": "same as 30 but more favorable"},
    40: {"name": "Reliable Planning", "nature": "neutral", "keywords": "same as 31, organized, methodical"},
    41: {"name": "Ambition Realized", "nature": "fortunate", "keywords": "same as 32, powerful expression"},
    42: {"name": "Self-Delusion", "nature": "warning", "keywords": "same as 24 reversed, misplaced trust"},
    43: {"name": "Revolution", "nature": "warning", "keywords": "same as 34, failure, upheaval"},
    44: {"name": "Hidden Power", "nature": "powerful", "keywords": "same as 26 but with occult strength"},
    45: {"name": "Accumulated Wisdom", "nature": "fortunate", "keywords": "same as 27, leadership, authority"},
    46: {"name": "Abundance", "nature": "fortunate", "keywords": "same as 37, great success possible"},
    47: {"name": "Crowned Success", "nature": "fortunate", "keywords": "same as 29 but better outcome, fortune after difficulty"},
    48: {"name": "Counselor and Advisor", "nature": "neutral", "keywords": "same as 30, mental gifts, analysis"},
    49: {"name": "Transformation and Change", "nature": "powerful", "keywords": "same as 31, dramatic life changes"},
    50: {"name": "Cosmic Communication", "nature": "neutral", "keywords": "same as 32, powerful speakers, orators"},
    51: {"name": "The Warrior", "nature": "powerful", "keywords": "same as 33, strength in adversity"},
    52: {"name": "The Magician Ascended", "nature": "highly fortunate", "keywords": "same as 43 reversed, triumph"},
}

# Cheiro's color affinities by number (1-9)
COLOR_TABLE = {
    1: {"primary": ["Red", "Orange", "Gold"], "secondary": ["Copper", "Yellow"], "avoid": ["Black", "Dark Blue"]},
    2: {"primary": ["Green", "Cream", "White"], "secondary": ["Light Blue"], "avoid": ["Dark Red", "Black"]},
    3: {"primary": ["Purple", "Violet", "Mauve"], "secondary": ["Lilac", "Cherry Red"], "avoid": []},
    4: {"primary": ["Blue", "Gray", "Silver"], "secondary": ["Electric Blue"], "avoid": []},
    5: {"primary": ["Light Gray", "Silver", "Platinum"], "secondary": ["White", "Glistening"], "avoid": ["Dark Brown"]},
    6: {"primary": ["Blue", "Rose Pink", "Turquoise"], "secondary": ["All shades of blue"], "avoid": []},
    7: {"primary": ["Green", "Yellow", "White"], "secondary": ["Pale shades"], "avoid": ["Dark", "Heavy colors"]},
    8: {"primary": ["Dark Gray", "Blue", "Purple", "Black"], "secondary": ["Dark tones"], "avoid": []},
    9: {"primary": ["Red", "Crimson", "Rose Pink"], "secondary": ["Scarlet", "Warm tones"], "avoid": []},
}


def _chaldean_total(name: str) -> int:
    return sum(CHALDEAN.get(c, 0) for c in name.upper() if c in CHALDEAN)


def _reduce_to_range(n: int, lo: int, hi: int) -> int:
    """Reduce digit-by-digit until in [lo, hi] range."""
    while n > hi:
        n = sum(int(d) for d in str(n))
    return n


def compute(profile: InputProfile, constants: dict, **kwargs) -> SystemResult:
    # ── Compound Number ──
    chal_total = _chaldean_total(profile.subject)
    compound = _reduce_to_range(chal_total, 10, 52) if chal_total >= 10 else chal_total
    # compound_root is the single-digit COMPANION to `compound`. `compound`
    # already preserves Cheiro's characteristic 10-52 range (which includes
    # 11/22/33 implicitly). This companion is intentionally collapsed to 1-9
    # for table lookup — not a master-number regression.
    compound_root = reduce_number(compound, keep_masters=())

    meaning = COMPOUND_MEANINGS.get(compound, {"name": "Unknown", "nature": "unknown", "keywords": ""})

    # ── Color Affinity ──
    # Life Path is the master-number-sensitive number in Pythagorean numerology.
    # Cheiro explicitly preserved 11/22/33 at the LP level. If the profile
    # doesn't carry a pre-computed life_path, compute one that respects masters.
    lp = profile.life_path or reduce_number(
        reduce_number(profile.dob.month, keep_masters=(11, 22, 33)) +
        reduce_number(profile.dob.day, keep_masters=(11, 22, 33)) +
        reduce_number(sum(int(x) for x in str(profile.dob.year)), keep_masters=(11, 22, 33)),
        keep_masters=(11, 22, 33)
    )
    # Color lookup table is indexed 1-9, so collapse master LP here — again
    # a companion value, not a master-number-preservation regression.
    color_key = lp if 1 <= lp <= 9 else reduce_number(lp, keep_masters=())
    colors = COLOR_TABLE.get(color_key, {"primary": [], "secondary": [], "avoid": []})

    return SystemResult(
        id="cheiro_extensions",
        name="Cheiro Extensions (Compound Number + Color)",
        certainty="LOOKUP_FIXED",
        data={
            "chaldean_total": chal_total,
            "compound_number": compound,
            "compound_root": compound_root,
            "compound_name": meaning["name"],
            "compound_nature": meaning["nature"],
            "compound_keywords": meaning["keywords"],
            "color_key_number": color_key,
            "color_primary": colors["primary"],
            "color_secondary": colors["secondary"],
            "color_avoid": colors["avoid"],
        },
        interpretation=None,
        constants_version=constants["version"],
        references=[
            "Cheiro, 'Book of Numbers' (1926): Compound number meanings 10-52",
            "Cheiro, 'Book of Numbers': Color affinity by birth number",
            "SOURCE_TIER:B — Historical Chaldean tradition systematized by Cheiro (Count Louis Hamon).",
        ],
        question="Q1_IDENTITY",
    )
