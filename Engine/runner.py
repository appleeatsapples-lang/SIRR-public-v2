"""
SIRR v2 New Systems Runner
Orchestrates all 52 modules + synthesis + ledger
"""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

from sirr_core.module_taxonomy import apply_taxonomy
from sirr_core.types import InputProfile, SystemResult
from sirr_core.utils import date_to_iso
from sirr_core.ledger import add_ledger_entry
from sirr_core.render import render_terminal, render_ledger
from interpretation_loader import InterpretationLoader, _format_interp, _flatten_data
try:
    from translation_layer import build_psychological_mirror
    _TRANSLATION_LAYER_AVAILABLE = True
except ImportError:
    _TRANSLATION_LAYER_AVAILABLE = False
try:
    from psych_layer import build_psychological_profile
    _PSYCH_LAYER_AVAILABLE = True
except ImportError:
    _PSYCH_LAYER_AVAILABLE = False
from modules.narrative import compute_narrative

# Semantic reading layer
from axis_reducer import reduce_axes, signals_to_dict, load_taxonomy
from inter_axis_synthesizer import synthesize_across_axes, resonance_to_dict
from activation_detector import activation_layer
from meta_pattern_detector import detect_all as detect_meta_patterns
from combination_engine import compute_tag_overlap
from reading_composer import compose_reading

from modules import (
    julian, biorhythm, mayan, geomancy, iching, wafq, essence, cardology,
    nayin, compound, sabian, challenges, bridges, attitude, profection,
    firdaria, notarikon, atbash, albam, temperament, bazi_growth,
    vedic_tithi, vedic_yoga, synthesis,
    # Batch 1: Pure math expansion
    pinnacles, personal_year, karmic_debt, lo_shu_grid,
    hidden_passion, subconscious_self, maturity,
    # Batch 2: Arabic expansion
    abjad_kabir, abjad_saghir, abjad_wusta, abjad_maghribi, hijri,
    solar_lunar, elemental_letters, luminous_dark,
    # Batch 3: Astrology expansion
    decan, day_ruler, tarot_birth, dwad,
    # Batch 5: Hebrew/Kabbalistic expansion
    hebrew_gematria, avgad, tree_of_life, hebrew_calendar,
    # Batch 6: Chinese expansion
    chinese_zodiac, nine_star_ki, flying_star, bazi_pillars,
    # Batch 7: Vedic + Arabic lunar
    nakshatra, manazil, vimshottari,
    # Phase 2: Dimensional expansion
    chaldean, ifa, egyptian_decan,
    # Batch 8: Islamic Ilm al-Huruf
    taksir, bast_kasr, istikhara_adad, zakat_huruf, jafr, buduh,
    # Batch 9: Quick wins
    cornerstone, life_purpose, steiner_cycles, enneagram_dob,
    tarot_year, tarot_name, latin_ordinal,
    # Mandaean gematria
    mandaean_gematria,
    # Batch 10: Gematria battery
    greek_isopsephy, coptic_isopsephy, armenian_gematria,
    georgian_gematria, agrippan, thelemic_gematria, trithemius,
    # Batch 11: Calendar systems
    planetary_hours, god_of_day, celtic_tree, ogham, birth_rune,
    # Batch 12: BaZi sub-layers
    bazi_daymaster, bazi_luck_pillars, bazi_hidden_stems, bazi_ten_gods, bazi_combos, bazi_shensha,
    # Batch 13: Additional P1 systems
    bazhai, meihua, pawukon, primbon, tibetan_mewa,
    dreamspell, tonalpohualli, ethiopian_asmat,
    rose_cross_sigil, planetary_kameas, ars_magna,
    gd_correspondences,
    # Module 110-111: Southeast Asian + Hellenistic expansion
    weton, planetary_joy,
    # Module 112-113: Akan + Persian
    akan_kra_din, persian_abjad,
    # Ephemeris Phase 1: Foundation
    natal_chart, house_system, aspects,
    # Ephemeris Phase 2: High-value systems
    essential_dignities, sect, arabic_parts,
    solar_return, progressions, fixed_stars,
    # Module 114-116: Antiscia + Vedic dashas
    antiscia, yogini_dasha, ashtottari_dasha,
    # Module 117-118: Birth-time-gated systems
    zi_wei_dou_shu, shadbala,
    # Module 119-130: Ephemeris Phase 3 expansion
    almuten, reception, declinations, midpoints, harmonic_charts,
    zodiacal_releasing, solar_arc, dorothean_chronocrators,
    ashtakavarga, shodashavarga, tasyir, kalachakra_dasha,
    # Batch 18a: Hellenistic + Islamic + Chinese
    bonification, zairja, qimen, liu_ren,
    # Batch 18b: Hellenistic + Vedic + Indo-Persian
    primary_directions, chara_dasha, sarvatobhadra, tajika, kp_system,
    # Batch 19: San Shi completion + Japanese + Hamburg School
    taiyi, onmyodo, uranian,
    # Batch 20: Vedic micro-division + Polynesian lunar
    nadi_amsa, maramataka,
    # Batch 21a: Babylonian sidereal
    babylonian_horoscope,
    # Batch 21b: Vedic triple-wheel timing
    sudarshana,
    # Round 2: Southeast Asian + Human Design + Gene Keys
    mahabote, human_design, gene_keys,
    # Round 2b: Mandaean baptismal oracle
    malwasha,
)
from modules import prashna_natal
from modules import rectification
from modules import horary_timing
from modules import jaimini_karakas, jaimini_argala, jaimini_navamsha
from modules import astrocartography
from modules import kp_sublords
from modules import draconic_chart
from modules import solar_return_deep
from modules import electional_windows
from modules import muhurta
from modules import synastry
from modules import quranic_figures
from modules import torah_figures, nt_figures, cross_scripture
from modules import arabic_roots, arabic_morphology, name_semantics, arabic_phonetics, arabic_letter_nature
from modules import digit_patterns, lineage_computation, hijri_calendar_encoding
from modules import calligraphy_structure, divine_breath, letter_position_encoding
from modules import abjad_visual_architecture, name_weight, arabic_rhetoric, sonority_curve
from modules import larger_awfaq, qibla_as_axis, prayer_times_as_timing, chronobiology
from modules import void_matrix, barzakh_coefficient, hermetic_alignment
from modules import execution_pattern_analysis, minimum_viable_signature
# Round 4: Cross-tradition expansion (20 modules)
from modules import kala_sarpa_check, panchamahabhuta, ayurvedic_constitution
from modules import mantra_seed_syllable, vedic_gem_prescription
from modules import bazi_10_year_forecast, zi_wei_deeper, four_pillars_balance
from modules import gematria_word_matches, sephirotic_path_analysis, solomonic_correspondences
from modules import african_day_name_extended, enneagram_deeper, hermetic_element_balance
from modules import circadian_medicine, seasonal_psychology
from modules import element_consensus, timing_consensus, planetary_ruler_consensus, archetype_consensus
# Round 5 Wave 1: Decoz layer
from modules import balance_number, rational_thought, inclusion_table, special_letters
from modules import period_cycles, transit_letters, yearly_essence_cycle, minor_numbers
# Round 5 Wave 2: Tarot + Esoteric + Hellenistic
from modules import tarot_greer_birth_cards, greer_zodiac_card, prenatal_syzygy
from modules import cheiro_extensions, roman_chronogram, hebrew_aiq_beker
# Round 5 Wave 3: Cross-tradition
from modules import tibetan_parkha, tibetan_elements, tamil_panchapakshi
from modules import chinese_jian_chu, igbo_market_day, zoroastrian_day_yazata
from modules import vedic_arudha_pada, vedic_upapada_lagna, vedic_pushkara_navamsha
from modules import bazi_san_he_san_hui, zwds_si_hua_palace, hebrew_mispar_variants
# Round 5 Wave 4: Planes of Expression
from modules import planes_of_expression

