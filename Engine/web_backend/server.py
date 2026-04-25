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

# §16.5 — encrypted URL tokens for reading access (post-P2F-PR1: AES-GCM,
# replaces both raw order_id in URLs and the earlier HMAC-signed format)
from tokens import mint_token, try_verify_token, TokenError
# §16.2 — Tier 2 at-rest encryption
from crypto import read_maybe_encrypted, write_encrypted, is_encrypted, DecryptionError
# §16.5 — traceback sanitization
from sanitize import hash_oid, sanitize_exception
# Styled error + status page rendering
from errors import (
    render_page, render_404, render_401, render_400, render_500,
    render_reading_processing, render_reading_pending,
)
# Centralized data paths — honors SIRR_DATA_DIR for Railway volume mount
from paths import ORDERS_DIR, READINGS_DIR, DELETION_QUEUE
# Rate limiting
from middleware import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from security_headers import SecurityHeadersMiddleware

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

# ── FastAPI lifespan — starts/stops the in-process retention scheduler ──
from contextlib import asynccontextmanager
import scheduler as _scheduler


@asynccontextmanager
async def lifespan(_app):
    # Startup
    _scheduler.start()
    yield
    # Shutdown
    await _scheduler.stop()


app = FastAPI(title="SIRR Engine", version="2.0", lifespan=lifespan)

# Security headers on every response (§16 hardening)
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiter wire-in (see middleware.py). Adds limiter to app state
# and registers the 429 handler that returns styled HTML for browsers
# and JSON for API callers.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# ── Router wire-in ────────────────────────────────────────────────────────
# Extracted route groups live in routers/*.py. Each router is a small,
# focused APIRouter with its own auth + helpers. server.py remains the
# composition point + home for cross-cutting concerns (exception handler,
# engine orchestration, checkout flow).
from routers.admin import router as admin_router
from routers.retention import router as retention_router
from routers.pages import router as pages_router

app.include_router(admin_router)
app.include_router(retention_router)
app.include_router(pages_router)


# ── Styled error pages for browser requests, JSON for API ────────────────
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


def _wants_html(request: Request) -> bool:
    """Render HTML only if (a) the path is NOT under /api/ AND
    (b) Accept header includes text/html. API paths always get JSON."""
    path = request.url.path or ""
    if path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept or not accept


