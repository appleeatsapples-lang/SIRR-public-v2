"""SIRR Web App — FastAPI server wrapping the engine for live analysis.

Thin HTTP wrapper over the existing runner.py execution path.
Accepts any name + DOB and runs all 146 modules.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import tempfile
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import stripe
import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# §16.5 — signed URL tokens for reading access (replaces order_id in URLs)
from tokens import mint_token, try_verify_token, TokenError
# §16.2 — Tier 2 at-rest encryption
from crypto import read_maybe_encrypted, write_encrypted, is_encrypted, DecryptionError
# §16.5 — traceback sanitization
from sanitize import sanitize_exception

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
LS_API_KEY = os.environ.get("LEMONSQUEEZY_API_KEY")
LS_WEBHOOK_SECRET = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET")
LS_STORE_ID = os.environ.get("LEMONSQUEEZY_STORE_ID")
LS_VARIANT_ID = os.environ.get("LEMONSQUEEZY_VARIANT_ID")
TEST_MODE = not (stripe.api_key or LS_API_KEY)  # No payment keys = test mode
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

ENGINE = Path(__file__).parent.parent  # web_backend → Engine
sys.path.insert(0, str(ENGINE))

from modules.transliterate import transliterate_to_arabic, transliterate_to_hebrew
try:
    from narrative_synthesis import generate_narrative
except ImportError:
    def generate_narrative(output):
        return "(narrative_synthesis module not available)"
from sirr_core.natal_chart import geocode, compute_chart
from order_store import create_order, get_order, update_order, get_order_by_stripe_session
from reading_generator import generate_reading, extract_reading_context, generate_dashboard_panels
from html_reading import generate_html as generate_html_reading
from unified_synthesis import compute_unified_synthesis

app = FastAPI(title="SIRR Engine", version="2.0")

# Sequential engine execution (runner is not thread-safe)
_engine_lock = threading.Lock()

# ── Tradition families (structural metadata from CLAUDE.md) ──
TRADITION_MAP = {
    "Islamic Hurufism": [
        "abjad_kabir", "abjad_saghir", "abjad_wusta", "abjad_maghribi",
        "elemental_letters", "luminous_dark", "solar_lunar", "wafq", "hijri",
        "manazil", "geomancy", "taksir", "bast_kasr", "istikhara_adad",
        "zakat_huruf", "jafr", "buduh", "persian_abjad", "tasyir", "zairja",
    ],
    "Western Numerology": [
        "attitude", "bridges", "challenges", "chaldean", "compound",
        "cornerstone", "essence", "hidden_passion", "karmic_debt",
        "life_purpose", "maturity", "personal_year", "pinnacles",
        "subconscious_self", "enneagram_dob", "steiner_cycles", "latin_ordinal",
    ],
    "Western Astrology": [
        "decan", "dwad", "profection", "sabian", "firdaria", "temperament",
        "declinations", "midpoints", "harmonic_charts", "solar_arc",
        "solar_return", "progressions", "fixed_stars", "uranian",
    ],
    "Hellenistic": [
        "essential_dignities", "sect", "arabic_parts", "antiscia", "reception",
        "zodiacal_releasing", "dorothean_chronocrators", "bonification",
        "primary_directions", "natal_chart", "house_system", "aspects",
        "almuten", "tajika",
    ],
    "Vedic": [
        "nakshatra", "vedic_tithi", "vedic_yoga", "vimshottari", "yogini_dasha",
        "ashtottari_dasha", "shadbala", "ashtakavarga", "shodashavarga",
        "kalachakra_dasha", "chara_dasha", "sarvatobhadra", "kp_system",
        "nadi_amsa", "sudarshana",
    ],
    "Chinese Metaphysics": [
        "bazi_pillars", "bazi_growth", "bazi_daymaster", "bazi_luck_pillars",
        "bazi_hidden_stems", "bazi_ten_gods", "bazi_combos", "bazi_shensha",
        "chinese_zodiac", "flying_star", "nayin", "nine_star_ki", "lo_shu_grid",
        "iching", "bazhai", "meihua", "zi_wei_dou_shu", "qimen", "liu_ren",
        "taiyi",
    ],
    "Hebrew/Kabbalistic": [
        "hebrew_gematria", "hebrew_calendar", "atbash", "albam", "avgad",
        "notarikon", "tree_of_life",
    ],
    "Gematria Battery": [
        "greek_isopsephy", "coptic_isopsephy", "armenian_gematria",
        "georgian_gematria", "agrippan", "thelemic_gematria", "trithemius",
        "mandaean_gematria",
    ],
    "Tarot & Cartomancy": [
        "tarot_birth", "tarot_year", "tarot_name", "cardology",
    ],
    "Calendar & Cycles": [
        "julian", "biorhythm", "day_ruler", "planetary_hours", "god_of_day",
    ],
    "African Divination": [
        "ifa", "ethiopian_asmat", "akan_kra_din",
    ],
    "Mesoamerican": [
        "mayan", "dreamspell", "tonalpohualli",
    ],
    "Southeast Asian": [
        "pawukon", "primbon", "weton", "planetary_joy",
    ],
    "Celtic & Norse": [
        "celtic_tree", "ogham", "birth_rune",
    ],
    "Western Esoteric": [
        "rose_cross_sigil", "planetary_kameas", "ars_magna", "gd_correspondences",
    ],
    "Other Traditions": [
        "onmyodo", "maramataka", "tibetan_mewa", "babylonian_horoscope",
        "egyptian_decan",
    ],
}

# Reverse lookup: module_id -> tradition family
MODULE_TRADITION = {}
for _trad, _mods in TRADITION_MAP.items():
    for _m in _mods:
        MODULE_TRADITION[_m] = _trad


# ── SIRR Unified Product: 4 internal domains ──
# Spec: REPO/Docs/engine/UNIFIED_ARCHITECTURE.md
# One product, 4 computation domains, ~110 modules surfaced from 238.
# The engine still computes all 238; this map decides what crosses the API boundary.

DOMAIN_MAP = {
    # ── Domain 1: NUMEROLOGY (~28) ──
    "attitude": "numerology",
    "balance_number": "numerology",
    "biorhythm": "numerology",
    "bridges": "numerology",
    "challenges": "numerology",
    "compound": "numerology",
    "cornerstone": "numerology",
    "digit_patterns": "numerology",
    "essence": "numerology",
    "execution_pattern_analysis": "numerology",
    "hidden_passion": "numerology",
    "inclusion_table": "numerology",
    "karmic_debt": "numerology",
    "life_purpose": "numerology",
    "lo_shu_grid": "numerology",
    "maturity": "numerology",
    "minimum_viable_signature": "numerology",
    "period_cycles": "numerology",
    "personal_year": "numerology",
    "pinnacles": "numerology",
    "planes_of_expression": "numerology",
    "rational_thought": "numerology",
    "subconscious_self": "numerology",
    "transit_letters": "numerology",
    "void_matrix": "numerology",
    "yearly_essence_cycle": "numerology",
    "steiner_cycles": "numerology",
    "hermetic_element_balance": "numerology",

    # ── Domain 2: NAME INTELLIGENCE (~40) ──
    "abjad_kabir": "name_intelligence",
    "abjad_saghir": "name_intelligence",
    "abjad_wusta": "name_intelligence",
    "abjad_maghribi": "name_intelligence",
    "abjad_visual_architecture": "name_intelligence",
    "agrippan": "name_intelligence",
    "albam": "name_intelligence",
    "arabic_letter_nature": "name_intelligence",
    "arabic_morphology": "name_intelligence",
    "arabic_phonetics": "name_intelligence",
    "arabic_rhetoric": "name_intelligence",
    "arabic_roots": "name_intelligence",
    "armenian_gematria": "name_intelligence",
    "atbash": "name_intelligence",
    "avgad": "name_intelligence",
    "calligraphy_structure": "name_intelligence",
    "chaldean": "name_intelligence",
    "coptic_isopsephy": "name_intelligence",
    "divine_breath": "name_intelligence",
    "elemental_letters": "name_intelligence",
    "georgian_gematria": "name_intelligence",
    "greek_isopsephy": "name_intelligence",
    "hebrew_aiq_beker": "name_intelligence",
    "hebrew_gematria": "name_intelligence",
    "hebrew_mispar_variants": "name_intelligence",
    "latin_ordinal": "name_intelligence",
    "letter_position_encoding": "name_intelligence",
    "luminous_dark": "name_intelligence",
    "mandaean_gematria": "name_intelligence",
    "name_semantics": "name_intelligence",
    "name_weight": "name_intelligence",
    "notarikon": "name_intelligence",
    "persian_abjad": "name_intelligence",
    "solar_lunar": "name_intelligence",
    "sonority_curve": "name_intelligence",
    "special_letters": "name_intelligence",
    "thelemic_gematria": "name_intelligence",
    "trithemius": "name_intelligence",
    "hebrew_calendar": "name_intelligence",

    # ── Domain 3: ASTRO TIMING (~32) ──
    "almuten": "astro_timing",
    "antiscia": "astro_timing",
    "arabic_parts": "astro_timing",
    "aspects": "astro_timing",
    "bazi_daymaster": "astro_timing",
    "bazi_luck_pillars": "astro_timing",
    "bazi_pillars": "astro_timing",
    "day_ruler": "astro_timing",
    "decan": "astro_timing",
    "declinations": "astro_timing",
    "dorothean_chronocrators": "astro_timing",
    "egyptian_decan": "astro_timing",
    "essential_dignities": "astro_timing",
    "firdaria": "astro_timing",
    "fixed_stars": "astro_timing",
    "house_system": "astro_timing",
    "manazil": "astro_timing",
    "midpoints": "astro_timing",
    "nakshatra": "astro_timing",
    "natal_chart": "astro_timing",
    "planetary_hours": "astro_timing",
    "prenatal_syzygy": "astro_timing",
    "profection": "astro_timing",
    "progressions": "astro_timing",
    "reception": "astro_timing",
    "sabian": "astro_timing",
    "sect": "astro_timing",
    "solar_arc": "astro_timing",
    "solar_return": "astro_timing",
    "tasyir": "astro_timing",
    "vimshottari": "astro_timing",
    "yogini_dasha": "astro_timing",
    "zodiacal_releasing": "astro_timing",
    "dwad": "astro_timing",

    # ── Domain 4: CONVERGENCE (~10) ──
    "archetype_consensus": "convergence",
    "barzakh_coefficient": "convergence",
    "element_consensus": "convergence",
    "hermetic_alignment": "convergence",
    "lineage_computation": "convergence",
    "planetary_ruler_consensus": "convergence",
    "timing_consensus": "convergence",
}

# The actual allowlist is just the keys of DOMAIN_MAP
SIRR_UNIFIED_ALLOWLIST = set(DOMAIN_MAP.keys())


# ── Request model ──

class AnalyzeRequest(BaseModel):
    name_en: str
    name_ar: str = ""
    dob: str  # YYYY-MM-DD
    birth_time: str = ""  # HH:MM, optional
    birth_place: str = ""  # optional — city name or "lat,lng,tz_offset"
    gender: str = ""  # "male" or "female", optional


# ── Engine helpers ──

def _read_json(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ── §16.2 Tier 2 encryption helpers ───────────────────────────────────────

def _serve_tier2_html(path: Path, order_id: str):
    """Return a FileResponse for plaintext files, or an HTMLResponse with
    on-the-fly decrypted content for encrypted files. Preserves backward
    compatibility for grandfathered plaintext reading files."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "Reading not found")
    if is_encrypted(raw):
        try:
            plaintext = read_maybe_encrypted(path, order_id).decode("utf-8")
        except DecryptionError:
            raise HTTPException(404, "Reading not found")
        return HTMLResponse(content=plaintext)
    return FileResponse(str(path), media_type="text/html")