def load_constants(path: str = None) -> dict:
    if path is None:
        path = str(Path(__file__).parent / "constants.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reduce_core(n: int) -> int:
    """Reduce to single digit or master number (11, 22, 33)."""
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


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


def load_profile(path: str = None) -> InputProfile:
    """Load from fixture or fall back to the synthetic FATIMA demo profile."""
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        dob = date.fromisoformat(data["dob"])
        # Auto-compute core numbers if not provided in fixture
        core = _compute_core_numbers(data["subject"], dob)
        # Auto-transliterate Arabic name if not provided
        arabic_name = data.get("arabic", "").strip()
        if not arabic_name:
            from modules.transliterate import transliterate_to_arabic
            arabic_name = transliterate_to_arabic(data["subject"])
            print(f"  [runner] Arabic auto-transliterated from '{data['subject']}' → '{arabic_name}'")
        # Compute abjad_first from Arabic first name if not provided
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

    # Default: synthetic FATIMA AHMED OMAR ALKATIB — public demo profile
    default_fixture = Path(__file__).parent / "fixtures" / "synthetic_profile.json"
    if default_fixture.exists():
        return load_profile(str(default_fixture))
    # Fallback hardcoded (should never reach here if fixtures/ exists)
    constants = load_constants()
    subject = "FATIMA AHMED OMAR ALKATIB"
    arabic = "فاطمة أحمد عمر الكاتب"
    dob = date(1990, 3, 15)
    core = _compute_core_numbers(subject, dob)
    abjad_table = constants["arabic_letters"]["abjad_kabir"]
    abjad_first = sum(abjad_table.get(ch, 0) for ch in "فاطمة")
    return InputProfile(
        subject=subject,
        arabic=arabic,
        dob=dob,
        today=date.today(),
        birth_time_local="14:22",
        timezone="Africa/Cairo",
        location="Cairo, Egypt",
        life_path=core["life_path"],
        expression=core["expression"],
        soul_urge=core["soul_urge"],
        personality=core["personality"],
        birthday_number=core["birthday_number"],
        abjad_first=abjad_first,
        gender="female",
        variant="full_legal",
        mother_name="MARYAM SALIM YUSUF HASSAN",
        mother_name_ar="مريم سليم يوسف حسن",
        mother_dob="1962-05-20",
    )


def system_run(profile_path: str = None, natal_chart_data: dict = None, output_path_override: str = None):
    constants = load_constants()
    profile = load_profile(profile_path)

    results = []
    ledger = []

    # ── 1. Julian Day Number (infrastructure) ──
    r_jdn = julian.compute(profile, constants)
    results.append(r_jdn)
    jdn = int(r_jdn.data["jdn"])

    # ── 2. Biorhythm ──
    results.append(biorhythm.compute(profile, constants))

    # ── 3. Mayan (correlation-dependent) ──
    r_mayan = mayan.compute(profile, constants, jdn=jdn)
    results.append(r_mayan)

    # G-Lord now verified: G7 Tlazolteotl (Purification)
    # Formula: (total_kin % 9), verified against 13.0.0.0.0 → G9
    # Previous G6 claim was narrative confabulation (Grok, Feb 2026)

    # ── 4. Geomancy ──
    results.append(geomancy.compute(profile, constants, jdn=jdn))

    # ── 5. I Ching ──
    results.append(iching.compute(profile, constants))

    # ── 6. Wafq ──
    results.append(wafq.compute(profile, constants, base_number=profile.abjad_first or 48))

    # ── 7. Essence Cycle ──
    age = profile.today.year - profile.dob.year
    if (profile.today.month, profile.today.day) < (profile.dob.month, profile.dob.day):
        age -= 1
    results.append(essence.compute(profile, constants, age=age))

    # ── 8. Cardology ──
    results.append(cardology.compute(profile, constants))

    # ── 9. NaYin ──
    results.append(nayin.compute(profile, constants))

    # ── 10. Compound Numbers ──
    results.append(compound.compute(profile, constants))

    # ── 11. Sabian Symbol ──
    results.append(sabian.compute(profile, constants))

    # ── 12. Challenge Cycles ──
    results.append(challenges.compute(profile, constants))

    # ── 13. Bridge Numbers ──
    results.append(bridges.compute(profile, constants))

    # ── 14. Attitude Number ──
    results.append(attitude.compute(profile, constants))

    # ── 15. Annual Profection ──
    results.append(profection.compute(profile, constants))

    # ── 16. Firdaria ──
    results.append(firdaria.compute(profile, constants))

    # ── 17. Notarikon ──
    results.append(notarikon.compute(profile, constants))

    # ── 18. AtBash ──
    results.append(atbash.compute(profile, constants))

    # ── 19. Albam ──
    results.append(albam.compute(profile, constants))

    # ── 20. Temperament — deferred to post-natal (see below line 571) ──

    # ── 21. BaZi Growth Phases ──
    results.append(bazi_growth.compute(profile, constants))

    # ── 22. Vedic Tithi (approximate) ──
    results.append(vedic_tithi.compute(profile, constants))

    # ── 23. Vedic Yoga (approximate) ──
    results.append(vedic_yoga.compute(profile, constants))

    # ── 24. Pinnacle Cycles ──
    results.append(pinnacles.compute(profile, constants))

    # ── 25. Personal Year / Month / Day ──
    results.append(personal_year.compute(profile, constants))

    # ── 26. Karmic Debt ──
    results.append(karmic_debt.compute(profile, constants))

    # ── 27. Lo Shu Birth Grid ──
    results.append(lo_shu_grid.compute(profile, constants))

    # ── 28. Hidden Passion ──
    results.append(hidden_passion.compute(profile, constants))

    # ── 29. Subconscious Self ──
    results.append(subconscious_self.compute(profile, constants))

    # ── 30. Maturity Number ──
    results.append(maturity.compute(profile, constants))

    # ── 31. Abjad Kabir (Full Name) ──
    results.append(abjad_kabir.compute(profile, constants))

    # ── 32. Abjad Saghir ──
    results.append(abjad_saghir.compute(profile, constants))

    # ── 33. Abjad Wusta ──
    results.append(abjad_wusta.compute(profile, constants))

    # ── 33b. Abjad Maghribi (North African) ──
    results.append(abjad_maghribi.compute(profile, constants))

    # ── 34. Hijri Calendar ──
    results.append(hijri.compute(profile, constants))

    # ── 35. Solar/Lunar Letters ──
    results.append(solar_lunar.compute(profile, constants))

    # ── 36. Elemental Letters ──
    results.append(elemental_letters.compute(profile, constants))

    # ── 37. Luminous/Dark Letters ──
    results.append(luminous_dark.compute(profile, constants))

    # ── 38. Decan ──
    results.append(decan.compute(profile, constants))

    # ── 39. Day of Week Ruler ──
    results.append(day_ruler.compute(profile, constants))

    # ── 40. Tarot Birth Cards ──
    results.append(tarot_birth.compute(profile, constants))

    # ── 41. Zodiac Dwad ──
    results.append(dwad.compute(profile, constants))

    # ── 42. Hebrew Gematria ──
    results.append(hebrew_gematria.compute(profile, constants))

    # ── 42b. Mandaean Gematria ──
    results.append(mandaean_gematria.compute(profile, constants))

    # ── 43. Temurah Avgad ──
    results.append(avgad.compute(profile, constants))

    # ── 44. Tree of Life Path ──
    results.append(tree_of_life.compute(profile, constants))

    # ── 45. Hebrew Calendar ──
    results.append(hebrew_calendar.compute(profile, constants))

    # ── 46. Chinese Zodiac (Full) ──
    results.append(chinese_zodiac.compute(profile, constants))

    # ── 47. Nine Star Ki ──
    results.append(nine_star_ki.compute(profile, constants))

    # ── 48. Flying Star Feng Shui ──
    results.append(flying_star.compute(profile, constants))

    # ── 49. BaZi Four Pillars ──
    r_bazi = bazi_pillars.compute(profile, constants, jdn=jdn)
    results.append(r_bazi)
    bazi_data = r_bazi.data  # Capture for sub-modules

    # ── 50. Nakshatra (Vedic Lunar Mansion) ──
    results.append(nakshatra.compute(profile, constants))

    # ── 51. Manazil al-Qamar (Arabic Lunar Mansions) ──
    results.append(manazil.compute(profile, constants))

    # ── 52. Vimshottari Dasha (Vedic Planetary Periods) ──
    results.append(vimshottari.compute(profile, constants))

    # ── Phase 2: Dimensional Expansion ──

    # ── 53. Chaldean Numerology ──
    results.append(chaldean.compute(profile, constants))

    # ── 54. Ifá (Yoruba Binary Odu) ──
    results.append(ifa.compute(profile, constants))

    # ── 55. Egyptian 36 Decans ──
    results.append(egyptian_decan.compute(profile, constants))

    # ── Batch 8: Islamic Ilm al-Huruf ──

    # ── 56. Taksir (Letter Decomposition) ──
    results.append(taksir.compute(profile, constants))

    # ── 57. Bast & Kasr (Expansion/Contraction) ──
    results.append(bast_kasr.compute(profile, constants))

    # ── 58. Istikhara Adad (Numerical Consultation) ──
    results.append(istikhara_adad.compute(profile, constants))

    # ── 59. Zakat al-Huruf (Letter Tithing) ──
    results.append(zakat_huruf.compute(profile, constants))

    # ── 60. Jafr (Prophetic Letter Science) ──
    results.append(jafr.compute(profile, constants))

    # ── 61. Buduh Magic Square ──
    results.append(buduh.compute(profile, constants))

    # ── Batch 9: Quick Wins ──

    # ── 62. Cornerstone / First Vowel / Capstone ──
    results.append(cornerstone.compute(profile, constants))

    # ── 57. Life Purpose (Dan Millman) ──
    results.append(life_purpose.compute(profile, constants))

    # ── 58. Steiner 7-Year Cycles ──
    results.append(steiner_cycles.compute(profile, constants))

    # ── 59. Enneagram from DOB ──
    results.append(enneagram_dob.compute(profile, constants))

    # ── 60. Tarot Year Card ──
    results.append(tarot_year.compute(profile, constants))

    # ── 61. Tarot Name Cards ──
    results.append(tarot_name.compute(profile, constants))

    # ── 62. Latin Ordinal Gematria ──
    results.append(latin_ordinal.compute(profile, constants))

    # ── Batch 10: Gematria Battery ──

    # ── 63. Greek Isopsephy ──
    results.append(greek_isopsephy.compute(profile, constants))

    # ── 64. Coptic Isopsephy ──
    results.append(coptic_isopsephy.compute(profile, constants))

    # ── 65. Armenian Gematria ──
    results.append(armenian_gematria.compute(profile, constants))

    # ── 66. Georgian Gematria ──
    results.append(georgian_gematria.compute(profile, constants))

    # ── 67. Agrippan Latin Gematria ──
    results.append(agrippan.compute(profile, constants))

    # ── 68. Thelemic (ALW) Gematria ──
    results.append(thelemic_gematria.compute(profile, constants))

    # ── 69. Trithemius Cipher ──
    results.append(trithemius.compute(profile, constants))

    # ── Batch 11: Calendar Systems ──

    # ── 70. Planetary Hours ──
    results.append(planetary_hours.compute(profile, constants))

    # ── 71. Egyptian God of Day ──
    results.append(god_of_day.compute(profile, constants))

    # ── 72. Celtic Tree Calendar ──
    results.append(celtic_tree.compute(profile, constants))

    # ── 73. Ogham ──
    results.append(ogham.compute(profile, constants))

    # ── 74. Birth Rune (Elder Futhark) ──
    results.append(birth_rune.compute(profile, constants))

    # ── Batch 12: BaZi Sub-Layers ──

    # ── 74b. BaZi Day Master Strength ──
    results.append(bazi_daymaster.compute(profile, constants, bazi_data=bazi_data))

    # ── 74c. BaZi Luck Pillars (Da Yun) ──
    results.append(bazi_luck_pillars.compute(profile, constants, bazi_data=bazi_data))

    # ── 75. BaZi Hidden Stems ──
    results.append(bazi_hidden_stems.compute(profile, constants, bazi_data=bazi_data))

    # ── 76. BaZi Ten Gods ──
    results.append(bazi_ten_gods.compute(profile, constants, bazi_data=bazi_data))

    # ── 77. BaZi Combinations & Clashes ──
    results.append(bazi_combos.compute(profile, constants, bazi_data=bazi_data))

    # ── 78. BaZi Special Stars (ShenSha) ──
    results.append(bazi_shensha.compute(profile, constants, bazi_data=bazi_data))

    # ── Batch 13: Additional P1 Systems ──

    # ── 79. Ba Zhai (Eight Mansions) ──
    results.append(bazhai.compute(profile, constants))

    # ── 80. Meihua Yishu (Plum Blossom) ──
    results.append(meihua.compute(profile, constants))

    # ── 81. Balinese Pawukon ──
    results.append(pawukon.compute(profile, constants))

    # ── 82. Javanese Primbon / Weton ──
    results.append(primbon.compute(profile, constants))

    # Module 110: Weton (Javanese 5+7 day cycle)
    results.append(weton.compute(profile, constants))

    # Module 111: Planetary Joy (Hellenistic house rejoicing)
    results.append(planetary_joy.compute(profile, constants))

    # Module 112: Akan Kra Din (West African soul-name)
    results.append(akan_kra_din.compute(profile, constants))

    # Module 113: Persian Extended Abjad
    results.append(persian_abjad.compute(profile, constants))

    # ── 83. Tibetan Mewa & Parkha ──
    results.append(tibetan_mewa.compute(profile, constants))

    # ── 84. Dreamspell / Galactic Signature ──
    results.append(dreamspell.compute(profile, constants))

    # ── 85. Aztec Tonalpohualli ──
    results.append(tonalpohualli.compute(profile, constants))

    # ── 86. Ethiopian Asmat ──
    results.append(ethiopian_asmat.compute(profile, constants))

    # ── 87. Rose Cross Sigil ──
    results.append(rose_cross_sigil.compute(profile, constants))

    # ── 88. Planetary Kameas ──
    results.append(planetary_kameas.compute(profile, constants))

    # ── 89. Ars Magna (Lull) ──
    results.append(ars_magna.compute(profile, constants))

    # ── 90. Golden Dawn 777 Correspondences ──
    results.append(gd_correspondences.compute(profile, constants))

    # ── Ephemeris Phase 1: Foundation ──

    # ── 91. Natal Chart (planetary positions) ──
    if natal_chart_data is not None:
        # Pre-computed natal chart provided (e.g., from web server geocoding)
        r_natal = SystemResult(
            id="natal_chart",
            name="Natal Chart (Tropical)",
            certainty="COMPUTED_STRICT",
            data=natal_chart_data,
            interpretation=None,
            constants_version=constants["version"],
            references=["Swiss Ephemeris (Moshier)", "Pre-computed by server"],
            question="Q1_IDENTITY",
        )
        results.append(r_natal)
    else:
        r_natal = natal_chart.compute(profile, constants)
        results.append(r_natal)
        natal_chart_data = r_natal.data if r_natal.certainty == "COMPUTED_STRICT" else None

    # ── 20. Temperament (post-natal: derive element from Sun sign season) ──
    _sun_lon = (natal_chart_data or {}).get("sun_longitude")
    if _sun_lon is not None:
        _sun_sign_idx = int(_sun_lon / 30)
        _season_map = {
            0: "Air", 1: "Air", 2: "Air",
            3: "Fire", 4: "Fire", 5: "Fire",
            6: "Earth", 7: "Earth", 8: "Earth",
            9: "Water", 10: "Water", 11: "Water",
        }
        _pri_el = _season_map.get(_sun_sign_idx, "Earth")
        _asc_lon = (natal_chart_data or {}).get("ascendant")
        _sec_el = _season_map.get(int(_asc_lon / 30), "Earth") if _asc_lon is not None else None
    else:
        _month = profile.dob.month
        _pri_el = {12:"Water",1:"Water",2:"Water",3:"Air",4:"Air",5:"Air",
                   6:"Fire",7:"Fire",8:"Fire",9:"Earth",10:"Earth",11:"Earth"}.get(_month,"Earth")
        _sec_el = None
    results.append(temperament.compute(profile, constants,
                                        primary_element=_pri_el,
                                        secondary_element=_sec_el))

    # ── 92. House System (Whole Sign) ──
    results.append(house_system.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 93. Aspects (Major) ──
    results.append(aspects.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Ephemeris Phase 2: High-value systems ──

    # ── 94. Essential Dignities ──
    results.append(essential_dignities.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 95. Sect (Diurnal/Nocturnal) ──
    results.append(sect.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 96. Arabic Parts (Hermetic Lots) ──
    results.append(arabic_parts.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 97. Solar Return (Annual Chart) ──
    results.append(solar_return.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 98. Secondary Progressions ──
    results.append(progressions.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 99. Fixed Stars (Behenian + Royal) ──
    results.append(fixed_stars.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 114. Antiscia (Shadow Degrees) ──
    results.append(antiscia.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 115. Yogini Dasha (36-Year Vedic Cycle) ──
    results.append(yogini_dasha.compute(profile, constants))

    # ── 116. Ashtottari Dasha (108-Year Vedic Cycle) ──
    results.append(ashtottari_dasha.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 117. Zi Wei Dou Shu (Purple Star Astrology) ──
    results.append(zi_wei_dou_shu.compute(profile, constants))

    # ── 118. Shadbala (Six-Fold Planetary Strength) ──
    results.append(shadbala.compute(profile, constants))

    # ── Ephemeris Phase 3: 12-Module Expansion ──

    # ── 119. Almuten Figuris (Lord of the Geniture) ──
    results.append(almuten.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 120. Mutual Reception ──
    results.append(reception.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 121. Declinations (Parallel/Contraparallel) ──
    results.append(declinations.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 122. Midpoints (Ebertin Cosmobiology) ──
    results.append(midpoints.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 123. Harmonic Charts ──
    results.append(harmonic_charts.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 124. Zodiacal Releasing ──
    results.append(zodiacal_releasing.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 125. Solar Arc Directions ──
    results.append(solar_arc.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 126. Dorothean Chronocrators ──
    results.append(dorothean_chronocrators.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 127. Ashtakavarga (Vedic Benefic Points) ──
    results.append(ashtakavarga.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 128. Shodashavarga (Vedic Divisional Charts) ──
    results.append(shodashavarga.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 129. Tasyir (Islamic Primary Directions) ──
    results.append(tasyir.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 130. Kalachakra Dasha ──
    results.append(kalachakra_dasha.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Batch 18a ──

    # ── 131. Bonification (Hellenistic Planetary Condition) ──
    results.append(bonification.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 132. Zairja (Islamic Combinatorial Letter Oracle) ──
    results.append(zairja.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 133. Qi Men Dun Jia (Nine Palace Board) ──
    results.append(qimen.compute(profile, constants, natal_chart_data=natal_chart_data, bazi_data=bazi_data))

    # ── 134. Da Liu Ren (12-Branch Rotating Plate) ──
    results.append(liu_ren.compute(profile, constants, natal_chart_data=natal_chart_data, bazi_data=bazi_data))

    # ── 135. Primary Directions (Hellenistic Timing) ──
    results.append(primary_directions.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 136. Jaimini Chara Dasha (Sign-Based Timing) ──
    results.append(chara_dasha.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 137. Sarvatobhadra Chakra (9×9 Vedic Matrix) ──
    results.append(sarvatobhadra.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 138. Tajika Varshaphal (Annual Horoscopy) ──
    results.append(tajika.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 139. Krishnamurti Paddhati (KP System) ──
    results.append(kp_system.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Batch 19 ──

    # ── 140. Tai Yi Shen Shu (Supreme Unity Cosmic Board) ──
    results.append(taiyi.compute(profile, constants, bazi_data=bazi_data))

    # ── 141. Onmyōdō (Way of Yin-Yang) ──
    results.append(onmyodo.compute(profile, constants))

    # ── 142. Uranian Astrology (Hamburg School) ──
    results.append(uranian.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Batch 20 ──

    # ── 143. Nadi Amsa (D-150 Micro-Division) ──
    results.append(nadi_amsa.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 144. Maramataka (Māori Lunar Calendar) ──
    results.append(maramataka.compute(profile, constants))

    # ── Batch 21a ──

    # ── 145. Babylonian Nativity Horoscope ──
    results.append(babylonian_horoscope.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Batch 21b ──

    # ── 146. Sudarshana Chakra (Triple Wheel of Time) ──
    results.append(sudarshana.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Round 2 ──

    # ── 147. Burmese Mahabote ──
    results.append(mahabote.compute(profile, constants))

    # ── 148. Human Design ──
    r_hd = human_design.compute(profile, constants)
    results.append(r_hd)
    hd_data_for_gk = r_hd.data if r_hd.certainty == "COMPUTED_STRICT" else None

    # ── 149. Gene Keys (depends on Human Design) ──
    results.append(gene_keys.compute(profile, constants, human_design_data=hd_data_for_gk))

    # ── 150. Mandaean Malwasha (Baptismal Name Oracle) ──
    results.append(malwasha.compute(profile, constants))

    # ── 151. Prashna Natal (Vedic Horary — today at noon) ──
    results.append(prashna_natal.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── Jaimini Expansion ──

    # ── 152. Jaimini Chara Karakas (7/8 Significators) ──
    r_karakas = jaimini_karakas.compute(profile, constants, natal_chart_data=natal_chart_data)
    results.append(r_karakas)
    karakas_data = r_karakas.data if r_karakas.certainty == "COMPUTED_STRICT" else None

    # ── 153. Jaimini Argala (Planetary Intervention) ──
    results.append(jaimini_argala.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 154. Jaimini Navamsha (D9 — Dharma Chart) ──
    results.append(jaimini_navamsha.compute(profile, constants, natal_chart_data=natal_chart_data, karakas_data=karakas_data))

    # ── 155. AstroCartoGraphy (Planetary Lines) ──
    results.append(astrocartography.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 156. KP Sub-Lord System (Three-Tier) ──
    results.append(kp_sublords.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 157. Draconic Chart (Soul Blueprint) ──
    results.append(draconic_chart.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 158. Solar Return Deep Read (Annual Thematic Interpretation) ──
    results.append(solar_return_deep.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 159. Electional Timing Windows (Ilm al-Ikhtiyarat) ──
    results.append(electional_windows.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 160. Muhurta (Vedic Auspicious Timing) ──
    results.append(muhurta.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 161. Synastry (Cross-Chart Relationship Analysis) ──
    results.append(synastry.compute(profile, constants,
        natal_chart_data=natal_chart_data))

    # ── 162. Rectification (Birth Time Sensitivity Diagnostic) ──
    results.append(rectification.compute(profile, constants))

    # ── 153. Horary Timing (Planetary Hour & Day Ruler) ──
    results.append(horary_timing.compute(profile, constants))

    # ── 164. Quranic Figures (46 Named Figures — Abjad Kabir) ──
    results.append(quranic_figures.compute(profile, constants))

    # ── 165. Torah Figures (68 Named Figures — Hebrew Gematria Standard) ──
    results.append(torah_figures.compute(profile, constants))

    # ── 166. NT Figures (34 Named Figures — Greek Isopsephy) ──
    results.append(nt_figures.compute(profile, constants))

    # ── 167. Cross-Scripture Intersection (Cross-Tradition Analysis) ──
    results.append(cross_scripture.compute(profile, constants))

    # ── 168. Arabic Root Extraction (علم الاشتقاق) ──
    results.append(arabic_roots.compute(profile, constants))

    # ── 169. Arabic Morphology Analysis (علم الصرف) ──
    results.append(arabic_morphology.compute(profile, constants))

    # ── 170. Name Semantics (علم المعاني) ──
    results.append(name_semantics.compute(profile, constants))

    # ── 171. Arabic Phonetics (علم المخارج والصفات) ──
    results.append(arabic_phonetics.compute(profile, constants))

    # ── 172. Arabic Letter Nature — Al-Buni (طبائع الحروف) ──
    results.append(arabic_letter_nature.compute(profile, constants))

    # ── 173. Digit Patterns (أنماط الأرقام) ──
    results.append(digit_patterns.compute(profile, constants))

    # ── 174. Lineage Computation (حساب النسب) ──
    results.append(lineage_computation.compute(profile, constants))

    # ── 175. Hijri Calendar Encoding (ترميز التقويم الهجري) ──
    results.append(hijri_calendar_encoding.compute(profile, constants))

    # ── 176. Calligraphy Structure (هندسة الخط) ──
    results.append(calligraphy_structure.compute(profile, constants))

    # ── 177. Divine Breath (النفس الإلهي) ──
    results.append(divine_breath.compute(profile, constants))

    # ── 178. Letter Position Encoding (ترميز المواقع) ──
    results.append(letter_position_encoding.compute(profile, constants))

    # ── 179. Abjad Visual Architecture (العمارة البصرية) ──
    results.append(abjad_visual_architecture.compute(profile, constants))

    # ── 180. Name Weight (ثقل الاسم) ──
    results.append(name_weight.compute(profile, constants))

    # ── 181. Arabic Rhetoric (علم البديع) ──
    results.append(arabic_rhetoric.compute(profile, constants))

    # ── 182. Sonority Curve (منحنى الرنين) ──
    results.append(sonority_curve.compute(profile, constants))

    # ── 183. Larger Awfaq (الأوفاق الكبرى) ──
    results.append(larger_awfaq.compute(profile, constants))

    # ── 184. Qibla as Axis (القبلة كمحور) ──
    results.append(qibla_as_axis.compute(profile, constants))

    # ── 185. Prayer Times as Timing (أوقات الصلاة كتوقيت) ──
    results.append(prayer_times_as_timing.compute(profile, constants))

    # ── 186. Chronobiology (الأحياء الزمنية) ──
    results.append(chronobiology.compute(profile, constants))

    # ── 187. Void Matrix (مصفوفة الفراغ) — comparative ──
    results.append(void_matrix.compute(profile, constants, all_results=results))

    # ── 188. Barzakh Coefficient (معامل البرزخ) — comparative ──
    results.append(barzakh_coefficient.compute(profile, constants, all_results=results))

    # ── 189. Hermetic Alignment (التوافق الهرمسي) — comparative ──
    results.append(hermetic_alignment.compute(profile, constants, all_results=results))

    # ── 190. Execution Pattern Analysis (تحليل نمط التنفيذ) — comparative ──
    results.append(execution_pattern_analysis.compute(profile, constants, all_results=results))

    # ── 191. Minimum Viable Signature (التوقيع الأدنى) — comparative ──
    results.append(minimum_viable_signature.compute(profile, constants, all_results=results))

    # ── Round 4: Cross-Tradition Expansion (20 modules) ──

    # ── 192. Kala Sarpa Yoga Check (Vedic) ──
    results.append(kala_sarpa_check.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 193. Panchamahabhuta (Vedic Five Elements) ──
    results.append(panchamahabhuta.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 194. Ayurvedic Astrological Dosha ──
    results.append(ayurvedic_constitution.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 195. Mantra Seed Syllable (Bija) ──
    results.append(mantra_seed_syllable.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 196. Vedic Gem Prescription (Navaratna) ──
    results.append(vedic_gem_prescription.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 197. BaZi 10-Year Forecast ──
    results.append(bazi_10_year_forecast.compute(profile, constants, bazi_data=bazi_data))

    # ── 198. Zi Wei Dou Shu — Four Transformations ──
    results.append(zi_wei_deeper.compute(profile, constants))

    # ── 199. Four Pillars Element Balance ──
    results.append(four_pillars_balance.compute(profile, constants, bazi_data=bazi_data))

    # ── 200. Gematria Word Matches ──
    results.append(gematria_word_matches.compute(profile, constants))

    # ── 201. Sephirotic Path Analysis (META) ──
    results.append(sephirotic_path_analysis.compute(profile, constants, all_results=results))

    # ── 202. Solomonic Correspondences (META) ──
    results.append(solomonic_correspondences.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 203. African Day Name Extended ──
    results.append(african_day_name_extended.compute(profile, constants))

    # ── 204. Enneagram Deeper Analysis (META) ──
    results.append(enneagram_deeper.compute(profile, constants, all_results=results))

    # ── 205. Hermetic Element Balance ──
    results.append(hermetic_element_balance.compute(profile, constants, natal_chart_data=natal_chart_data, all_results=results))

    # ── 206. Circadian Medicine (Birth Hour Organ Clock) ──
    results.append(circadian_medicine.compute(profile, constants))

    # ── 207. Seasonal Psychology ──
    results.append(seasonal_psychology.compute(profile, constants))

    # ── 208. Element Consensus (Bridge) ──
    results.append(element_consensus.compute(profile, constants, all_results=results))

    # ── 209. Timing Consensus (Bridge) ──
    results.append(timing_consensus.compute(profile, constants, all_results=results))

    # ── 210. Planetary Ruler Consensus (Bridge) ──
    results.append(planetary_ruler_consensus.compute(profile, constants, all_results=results))

    # ── 211. Archetype Consensus (Bridge/META) ──
    results.append(archetype_consensus.compute(profile, constants, all_results=results))

    # ── Round 5 Wave 1: Decoz Layer (8 modules, 15 logical systems) ──

    # ── 212. Balance Number ──
    results.append(balance_number.compute(profile, constants))

    # ── 213. Rational Thought Number ──
    results.append(rational_thought.compute(profile, constants))

    # ── 214. Inclusion Table (Karmic Lessons) ──
    results.append(inclusion_table.compute(profile, constants))

    # ── 215. Special Letters (First Vowel + First Consonant) ──
    results.append(special_letters.compute(profile, constants))

    # ── 216. Period Cycles (3 life periods) ──
    results.append(period_cycles.compute(profile, constants))

    # ── 217. Transit Letters (Physical / Mental / Spiritual) ──
    results.append(transit_letters.compute(profile, constants))

    # ── 218. Yearly Essence Cycle ──
    results.append(yearly_essence_cycle.compute(profile, constants))

    # ── 219. Minor Numbers (Current Name) ──
    results.append(minor_numbers.compute(profile, constants))

    # ── Round 5 Wave 2: Tarot + Esoteric + Hellenistic (6 modules, 10 logical systems) ──

    # ── 220. Tarot Greer Birth Cards (Constellation + Hidden Factor) ──
    results.append(tarot_greer_birth_cards.compute(profile, constants))

    # ── 221. Greer Zodiac Card (Sun Sign → Major Arcana) ──
    results.append(greer_zodiac_card.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 222. Prenatal Syzygy (Last New/Full Moon before birth) ──
    results.append(prenatal_syzygy.compute(profile, constants))

    # ── 223. Cheiro Extensions (Compound Number + Color Affinity) ──
    results.append(cheiro_extensions.compute(profile, constants))

    # ── 224. Roman Chronogram Name ──
    results.append(roman_chronogram.compute(profile, constants))

    # ── 225. Hebrew AIQ BKR (Nine Chambers) ──
    results.append(hebrew_aiq_beker.compute(profile, constants))

    # ── Round 5 Wave 3: Cross-Tradition (12 modules, 15 logical systems) ──

    # ── 226. Tibetan Parkha (gender-dependent) ──
    results.append(tibetan_parkha.compute(profile, constants))

    # ── 227. Tibetan Elements (Lo + Srog) ──
    results.append(tibetan_elements.compute(profile, constants))

    # ── 228. Tamil Pancha Pakshi (Moon nakshatra + paksha) ──
    results.append(tamil_panchapakshi.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 229. Chinese Jian-Chu (12 Day Officers) ──
    results.append(chinese_jian_chu.compute(profile, constants))

    # ── 230. Igbo Market Day ──
    results.append(igbo_market_day.compute(profile, constants))

    # ── 231. Zoroastrian Day Yazata ──
    results.append(zoroastrian_day_yazata.compute(profile, constants))

    # ── 232. Vedic Arudha Pada ──
    results.append(vedic_arudha_pada.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 233. Vedic Upapada Lagna ──
    results.append(vedic_upapada_lagna.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 234. Vedic Pushkara Navamsha ──
    results.append(vedic_pushkara_navamsha.compute(profile, constants, natal_chart_data=natal_chart_data))

    # ── 235. BaZi San He + San Hui ──
    results.append(bazi_san_he_san_hui.compute(profile, constants, bazi_data=bazi_data))

    # ── 236. ZWDS Si Hua (Four Transformations) ──
    results.append(zwds_si_hua_palace.compute(profile, constants))

    # ── 237. Hebrew Mispar Variants (4 methods) ──
    results.append(hebrew_mispar_variants.compute(profile, constants))

    # ── Round 5 Wave 4: Planes of Expression ──

    # ── 238. Planes of Expression (Physical/Mental/Emotional/Intuitive) ──
    results.append(planes_of_expression.compute(profile, constants))

    # ── SYNTHESIS ──
    # Pass profile so synthesis can pick a name-length-matched baseline
    synth = synthesis.synthesize(results, constants, profile=profile)

    # ── NARRATIVE ──
    narrative = compute_narrative(profile, results, synth, constants)

    # ── ATTACH INTERPRETATIONS ──
    loader = InterpretationLoader().load_all()
    for r in results:
        # Skip override if module-source already provides interpretation
        if getattr(r, 'interpretation', None):
            continue
        interp = loader.get(r.id)
        if interp:
            data = r.data if isinstance(r.data, dict) else {}
            # Conditional template: use fallback when primary placeholder can't resolve
            en_template = interp.en
            ar_template = interp.ar
            if interp.en_fallback:
                # Check if primary template's key placeholder resolves to a real value
                flat = _flatten_data(data) if hasattr(_flatten_data, '__call__') else data
                # For archetype_consensus: use fallback when consensus_archetype is None/empty
                archetype_val = flat.get("consensus_archetype") or flat.get("archetype")
                if not archetype_val:
                    en_template = interp.en_fallback
                    ar_template = interp.ar_fallback or interp.ar
            r.interpretation = _format_interp(en_template, data) if en_template else ""
            if ar_template:
                r.ar_interpretation = _format_interp(ar_template, data)
    interp_report = loader.coverage_report([r.id for r in results])

    # ── OUTPUT ──
    out = {
        "profile": {
            "subject": profile.subject,
            "arabic": profile.arabic,
            "dob": date_to_iso(profile.dob),
            "today": date_to_iso(profile.today),
            "timezone": profile.timezone,
            "location": profile.location,
            "variant": profile.variant,
            "core_numbers": {
                "life_path": profile.life_path,
                "expression": profile.expression,
                "soul_urge": profile.soul_urge,
                "personality": profile.personality,
                "birthday": profile.birthday_number,
                "abjad_first": profile.abjad_first,
            },
            "mother_name": profile.mother_name,
            "mother_name_ar": profile.mother_name_ar,
            "mother_dob": profile.mother_dob,
        },
        "constants_version": constants["version"],
        # Product-surface taxonomy — adds domain + tier fields to each result for
        # unified_view.render_domain. Unclassified modules (engine debug view)
        # get domain=None and are excluded from domain tables.
        "results": [apply_taxonomy(r.__dict__) for r in results],
        "synthesis": synth,
        "narrative": narrative,
        "ledger": ledger
    }

    # ── Semantic Reading Layer ──────────────────────────────────────────────
    try:
        taxonomy = load_taxonomy()

        # Step 1: Reduce module results into axis signals
        axis_signals = reduce_axes(results, taxonomy)

        # Step 2: Detect cross-axis resonance and tension
        resonance = synthesize_across_axes(axis_signals)

        # Step 3: Determine activation state per axis
        activation = activation_layer(axis_signals)

        # Step 4: Detect meta-patterns
        profile_core = {
            "day": profile.dob.day,
            "month": profile.dob.month,
            "year": profile.dob.year,
        }
        meta_patterns = detect_meta_patterns(
            axis_signals=axis_signals,
            resonance=resonance_to_dict(resonance),
            results=results,
            profile_core=profile_core,
        )

        # Step 5: Compute combination for dominant root x dominant sign
        dom_root = resonance.dominant_cross_root
        sky_sig = axis_signals.get("sky") or axis_signals.get("archetypal")
        dom_sign_str = "unknown"
        if sky_sig and hasattr(sky_sig, "dominant_sign") and sky_sig.dominant_sign:
            dom_sign_str = sky_sig.dominant_sign.lower()
        elif sky_sig and isinstance(sky_sig, dict) and sky_sig.get("dominant_sign"):
            dom_sign_str = sky_sig["dominant_sign"].lower()

        combination = {}
        if dom_root and dom_sign_str and dom_sign_str != "unknown":
            try:
                combination = compute_tag_overlap(dom_root, dom_sign_str)
            except Exception:
                combination = {}

        # Step 6: Compose final reading
        semantic_reading = compose_reading(
            axis_signals=signals_to_dict(axis_signals),
            cross_axis=resonance_to_dict(resonance),
            combination=combination,
            profile_core=profile_core,
            activation=activation,
            meta_patterns=meta_patterns,
        )

        out["semantic_reading"] = semantic_reading

    except Exception as e:
        # Never let semantic layer crash the main engine run
        out["semantic_reading"] = {"error": type(e).__name__, "status": "PIPELINE_ERROR"}
    # ── End Semantic Reading Layer ──────────────────────────────────────────

    # ── Psychological Translation Layer ────────────────────────────────────
    if _TRANSLATION_LAYER_AVAILABLE and "semantic_reading" in out:
        try:
            out["psychological_mirror"] = build_psychological_mirror(out["semantic_reading"])
        except Exception as e:
            out["psychological_mirror"] = {"error": type(e).__name__, "status": "TRANSLATION_ERROR"}
    # ── End Psychological Translation Layer ────────────────────────────────

    # ── Psychological Construct Profile ────────────────────────────────────
    if _PSYCH_LAYER_AVAILABLE and "semantic_reading" in out:
        try:
            out["psychological_profile"] = build_psychological_profile(out)
        except Exception as e:
            out["psychological_profile"] = {"error": type(e).__name__, "status": "PSYCH_LAYER_ERROR"}
    # ── End Psychological Construct Profile ────────────────────────────────

    # Write JSON
    if output_path_override:
        output_path = Path(output_path_override)
    else:
        output_path = Path(__file__).parent / "output.json"
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Terminal report
    print(render_terminal(results, synth))
    ledger_text = render_ledger(ledger)
    if ledger_text:
        print(ledger_text)

    print(f"\n  JSON output: {output_path}")
    print(f"  Total systems: {len(results)}")
    print(f"  Locked: {synth['confidence_summary']['strict_locked'] + synth['confidence_summary']['method_locked']}")
    print(f"  Approximate: {synth['confidence_summary']['approximate']}")
    print(f"  Convergences found: {synth['convergence_count']}")
    print(f"  Tier 1 Resonances: {synth['resonance_count']}")
    # True interpretation coverage = batch JSON + inline compute() interpretations
    _result_interps = {r.id for r in results if getattr(r, 'interpretation', None)}
    _batch_missing = interp_report['missing']
    true_missing = [m for m in _batch_missing if m not in _result_interps]
    inline_covered = len(_batch_missing) - len(true_missing)
    true_covered = interp_report['interpreted'] + inline_covered
    true_total = interp_report['total_modules']
    print(f"  Interpretations: {true_covered}/{true_total} ({round(true_covered/true_total*100,1)}%) [{interp_report['interpreted']} batch + {inline_covered} inline]")
    if true_missing:
        print(f"  Missing interps (no batch + no inline): {', '.join(true_missing)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SIRR Engine Runner")
    parser.add_argument("fixture", nargs="?", default=None, help="Path to profile fixture JSON")
    parser.add_argument("--output", default=None, help="Output JSON path (overrides default)")
    # Support legacy positional output path: runner.py fixture.json output.json
    parser.add_argument("legacy_output", nargs="?", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    profile_path = args.fixture
    output_path_override = args.output or args.legacy_output

    # Safety guard: if a non-default profile is passed without an explicit output path,
    # derive the output filename from the profile filename to avoid clobbering output.json.
    if profile_path and not output_path_override:
        from pathlib import Path as _P
        stem = _P(profile_path).stem
        # Only auto-derive if it is NOT the canonical demo fixture
        if stem != "synthetic_profile":
            output_path_override = str(_P(__file__).parent / f"output_{stem}.json")
            print(f"  [runner] Non-default profile detected — writing to output_{stem}.json (not output.json)")

    system_run(profile_path, output_path_override=output_path_override)