@app.exception_handler(StarletteHTTPException)
async def styled_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not _wants_html(request):
        # Preserve FastAPI's default JSON response for API callers
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    # Browser request — render the styled page
    status = exc.status_code
    if status == 404:
        body = render_404()
    elif status == 401:
        body = render_401()
    elif status == 400:
        body = render_400(str(exc.detail) if exc.detail else None)
    elif status >= 500:
        body = render_500()
    else:
        body = render_page(
            title=f"Error {status}",
            code=str(status),
            headline="Something went sideways.",
            detail=str(exc.detail) if exc.detail else "Unexpected response.",
            actions=[("Return home", "/", True)],
        )
    return HTMLResponse(content=body, status_code=status)


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
    compatibility for grandfathered plaintext reading files.

    P2F-PR3 §D: defense-in-depth for FIX E. If encryption failed AND
    the cleanup unlink also failed (best-effort), a plaintext file
    survives alongside an order with status="failed". Refuse to serve
    plaintext for failed orders. The encrypted-content path is unaffected
    (always safe at rest, regardless of order status)."""
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

    # Plaintext fallthrough: only happens for grandfathered legacy files
    # OR for files where encryption failed and FIX E's cleanup also failed.
    # In the latter case, the order has status="failed" — refuse to serve.
    # Defense-in-depth check Codex round 5 named.
    order = get_order(order_id)
    if order and order.get("status") == "failed":
        raise HTTPException(404, "Reading not found")

    return FileResponse(str(path), media_type="text/html")


def _encrypt_tier2_outputs(order_id: str) -> int:
    """Encrypt an order's Tier 2 output files in place. Idempotent.
    Called at end of a successful engine job. Returns count encrypted.

    Failure is FATAL — we must never leave plaintext on disk when
    encryption was expected (Codex Item 10). On any per-file failure:
      1. Log the exception class name (no message — could leak paths).
      2. Downgrade the order from "ready" to status="failed" with an
         "encryption_failed:<ExcClass>" error prefix. The success page
         polls for status in {"ready","failed"}; using "failed" makes
         the customer see the failure UI instead of polling forever.
      3. Atomically clean up — delete any remaining plaintext target
         files so the on-disk state matches the status. Without this
         (P2F-PR2 FIX E / Codex round 4), token-gated serve helpers
         could later read the leftover plaintext via _serve_tier2_html's
         FileResponse fallthrough. FIX A's status update is informational;
         the on-disk state is what serve helpers actually check.
      4. Re-raise so the outer caller can also log and stop further
         post-encryption work.

    Post-condition: after this function returns or raises, every target
    on disk is either encrypted or absent. Plaintext does not survive a
    failed encryption pass.

    Targets list (P2F-PR2 FIX B): explicitly includes _merged.html,
    which is the canonical post-checkout view served at /r/{token}/merged.
    Without this entry, the merged view (which contains the actual
    customer reading) would be left unencrypted on disk.
    """
    readings_dir = READINGS_DIR
    orders_dir = ORDERS_DIR
    targets = [
        orders_dir / f"{order_id}_output.json",
        readings_dir / f"{order_id}.html",
        readings_dir / f"{order_id}_unified.html",
        readings_dir / f"{order_id}_merged.html",
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
        except Exception as enc_err:
            print(
                f"[tier2-encrypt] failed for order {hash_oid(order_id)}: "
                f"{type(enc_err).__name__}",
                file=sys.stderr,
            )
            # Mark order "failed" (not a custom string) so success.html's
            # status===failed branch fires and the customer sees the
            # error UI instead of polling forever. Error field carries
            # the encryption_failed prefix + exception class name for
            # ops visibility — message is omitted to avoid path/key leaks.
            try:
                update_order(
                    order_id,
                    status="failed",
                    error="encryption_failed:" + type(enc_err).__name__,
                )
            except Exception:
                # Order-store failure on top of encryption failure: log
                # and let the outer raise propagate the original error.
                pass
            # FIX E (Codex round 4): atomic plaintext cleanup. Delete any
            # remaining target file that's still plaintext on disk, so the
            # token-gated serve helpers (_serve_tier2_html) cannot return
            # leftover unencrypted bytes via the FileResponse fallthrough.
            # Encrypted-already files are left alone (they'll be
            # retention-swept naturally with the failed order). Best-
            # effort: a delete failure here is logged-then-swallowed
            # because the original encryption error is what we re-raise.
            for cleanup_target in targets:
                if not cleanup_target.exists():
                    continue
                try:
                    raw_now = cleanup_target.read_bytes()
                    if not is_encrypted(raw_now):
                        cleanup_target.unlink()
                except Exception:
                    # Best-effort — original encryption error has priority
                    pass
            # Re-raise so the caller knows encryption did not happen.
            raise
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
@limiter.limit("30/minute")
def analyze(request: Request, req: AnalyzeRequest, unified: bool = Query(True, description="Return unified product view (~110 modules) vs full 238")):
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
        # str(e) could carry user input from the engine error message
        raise HTTPException(500, detail=f"analysis_failed:{type(e).__name__}")
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
@limiter.limit("60/minute")
def transliterate(request: Request, name: str = Query(..., min_length=1)):
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
# Static page routes (/, /privacy, /terms, /success) moved to routers/pages.py.
# WEB_DIR retained here because other routes (e.g. token-gated reading) use it.

WEB_DIR = ENGINE / "web"


# ── §16.5 — Token-based reading access (preferred; no PII in URLs) ─────────

def _resolve_token_or_order_id(token_or_id: str) -> str:
    """Verify an encrypted token and return the embedded order_id.

    §16.5: raw order IDs are no longer accepted on the /r/ path. Only
    AES-256-GCM AEAD-encrypted tokens minted by tokens.mint_token()
    are valid (post-P2F-PR1, 2026-04-19; the prior HMAC-signed format
    is incompatible). The legacy grandfather fallback was removed in P2D.

    Name retained for call-site compatibility; semantics are now
    token-only.
    """
    resolved = try_verify_token(token_or_id)
    if resolved:
        return resolved
    raise HTTPException(404, "Reading not found")


@app.get("/r/{token}")
async def reading_by_token(token: str):
    """Token-gated reading page. §16.5 — replaces /reading/{order_id} pattern."""
    order_id = _resolve_token_or_order_id(token)
    return await _serve_reading_by_id(order_id)


@app.get("/r/{token}/unified")
async def reading_unified_by_token(token: str):
    """Token-gated unified view. §16.5 — replaces /reading/{order_id}/unified."""
    order_id = _resolve_token_or_order_id(token)
    return await _serve_reading_unified_by_id(order_id)


@app.get("/r/{token}/merged")
async def reading_merged_by_token(token: str):
    """Token-gated merged view. PR #18 — combines unified architecture
    with legacy visual vocabulary at each domain header."""
    order_id = _resolve_token_or_order_id(token)
    return await _serve_reading_merged_by_id(order_id)


@app.get("/api/r/{token}/status")
async def reading_status_by_token(token: str):
    """Token-gated polling. §16.5 — replaces /api/order-status/{order_id}."""
    order_id = _resolve_token_or_order_id(token)
    return await _serve_order_status_by_id(order_id)


# ── §16.6 — Right to deletion ──────────────────────────────────────────────

class DeleteRequest(BaseModel):
    token: Optional[str] = None
    order_id: Optional[str] = None
    email: Optional[str] = None  # must match order's email for verification


@app.post("/api/delete")
@limiter.limit("5/minute")
async def request_deletion(request: Request, req: DeleteRequest):
    """Delete a user's Tier 2 record (order + reading files).

    Authentication model: possession of a valid encrypted token (P2F-PR1
    AES-GCM) OR possession of the raw order_id AND matching email. The
    email check prevents a leaked order_id from being used by a third
    party to delete someone's reading.

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
    readings_dir = READINGS_DIR
    orders_dir = ORDERS_DIR
    deleted_files = []
    for path in [
        readings_dir / f"{order_id}.html",
        readings_dir / f"{order_id}_unified.html",
        readings_dir / f"{order_id}_merged.html",
        orders_dir / f"{order_id}_output.json",
    ]:
        if path.exists():
            try:
                path.unlink()
                deleted_files.append(path.name)
            except Exception:
                pass

    # Mark order record as deleted. Nulls four fields only (profile,
    # email_hash, reading_url, error). Does NOT null name_latin,
    # name_arabic, dob, birth_time, or birth_location — those PII fields
    # remain in the row after this update. Closing that gap is tracked
    # in SIRR_MASTER_REGISTRY.md §16.5 deferred surfaces (P2G arc).
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
    queue_path = DELETION_QUEUE
    with open(queue_path, "a") as f:
        f.write(f"{order_id}\n")