def _encrypt_tier2_outputs(order_id: str) -> int:
    """Encrypt an order's Tier 2 output files in place. Idempotent.
    Called at end of a successful engine job. Returns count encrypted."""
    readings_dir = Path(__file__).parent / "readings"
    orders_dir = Path(__file__).parent / "orders"
    targets = [
        orders_dir / f"{order_id}_output.json",
        readings_dir / f"{order_id}.html",
        readings_dir / f"{order_id}_unified.html",
    ]
    encrypted = 0
    for t in targets:
        if not t.exists():
            continue
        try:
            raw = t.read_bytes()
            if is_encrypted(raw):
                continue
            write_encrypted(t, raw, order_id)
            encrypted += 1
        except Exception:
            pass
    return encrypted


def _run_engine(profile_path: str = None, natal_chart_data: dict = None) -> dict:
    """Run the full engine pipeline and return output dict."""
    import importlib
    if "runner" in sys.modules:
        importlib.reload(sys.modules["runner"])
    import runner

    with _engine_lock:
        runner.system_run(profile_path, natal_chart_data=natal_chart_data)
    output = _read_json(ENGINE / "output.json")
    if not output:
        raise HTTPException(500, "Engine produced no output")
    return output


def _enrich_output(output: dict, unified_filter: bool = False) -> dict:
    """Add tradition family + unified-domain metadata to each result.

    If unified_filter=True, drop any result NOT in SIRR_UNIFIED_ALLOWLIST.
    This is the product-surface view (~110 modules). The full 238 remain
    in the engine; they just don't cross the API boundary for the unified product.
    """
    results = output.get("results", [])
    enriched = []
    for r in results:
        rid = r.get("id", "")
        if unified_filter and rid not in SIRR_UNIFIED_ALLOWLIST:
            continue
        r["tradition"] = MODULE_TRADITION.get(rid, "Other Traditions")
        r["domain"] = DOMAIN_MAP.get(rid)  # None if not in allowlist
        enriched.append(r)
    output["results"] = enriched
    return output


