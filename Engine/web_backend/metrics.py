"""Zero-knowledge operational metrics (§16.3).

Returns aggregate-only snapshots of Tier 2 state. Structurally incapable of
surfacing any individual order's content, name, DOB, or other PII — the
functions in this module NEVER return order_ids, names, or per-row data.
They return counts, distributions, and time-bucketed histograms.

This is the single source of truth for the /admin dashboard. Any field
added here must pass the smell test: "could this leak who a specific
customer is?"  If yes, it doesn't go in.

Aggregation thresholds:
    MIN_BUCKET_SIZE = 5
Any bucket (status counts, language distribution, error category, etc.)
with fewer than MIN_BUCKET_SIZE members is collapsed into "<5" to preserve
k-anonymity. Without this, a single customer from a rare country could be
identified by their language bucket count of 1.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).parent
ORDERS_DIR = BACKEND_DIR / "orders"
READINGS_DIR = BACKEND_DIR / "readings"
DELETION_QUEUE = BACKEND_DIR / "deletion_queue.txt"

MIN_BUCKET_SIZE = 5


def _k_anon(counter: Counter, floor: int = MIN_BUCKET_SIZE) -> dict:
    """Collapse any bucket under `floor` into '<N' placeholder so a rare
    bucket can't point at a single customer.

    Also drops buckets to 0 instead of exact small numbers so even the
    existence of a rare category isn't revealed.
    """
    out: dict = {}
    collapsed = 0
    for key, count in counter.items():
        if count < floor:
            collapsed += count
            continue
        out[str(key)] = count
    if collapsed > 0:
        out[f"<{floor}"] = collapsed
    return out


def _age_bucket(iso_timestamp: str, now: Optional[datetime] = None) -> str:
    """Bucket an ISO timestamp into human-readable age brackets.
    Never returns exact age — just 'today', '1-7d', '8-30d', '>30d'."""
    if not iso_timestamp:
        return "unknown"
    try:
        created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "unknown"
    now = now or datetime.now(timezone.utc)
    age_days = (now - created).total_seconds() / 86400
    if age_days < 1:
        return "today"
    if age_days < 7:
        return "1-7d"
    if age_days < 30:
        return "8-30d"
    return ">30d"


def _error_category(error: Optional[str]) -> str:
    """Map raw error strings to coarse categories without surfacing details.

    The order's 'error' field is already sanitized by sanitize_exception
    (class name + frames only, no message). We scan the full text for
    known exception-class names so tracebacks like
    'Traceback...\\nValueError: <redacted>' still bucket correctly."""
    if not error:
        return "none"
    lower = error.lower()
    for known in ("ValueError", "KeyError", "RuntimeError", "TimeoutError",
                  "ConnectionError", "FileNotFoundError", "subprocess"):
        if known.lower() in lower:
            return known
    return "other"


def _iter_order_rows():
    """Yield order JSON dicts. Skips non-order files and unreadable rows."""
    if not ORDERS_DIR.exists():
        return
    for p in ORDERS_DIR.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        # Skip engine output files — those end with _output.json
        if p.name.endswith("_output.json"):
            continue
        try:
            yield json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue


def compute_snapshot(now: Optional[datetime] = None) -> dict:
    """Walk the order store and return a PII-free aggregate snapshot.

    Return shape (stable — used by /admin UI):
      {
        "generated_at": ISO timestamp (UTC),
        "orders": {
          "total": int,
          "by_status": {status: count, ... with <5 buckets collapsed},
          "by_age": {bucket: count},
          "by_lang": {lang: count, with <5 collapsed},
          "error_categories": {category: count},
        },
        "tier2_files": {
          "orders_json": int,
          "readings_html": int,
          "unified_html": int,
        },
        "deletion_queue": {
          "pending": int,
        },
        "health": {
          "oldest_order_age_bucket": str,
          "ready_rate_pct": float | None,  # only if total >= MIN_BUCKET_SIZE
        }
      }
    """
    now = now or datetime.now(timezone.utc)

    status_counts: Counter = Counter()
    age_counts: Counter = Counter()
    lang_counts: Counter = Counter()
    error_counts: Counter = Counter()
    oldest_bucket = "today"
    BUCKET_ORDER = ["today", "1-7d", "8-30d", ">30d", "unknown"]
    ready = 0
    total = 0

    for row in _iter_order_rows():
        total += 1
        status_counts[row.get("status", "unknown")] += 1
        bucket = _age_bucket(row.get("created_at", ""), now=now)
        age_counts[bucket] += 1
        if BUCKET_ORDER.index(bucket) > BUCKET_ORDER.index(oldest_bucket):
            oldest_bucket = bucket
        lang_counts[row.get("lang", "unknown")] += 1
        error_counts[_error_category(row.get("error"))] += 1
        if row.get("status") == "ready":
            ready += 1

    # Count Tier 2 artifact files directly — detects orphans (files with
    # no matching order row, from manual deletions or crashes)
    orders_json = 0
    if ORDERS_DIR.exists():
        orders_json = sum(
            1 for p in ORDERS_DIR.iterdir()
            if p.is_file() and p.name.endswith("_output.json")
        )
    readings_html = 0
    unified_html = 0
    if READINGS_DIR.exists():
        for p in READINGS_DIR.iterdir():
            if not p.is_file() or p.suffix != ".html":
                continue
            if p.name.endswith("_unified.html"):
                unified_html += 1
            else:
                readings_html += 1

    # Deletion queue depth
    deletion_pending = 0
    if DELETION_QUEUE.exists():
        try:
            deletion_pending = sum(
                1 for line in DELETION_QUEUE.read_text().splitlines()
                if line.strip()
            )
        except OSError:
            pass

    # Ready-rate: only disclose if we have enough orders to avoid
    # single-customer inference
    ready_rate = None
    if total >= MIN_BUCKET_SIZE:
        ready_rate = round(100 * ready / total, 1)

    return {
        "generated_at": now.isoformat(),
        "orders": {
            "total": total,
            "by_status": _k_anon(status_counts),
            "by_age": dict(age_counts),  # age buckets are coarse, no k-anon needed
            "by_lang": _k_anon(lang_counts),
            "error_categories": _k_anon(error_counts),
        },
        "tier2_files": {
            "orders_json": orders_json,
            "readings_html": readings_html,
            "unified_html": unified_html,
        },
        "deletion_queue": {
            "pending": deletion_pending,
        },
        "health": {
            "oldest_order_age_bucket": oldest_bucket if total > 0 else "none",
            "ready_rate_pct": ready_rate,
        },
    }