def _gone_410_response() -> HTMLResponse:
    """Styled 410 Gone for deprecated raw-order-id reading paths.

    §16.5: order IDs must not appear in URLs. These paths are retained
    only to return a helpful message pointing the user at their secure
    link from checkout email. No order lookup, no status check, no
    order_id echo in the response body.
    """
    body = render_page(
        title="Link retired",
        code="410",
        headline="This link format has been retired for your privacy.",
        detail=(
            "Reading URLs that contained order identifiers have been "
            "deprecated. Please use the secure link from your checkout "
            "email — it does not expose personal information in the URL. "
            "If you can't find it, reach out and we'll re-send."
        ),
        actions=[
            ("Contact support", "mailto:hello@sirr.app", True),
            ("Return home", "/", False),
        ],
    )
    return HTMLResponse(body, status_code=410)


async def _serve_reading_by_id(order_id: str):
    """Internal: serve legacy reading HTML by order_id. Called only via
    the token-gated /r/ wrapper — never routed directly."""
    reading_path = READINGS_DIR / f"{order_id}.html"
    if not reading_path.exists():
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "Reading not found")
        if order["status"] == "processing":
            return HTMLResponse(render_reading_processing())
        if order["status"] in ("pending", "paid"):
            return HTMLResponse(render_reading_pending())
        raise HTTPException(404, "Reading not found")
    return _serve_tier2_html(reading_path, order_id)