# ── Name length tiering ──
# SHORT  (2-3 words) : structural mirror framing, no p-value claims
# MEDIUM (4-6 words) : partial convergence framing, no p-value claims
# LONG   (7+ words)  : full signal framing, p-value claims valid
#
# Name length policy is tracked in Docs/engine/.

def _word_count(s: str) -> int:
    """Count whitespace-separated tokens in a name string."""
    if not s:
        return 0
    return len([w for w in s.strip().split() if w])


def compute_name_length_tier(name_en: str, name_ar: str = "") -> dict:
    """Compute name length tier from the longer of name_en / name_ar word counts.

    Returns a dict with:
      tier: "short" | "medium" | "long"
      word_count: the max word count used for tiering
      name_en_words: word count of Latin name
      name_ar_words: word count of Arabic name
      frame: statistical framing label
      copy: customer-facing framing sentence (EN)
      allows_pvalue_claims: bool — whether p-value language is valid at this tier
    """
    en_words = _word_count(name_en)
    ar_words = _word_count(name_ar)
    word_count = max(en_words, ar_words)

    if word_count >= 7:
        tier = "long"
        frame = "full signal"
        copy = (
            "15 of 25 independent traditions return the same root. "
            "No comparable profile in our reference population has matched this number."
        )
        allows_pvalue = True
    elif word_count >= 4:
        tier = "medium"
        frame = "partial convergence"
        copy = (
            "Across independent traditions, a consistent pattern emerges. "
            "Fuller name chains — father's name, grandfather's name — deepen the reading."
        )
        allows_pvalue = False
    else:
        tier = "short"
        frame = "structural mirror"
        copy = (
            "Multiple traditions compute from your name and birth data. "
            "The pattern they reveal is structural, not statistical."
        )
        allows_pvalue = False

    return {
        "tier": tier,
        "word_count": word_count,
        "name_en_words": en_words,
        "name_ar_words": ar_words,
        "frame": frame,
        "copy": copy,
        "allows_pvalue_claims": allows_pvalue,
    }


# ── API Endpoints ──

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, unified: bool = Query(True, description="Return unified product view (~110 modules) vs full 238")):
    """Analyze any person's name + DOB.

    unified=True  (default): returns ~110 product-surface modules + coherence + tension
    unified=False           : returns full 238 modules (engine debug view)
    """
    try:
        dob = date.fromisoformat(req.dob)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    if not req.name_en.strip():
        raise HTTPException(400, "English name is required.")

    # Auto-transliterate if no Arabic name provided
    arabic_name = req.name_ar.strip()
    auto_transliterated = False
    if not arabic_name:
        arabic_name = transliterate_to_arabic(req.name_en)
        auto_transliterated = True

    # Geocode birth place → coordinates + timezone
    geo = geocode(req.birth_place) if req.birth_place.strip() else None
    chart_data = None
    if geo and req.birth_time.strip():
        try:
            chart_data = compute_chart(
                dob, req.birth_time.strip(), geo.lat, geo.lng, geo.utc_offset,
            )
        except Exception:
            chart_data = None  # graceful degradation

    # Build temporary fixture for runner.py
    fixture = {
        "subject": req.name_en.strip().upper(),
        "arabic": arabic_name if arabic_name else req.name_en.strip().upper(),
        "dob": req.dob,
        "today": date.today().isoformat(),
    }
    if req.birth_time.strip():
        fixture["birth_time_local"] = req.birth_time.strip()
    if geo:
        fixture["location"] = geo.city
        fixture["timezone"] = geo.tz_name
        fixture["latitude"] = geo.lat
        fixture["longitude"] = geo.lng
        fixture["utc_offset"] = geo.utc_offset
    elif req.birth_place.strip():
        fixture["location"] = req.birth_place.strip()
    if req.gender.strip().lower() in ("male", "female"):
        fixture["gender"] = req.gender.strip().lower()

    tmp = ENGINE / "fixtures" / "_temp_analyze.json"
    tmp.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        output = _run_engine(str(tmp), natal_chart_data=chart_data)
        # Compute unified synthesis BEFORE filtering, so coherence/tension
        # can draw on the full 238-module synthesis layer.
        output["unified"] = compute_unified_synthesis(output)
        output = _enrich_output(output, unified_filter=unified)
        output["narrative"] = generate_narrative(output)
        output["name_length_tier"] = compute_name_length_tier(
            req.name_en, arabic_name
        )
        output["view"] = "unified" if unified else "full_238"
        if auto_transliterated:
            output["auto_transliterated"] = True
            output["arabic_used"] = arabic_name
        if chart_data:
            output["natal_chart_computed"] = True
        return output
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        tmp.unlink(missing_ok=True)