@app.get("/reading/{order_id}")
async def reading_page(order_id: str):
    """DEPRECATED — returns 410 Gone. Use /r/{token} instead."""
    return _gone_410_response()


async def _serve_reading_unified_by_id(order_id: str):
    """Internal: serve unified view by order_id. Called only via the
    token-gated /r/ wrapper — never routed directly.

    If the unified file does not exist yet, attempt to generate it on the fly
    from the order's output JSON (lazy fallback for orders completed before
    the unified view was deployed).
    """
    readings_dir = READINGS_DIR
    unified_path = readings_dir / f"{order_id}_unified.html"

    if not unified_path.exists():
        # Lazy generation from existing output JSON (for legacy orders)
        output_json = ORDERS_DIR / f"{order_id}_output.json"
        if output_json.exists():
            _generate_unified_view(str(output_json), order_id)
            # P2F-PR2 FIX C: lazy regen writes plaintext via write_text();
            # encrypt before serving. Idempotent — already-encrypted
            # targets are skipped. Encryption errors propagate as 500
            # (strict-fail per Codex round 3): we never serve a reading
            # we couldn't seal.
            if unified_path.exists():
                _encrypt_tier2_outputs(order_id)

    if not unified_path.exists():
        # Still not there — either the order never completed or JSON was purged
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "Unified view not found")
        if order["status"] in ("processing", "paid", "pending"):
            return HTMLResponse(render_reading_processing())
        raise HTTPException(404, "Unified view not found")

    return _serve_tier2_html(unified_path, order_id)


@app.get("/reading/{order_id}/unified")
async def reading_unified_page(order_id: str):
    """DEPRECATED — returns 410 Gone. Use /r/{token}/unified instead."""
    return _gone_410_response()


async def _serve_reading_merged_by_id(order_id: str):
    """Internal: serve merged view by order_id. Called only via the
    token-gated /r/ wrapper — never routed directly.

    Lazy-regenerates from output JSON on demand for orders completed
    before the merged view was deployed.
    """
    readings_dir = READINGS_DIR
    merged_path = readings_dir / f"{order_id}_merged.html"

    # PR #20 (F7.3 from audit): stale HTML after redeploy. If the
    # rendering code has been updated since the cached HTML was
    # written, regenerate. Avoids customers-with-existing-readings
    # being frozen on the version of the template that existed
    # when they first viewed the page.
    should_regen = not merged_path.exists()
    if merged_path.exists():
        try:
            import merged_view as _mv_mod
            code_mtime = os.path.getmtime(_mv_mod.__file__)
            html_mtime = os.path.getmtime(merged_path)
            if code_mtime > html_mtime:
                should_regen = True
        except Exception:
            # mtime check is a best-effort optimization; never block
            # serving the existing file because of a stat error.
            pass

    if should_regen:
        output_json = ORDERS_DIR / f"{order_id}_output.json"
        if output_json.exists():
            _generate_merged_view(str(output_json), order_id)
            # P2F-PR2 FIX C: lazy regen writes plaintext via write_text();
            # encrypt before serving. Closes the F7.3 mtime-regen
            # plaintext window — without this, every code-update
            # cache-invalidation re-wrote merged.html unencrypted.
            # Idempotent — already-encrypted targets are skipped.
            # Encryption errors propagate as 500 (strict-fail per
            # Codex round 3): we never serve a reading we couldn't seal.
            if merged_path.exists():
                _encrypt_tier2_outputs(order_id)

    if not merged_path.exists():
        order = get_order(order_id)
        if not order:
            raise HTTPException(404, "Merged view not found")
        if order["status"] in ("processing", "paid", "pending"):
            return HTMLResponse(render_reading_processing())
        raise HTTPException(404, "Merged view not found")

    return _serve_tier2_html(merged_path, order_id)