@app.get("/api/demo")
def demo(unified: bool = Query(True)):
    """Serve the synthetic demo profile (FATIMA AHMED OMAR ALKATIB).

    Returns the pre-generated synthetic_output.json — no on-the-fly engine
    run, no personal data. The synthetic profile demonstrates the engine's
    output shape against a fictional identity.
    """
    output = _read_json(ENGINE / "fixtures" / "synthetic_output.json")
    if not output:
        raise HTTPException(500, "Synthetic demo output not available")
    output["unified"] = compute_unified_synthesis(output)
    output = _enrich_output(output, unified_filter=unified)
    output["narrative"] = generate_narrative(output)
    output["view"] = "unified" if unified else "full_238"
    return output


@app.get("/api/transliterate")
def transliterate(name: str = Query(..., min_length=1)):
    """Transliterate an English name to Arabic and Hebrew script."""
    return {
        "arabic": transliterate_to_arabic(name),
        "hebrew": transliterate_to_hebrew(name),
    }


@app.get("/api/name-tier")
def name_tier(name_en: str = Query("", max_length=512),
              name_ar: str = Query("", max_length=512)):
    """Return the name-length tier (short/medium/long) for given inputs.

    Front-end uses this for live tier indicators. Never rejects — if both
    fields are empty, returns tier=short with word_count=0.
    """
    return compute_name_length_tier(name_en, name_ar)


@app.get("/api/status")
def get_status():
    """Return engine metadata."""
    modules_dir = ENGINE / "modules"
    py = [f for f in modules_dir.glob("*.py")
          if f.name not in ("__init__.py", "synthesis.py", "narrative.py", "transliterate.py")]
    return {
        "module_count": len(py),
        "tradition_count": len(TRADITION_MAP),
        "version": "SIRR v2",
    }


@app.get("/api/traditions")
def get_traditions():
    """Return tradition family groupings."""
    return TRADITION_MAP


# ── Website / Commercial Endpoints ────────────────────────────────────────

WEB_DIR = ENGINE / "web"

@app.get("/")
async def homepage():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/privacy")
async def privacy_page():
    return FileResponse(str(WEB_DIR / "privacy.html"))


@app.get("/terms")
async def terms_page():
    return FileResponse(str(WEB_DIR / "terms.html"))

@app.get("/success")
async def success_page(order_id: str = None, token: str = None):
    # Both accepted for backward-compat; token is preferred per §16.5
    return FileResponse(str(WEB_DIR / "success.html"))


# ── §16.5 — Token-based reading access (preferred; no PII in URLs) ─────────

def _resolve_token_or_order_id(token_or_id: str) -> str:
    """Accept either a signed token (new canonical) or a raw order_id
    (grandfathered). Returns the resolved order_id or raises 404."""
    resolved = try_verify_token(token_or_id)
    if resolved:
        return resolved
    # Grandfather: still accept raw order_id from legacy URLs
    order = get_order(token_or_id)
    if not order:
        raise HTTPException(404, "Reading not found")
    return token_or_id


@app.get("/r/{token}")
async def reading_by_token(token: str):
    """Token-gated reading page. §16.5 — replaces /reading/{order_id} pattern."""
    order_id = _resolve_token_or_order_id(token)
    return await reading_page(order_id)


@app.get("/r/{token}/unified")
async def reading_unified_by_token(token: str):
    """Token-gated unified view. §16.5 — replaces /reading/{order_id}/unified."""
    order_id = _resolve_token_or_order_id(token)
    return await reading_unified_page(order_id)


@app.get("/api/r/{token}/status")
async def reading_status_by_token(token: str):
    """Token-gated polling. §16.5 — replaces /api/order-status/{order_id}."""
    order_id = _resolve_token_or_order_id(token)
    return await order_status(order_id)


# ── §16.6 — Right to deletion ──────────────────────────────────────────────

class DeleteRequest(BaseModel):
    token: Optional[str] = None
    order_id: Optional[str] = None
    email: Optional[str] = None  # must match order's email for verification


@app.post("/api/delete")
async def request_deletion(req: DeleteRequest):
    """Delete a user's Tier 2 record (order + reading files).

    Authentication model: possession of a valid signed token OR possession of
    the raw order_id AND matching email. The email check prevents a leaked
    order_id from being used by a third party to delete someone's reading.

    Tier 3 (aggregate analytics) removal is handled asynchronously — the
    order_id is added to a deletion queue that the purge job drains within
    30 days per the §16.2 retention commitment.
    """
    if not (req.token or req.order_id):
        raise HTTPException(400, "token or order_id required")

    # Resolve identity
    if req.token:
        resolved = try_verify_token(req.token)
        if not resolved:
            raise HTTPException(401, "invalid or expired token")
        order_id = resolved
    else:
        order_id = req.order_id
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "order not found")
        # Email-based verification for raw order_id path
        if not req.email or order.get("email", "").strip().lower() != req.email.strip().lower():
            raise HTTPException(401, "email does not match order")

    # Delete Tier 2 artifacts: reading HTML, unified HTML, output JSON
    readings_dir = Path(__file__).parent / "readings"
    orders_dir = Path(__file__).parent / "orders"
    deleted_files = []
    for path in [
        readings_dir / f"{order_id}.html",
        readings_dir / f"{order_id}_unified.html",
        orders_dir / f"{order_id}_output.json",
    ]:
        if path.exists():
            try:
                path.unlink()
                deleted_files.append(path.name)
            except Exception:
                pass

    # Mark order record as deleted (retain minimal audit row, strip PII payload)
    try:
        update_order(
            order_id,
            status="deleted",
            profile=None,
            email_hash=None,
            reading_url=None,
            error=None,
        )
    except Exception:
        pass

    # Queue Tier 3 removal (see retention.py — drained by the purge job)
    try:
        _queue_tier3_deletion(order_id)
    except Exception:
        pass

    # §16.5 log hygiene: no profile content in response, no email echoed
    return {"status": "deleted", "files_removed": len(deleted_files)}


def _queue_tier3_deletion(order_id: str) -> None:
    """Append order_id to the Tier 3 deletion queue for async purging."""
    queue_path = Path(__file__).parent / "deletion_queue.txt"
    with open(queue_path, "a") as f:
        f.write(f"{order_id}\n")


@app.get("/reading/{order_id}")
async def reading_page(order_id: str):
    reading_path = Path(__file__).parent / "readings" / f"{order_id}.html"
    if not reading_path.exists():
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "Reading not found")
        if order["status"] == "processing":
            return HTMLResponse("<html><body style='font-family:ui-monospace,monospace;background:#f5f1ea;color:#1a1814;padding:40px'>Your reading is being prepared. Refresh shortly.</body></html>")
        if order["status"] in ("pending", "paid"):
            return HTMLResponse("<html><body style='font-family:ui-monospace,monospace;background:#f5f1ea;color:#1a1814;padding:40px'>Payment confirmed. Your reading is being generated.</body></html>")
        raise HTTPException(404, "Reading not found")
    return _serve_tier2_html(reading_path, order_id)


@app.get("/reading/{order_id}/unified")
async def reading_unified_page(order_id: str):
    """Serve the SIRR unified product view for a completed order.

    Generated alongside the legacy reading by _generate_unified_view().
    If the unified file does not exist yet, attempt to generate it on the fly
    from the order's output JSON (lazy fallback for orders completed before
    the unified view was deployed).
    """
    readings_dir = Path(__file__).parent / "readings"
    unified_path = readings_dir / f"{order_id}_unified.html"

    if not unified_path.exists():
        # Lazy generation from existing output JSON (for legacy orders)
        output_json = Path(__file__).parent / "orders" / f"{order_id}_output.json"
        if output_json.exists():
            _generate_unified_view(str(output_json), order_id)

    if not unified_path.exists():
        # Still not there — either the order never completed or JSON was purged
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "Unified view not found")
        if order["status"] in ("processing", "paid", "pending"):
            return HTMLResponse(
                "<html><body style='font-family:monospace;background:#f5f1ea;color:#1a1814;padding:40px'>"
                "Your unified view is being prepared. Refresh shortly.</body></html>"
            )
        raise HTTPException(404, "Unified view not found")

    return _serve_tier2_html(unified_path, order_id)


@app.get("/view/demo")
async def unified_demo_page():
    """Public demo of the SIRR unified view — renders the synthetic FATIMA profile.

    Never runs the engine. Reads the synthetic golden at fixtures/synthetic_output.json
    and renders it through the unified pipeline. This is the public showcase URL.
    All names, dates, and numbers are generated from synthetic_profile.json.
    """
    try:
        from unified_view import render_unified_html
        golden = ENGINE / "fixtures" / "synthetic_output.json"
        if not golden.exists():
            raise HTTPException(503, "Demo profile unavailable on this deployment.")

        output = json.loads(golden.read_text(encoding="utf-8"))
        output["unified"] = compute_unified_synthesis(output)

        filtered = []
        for r in output.get("results", []):
            rid = r.get("id", "")
            if rid in SIRR_UNIFIED_ALLOWLIST:
                r["domain"] = DOMAIN_MAP[rid]
                r["tradition"] = MODULE_TRADITION.get(rid, "Other Traditions")
                filtered.append(r)
        output["results"] = filtered
        output["view"] = "unified"

        return HTMLResponse(render_unified_html(output))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Demo render failed: {e}")


@app.post("/api/transliterate")
async def api_transliterate(body: dict):
    name = body.get("name", "")
    arabic = transliterate_to_arabic(name)
    return {"arabic": arabic}


class CheckoutRequest(BaseModel):
    name_latin: str
    name_arabic: str = ""
    dob: str
    birth_time: Optional[str] = None
    birth_location: Optional[str] = None
    lang: str = "en"