@app.get("/reading/{order_id}/merged")
async def reading_merged_page(order_id: str):
    """DEPRECATED — returns 410 Gone. Use /r/{token}/merged instead."""
    return _gone_410_response()


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
        # Demo uses synthetic input; class name is sufficient for ops
        raise HTTPException(500, f"Demo render failed: {type(e).__name__}")


@app.post("/api/transliterate")
@limiter.limit("60/minute")
async def api_transliterate(request: Request, body: dict):
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
@limiter.limit("10/minute")
async def create_checkout(request: Request, req: CheckoutRequest):
    order_id = create_order(req.dict())

    # ── TEST MODE: skip payment, generate reading immediately ──
    if TEST_MODE:
        update_order(order_id, status="paid")
        threading.Thread(
            target=_generate_reading_background,
            args=(order_id,),
            daemon=True
        ).start()
        return {"checkout_url": f"{BASE_URL}/success?token={mint_token(order_id)}", "token": mint_token(order_id), "mode": "test"}

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
            # LS error body could carry untrusted/provider-controlled detail.
            # Log the full response server-side; surface only a constant to
            # the caller.
            print(
                f"[checkout-ls] HTTP {resp.status_code} from LS",
                file=sys.stderr,
            )
            raise HTTPException(500, "checkout_provider_error")
        checkout_url = resp.json()["data"]["attributes"]["url"]
        update_order(order_id, status="pending")
        return {"checkout_url": checkout_url, "token": mint_token(order_id), "mode": "lemonsqueezy"}

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
    return {"checkout_url": session.url, "token": mint_token(order_id), "mode": "stripe"}


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        # Stripe library exception detail is not user input but the
        # caller is untrusted; constants only.
        raise HTTPException(400, "invalid_signature")

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

    # Fail-closed: an unset secret MUST NOT skip signature verification.
    # Without this guard, any attacker with a guessable order_id could
    # mark orders as paid and trigger engine runs (Anthropic API burn).
    if not LS_WEBHOOK_SECRET:
        raise HTTPException(503, "webhook not configured")

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

        readings_dir = READINGS_DIR
        readings_dir.mkdir(parents=True, exist_ok=True)
        unified_path = readings_dir / f"{order_id}_unified.html"
        unified_path.write_text(render_unified_html(output), encoding="utf-8")
        return f"/reading/{order_id}/unified"
    except Exception as e:
        # Never block the main reading flow on unified-view failure.
        print(f"[unified_view] failed for order {hash_oid(order_id)}: {sanitize_exception(e)}", file=sys.stderr)
        return None


def _generate_merged_view(output_json_path: str, order_id: str) -> Optional[str]:
    """Render the SIRR merged product view from an order's engine output.

    Additive to legacy + unified: never replaces them, never raises.
    Writes readings/{order_id}_merged.html and returns the URL path on
    success.

    Unlike _generate_unified_view, we do NOT strip un-allowlisted results
    from output["results"]. The merged view's visual extractors
    (render_name_cards, extract_animal_profile, extract_planetary_profile)
    need access to modules like tarot_birth, tarot_name, cardology,
    celtic_tree, and mayan that aren't in SIRR_UNIFIED_ALLOWLIST.
    Un-tagged results remain in the list but are naturally invisible to
    render_domain_merged, which filters rows by r["domain"]. So tables
    still only show allowlisted content; visual blocks can draw on the
    full set.
    """
    try:
        from merged_view import render_merged_html
        output = json.loads(read_maybe_encrypted(output_json_path, order_id).decode("utf-8"))
        output["unified"] = compute_unified_synthesis(output)
        for r in output.get("results", []):
            rid = r.get("id", "")
            if rid in SIRR_UNIFIED_ALLOWLIST:
                r["domain"] = DOMAIN_MAP[rid]
                r["tradition"] = MODULE_TRADITION.get(rid, "Other Traditions")
        output["view"] = "merged"

        readings_dir = READINGS_DIR
        readings_dir.mkdir(parents=True, exist_ok=True)
        merged_path = readings_dir / f"{order_id}_merged.html"
        merged_path.write_text(render_merged_html(output), encoding="utf-8")
        return f"/reading/{order_id}/merged"
    except Exception as e:
        print(f"[merged_view] failed for order {hash_oid(order_id)}: {sanitize_exception(e)}", file=sys.stderr)
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

        output_path = str(ORDERS_DIR / f"{order_id}_output.json")

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
            readings_dir = READINGS_DIR
            readings_dir.mkdir(parents=True, exist_ok=True)
            html_output_path = str(readings_dir / f"{order_id}.html")
            # P2F-PR3 §C (round-2 enforcement): _reading.md was always
            # intended to be transient (see "Save reading md temporarily"
            # comment above) but no cleanup was wired up. The file
            # contains the full legacy narrative in plaintext — Tier 2
            # residue that's not in the encryption target list and not
            # in the deletion artifact list.
            #
            # Cleanup is in a `finally` so it runs even if
            # generate_html_reading raises (which it may: panels payload
            # parse failure, template error, disk full, etc.). Unlink
            # itself is best-effort — if THAT fails, retention sweep
            # eventually catches it.
            try:
                generate_html_reading(output_path, reading_md_path, html_output_path,
                                      panels_data=panels_data)
            finally:
                try:
                    Path(reading_md_path).unlink(missing_ok=True)
                except Exception:
                    pass

            legacy_reading_url = f"/reading/{order_id}"
        except Exception as e:
            print(f"[legacy_reading] failed for order {hash_oid(order_id)}: {sanitize_exception(e)}", file=sys.stderr)
            # Continue — unified view is the product

        # ── Unified product view (pure Python, no API calls) ──
        unified_url = _generate_unified_view(output_path, order_id)

        # ── Merged product view (visual hydration of unified domains) ──
        merged_url = _generate_merged_view(output_path, order_id)

        update_order(
            order_id,
            status="ready",
            reading_url=legacy_reading_url or "",
            unified_url=unified_url or "",
            merged_url=merged_url or "",
        )
        # §16.2 — encrypt Tier 2 output files at rest. Idempotent.
        try:
            _encrypt_tier2_outputs(order_id)
        except Exception as enc_err:
            print(f"[tier2-encrypt] failed for order {hash_oid(order_id)}: {type(enc_err).__name__}", file=sys.stderr)

    except Exception as engine_err:
        # §16.5 — sanitize traceback before storing so no profile content
        # leaks into the order row even if an exception message embedded it.
        update_order(order_id, status="failed", error=sanitize_exception(engine_err))


async def _serve_order_status_by_id(order_id: str):
    """Internal: serve order status by order_id. Token-gated callers
    construct reading URLs from their own token; we don't echo the
    server-side raw URL (which contains order_id) into the response.
    Codex Finding 1 (P2F-PR2)."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(404)
    return {"status": order["status"]}


@app.get("/api/order-status/{order_id}")
async def order_status_deprecated(order_id: str):
    """DEPRECATED — returns 410 Gone (P2F §16.5).

    Use /api/r/{token}/status instead, which is token-gated and does not
    accept a raw order_id in the URL path."""
    return _gone_410_response()


# ── Retention + admin + static pages ──────────────────────────────────────
# The following route groups moved to routers/ for clarity:
#   /api/internal/purge   → routers/retention.py
#   /api/internal/metrics → routers/admin.py
#   /admin                → routers/admin.py
#   /, /privacy, /terms, /success → routers/pages.py
# Shared auth lives in auth.py (require_internal_secret).


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