@app.post("/api/checkout")
async def create_checkout(req: CheckoutRequest):
    order_id = create_order(req.dict())

    # ── TEST MODE: skip payment, generate reading immediately ──
    if TEST_MODE:
        update_order(order_id, status="paid")
        threading.Thread(
            target=_generate_reading_background,
            args=(order_id,),
            daemon=True
        ).start()
        return {"checkout_url": f"{BASE_URL}/success?token={mint_token(order_id)}", "order_id": order_id, "token": mint_token(order_id), "mode": "test"}

    # ── LEMON SQUEEZY MODE ──
    if LS_API_KEY and LS_STORE_ID and LS_VARIANT_ID:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.lemonsqueezy.com/v1/checkouts",
                headers={
                    "Authorization": f"Bearer {LS_API_KEY}",
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
                json={
                    "data": {
                        "type": "checkouts",
                        "attributes": {
                            "checkout_data": {
                                "custom": {"order_id": order_id}
                            },
                            "product_options": {
                                "redirect_url": f"{BASE_URL}/success?token={mint_token(order_id)}",
                            },
                        },
                        "relationships": {
                            "store": {"data": {"type": "stores", "id": LS_STORE_ID}},
                            "variant": {"data": {"type": "variants", "id": LS_VARIANT_ID}},
                        },
                    }
                },
            )
        if resp.status_code != 201:
            raise HTTPException(500, f"Lemon Squeezy error: {resp.text[:200]}")
        checkout_url = resp.json()["data"]["attributes"]["url"]
        update_order(order_id, status="pending")
        return {"checkout_url": checkout_url, "order_id": order_id, "token": mint_token(order_id), "mode": "lemonsqueezy"}

    # ── STRIPE MODE (fallback) ──
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "SIRR Personal Reading",
                    "description": f"Cross-tradition identity analysis for {req.name_latin}",
                },
                "unit_amount": 4900,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{BASE_URL}/success?token={mint_token(order_id)}",
        cancel_url=f"{BASE_URL}/#order",
        metadata={"order_id": order_id},
        customer_email=None,
    )

    update_order(order_id, stripe_session_id=session.id, status="pending")
    return {"checkout_url": session.url, "order_id": order_id, "token": mint_token(order_id), "mode": "stripe"}


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(400, str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session["metadata"].get("order_id")
        if order_id:
            update_order(order_id, status="paid")
            threading.Thread(
                target=_generate_reading_background,
                args=(order_id,),
                daemon=True
            ).start()

    return {"received": True}


@app.post("/api/webhook/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    """Lemon Squeezy webhook — triggered on order_created."""
    import hashlib, hmac
    payload = await request.body()

    if LS_WEBHOOK_SECRET:
        sig = request.headers.get("x-signature", "")
        digest = hmac.new(LS_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, digest):
            raise HTTPException(400, "Invalid signature")

    data = json.loads(payload)
    event_name = data.get("meta", {}).get("event_name", "")

    if event_name == "order_created":
        custom = data.get("meta", {}).get("custom_data", {})
        order_id = custom.get("order_id")
        if order_id:
            update_order(order_id, status="paid")
            threading.Thread(
                target=_generate_reading_background,
                args=(order_id,),
                daemon=True
            ).start()

    return {"received": True}


def _generate_unified_view(output_json_path: str, order_id: str) -> Optional[str]:
    """Render the SIRR unified product view from an order's engine output.

    Additive to the legacy reading: never replaces it, never raises.
    Writes readings/{order_id}_unified.html and returns the URL path on success.
    """
    try:
        from unified_view import render_unified_html
        output = json.loads(read_maybe_encrypted(output_json_path, order_id).decode("utf-8"))
        output["unified"] = compute_unified_synthesis(output)

        filtered = []
        for r in output.get("results", []):
            rid = r.get("id", "")
            if rid in SIRR_UNIFIED_ALLOWLIST:
                r["domain"] = DOMAIN_MAP[rid]
                r["tradition"] = MODULE_TRADITION.get(rid, "Other Traditions")
                filtered.append(r)
        output["results"] = filtered
        output["view"] = "unified"

        readings_dir = Path(__file__).parent / "readings"
        readings_dir.mkdir(exist_ok=True)
        unified_path = readings_dir / f"{order_id}_unified.html"
        unified_path.write_text(render_unified_html(output), encoding="utf-8")
        return f"/reading/{order_id}/unified"
    except Exception as e:
        # Never block the main reading flow on unified-view failure.
        print(f"[unified_view] failed for order {order_id}: {e}", file=sys.stderr)
        return None


def _generate_reading_background(order_id: str):
    """Background thread: run engine + generate reading + save HTML."""
    try:
        order = get_order(order_id)
        if not order:
            return

        update_order(order_id, status="processing")

        # Build a temporary profile fixture
        profile = {
            "subject": order["name_latin"],
            "arabic": order["name_arabic"] or transliterate_to_arabic(order["name_latin"]),
            "dob": order["dob"],
            "today": datetime.utcnow().strftime("%Y-%m-%d"),
            "timezone": "UTC",
            "location": order.get("birth_location") or "",
            "variant": "passport_legal",
        }
        if order.get("birth_time"):
            profile["birth_time"] = order["birth_time"]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            fixture_path = f.name

        output_path = str(Path(__file__).parent / "orders" / f"{order_id}_output.json")

        # Run engine
        result = subprocess.run(
            [sys.executable, "runner.py", fixture_path, "--output", output_path],
            cwd=str(ENGINE),
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"Engine failed: {result.stderr[:500]}")

        # ── Legacy reading (narrative + HTML) — best-effort ──
        # This calls the Anthropic API for narrative generation.
        # If it fails (expired key, rate limit, etc.), the unified product
        # view still renders below. The unified view is the shipped product;
        # the legacy narrative reading is additive.
        legacy_reading_url = None
        try:
            lang = order.get("lang", "en")
            reading_md = generate_reading(output_path, lang)

            # Save reading md temporarily
            reading_md_path = output_path.replace("_output.json", "_reading.md")
            Path(reading_md_path).write_text(reading_md, encoding="utf-8")

            # Generate dashboard panels (best-effort — fall back to prose if it fails)
            panels_data = None
            try:
                panels_data = generate_dashboard_panels(output_path, lang)
            except Exception:
                pass  # Fall back to paragraph rendering

            # Generate HTML
            readings_dir = Path(__file__).parent / "readings"
            readings_dir.mkdir(exist_ok=True)
            html_output_path = str(readings_dir / f"{order_id}.html")
            generate_html_reading(output_path, reading_md_path, html_output_path,
                                  panels_data=panels_data)
            legacy_reading_url = f"/reading/{order_id}"
        except Exception as e:
            print(f"[legacy_reading] failed for order {order_id}: {e}", file=sys.stderr)
            # Continue — unified view is the product

        # ── Unified product view (pure Python, no API calls) ──
        unified_url = _generate_unified_view(output_path, order_id)

        update_order(
            order_id,
            status="ready",
            reading_url=legacy_reading_url or "",
            unified_url=unified_url or "",
        )
        # §16.2 — encrypt Tier 2 output files at rest. Idempotent.
        try:
            _encrypt_tier2_outputs(order_id)
        except Exception as enc_err:
            print(f"[tier2-encrypt] failed for order {order_id}: {type(enc_err).__name__}", file=sys.stderr)

    except Exception as engine_err:
        # §16.5 — sanitize traceback before storing so no profile content
        # leaks into the order row even if an exception message embedded it.
        update_order(order_id, status="failed", error=sanitize_exception(engine_err))


@app.get("/api/order-status/{order_id}")
async def order_status(order_id: str):
    order = get_order(order_id)
    if not order:
        raise HTTPException(404)
    return {
        "status": order["status"],
        "reading_url": order.get("reading_url"),
    }


# ── §16.2 / §16.6 — Retention purge endpoint ──────────────────────────────

@app.post("/api/internal/purge")
async def trigger_purge(request: Request):
    """Run a Tier 2 retention sweep + Tier 3 deletion queue drain.

    Authentication: caller must present the shared secret as the
    `X-Internal-Secret` header (value of env var `SIRR_INTERNAL_SECRET`).
    Intended to be invoked by a Railway scheduled job / external cron.

    If `SIRR_INTERNAL_SECRET` is unset, the endpoint refuses all requests
    — fail closed. Operators who want to trigger it manually must set the
    secret in Railway env vars.

    Returns a JSON summary of what the purge did: orders_removed,
    readings_removed, tier3_processed, dry_run, retention_days, ran_at_unix.
    Never surfaces filenames, order IDs, or any user data in the response.
    """
    configured_secret = os.environ.get("SIRR_INTERNAL_SECRET", "").strip()
    if not configured_secret:
        raise HTTPException(503, "purge endpoint disabled (no SIRR_INTERNAL_SECRET)")

    provided = request.headers.get("x-internal-secret", "")
    # Constant-time comparison to avoid timing-based side-channel
    import hmac as _hmac
    if not _hmac.compare_digest(provided, configured_secret):
        raise HTTPException(401, "invalid or missing internal secret")

    try:
        from retention import purge_cycle
        summary = purge_cycle()
    except Exception as purge_err:
        # Log the sanitized traceback server-side, return a generic error
        print(f"[purge-endpoint] failed: {sanitize_exception(purge_err)}", file=sys.stderr)
        raise HTTPException(500, "purge cycle failed")

    return summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
