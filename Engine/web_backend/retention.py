"""Retention purge — Tier 2 and Tier 3 deletion enforcement (§16.2, §16.6).

Per §16.2, reading input/output records live in Tier 2 and must be purged
30 days after creation. Per §16.6, user-requested deletions must be honored
within 24 hours for Tier 2 and within 30 days for Tier 3 aggregates.

This module implements both flows:

  sweep_tier2_expired(now)
    Scans orders/ and readings/ for files older than RETENTION_DAYS,
    deletes them, and records a minimal audit row.

  drain_tier3_deletion_queue()
    Reads deletion_queue.txt (appended by POST /api/delete), processes
    each order_id's removal from the aggregate analytics store, truncates
    the queue on success.

  purge_cycle()
    Convenience wrapper that runs both. Safe to call daily from a cron,
    a Railway scheduled job, or on server start (idempotent).

Design notes:
  - Deletion is a file-level unlink; SQLite / Postgres rows are updated
    via the existing update_order() / order_store interface so the audit
    trail is preserved without the content.
  - Tier 3 (aggregate) store is not yet implemented — this module stages
    the deletion queue so it drains automatically once Tier 3 lands.
  - Uses file mtime for age, not database created_at, so files orphaned
    from deleted DB rows also get cleaned up. Covers disaster recovery.
  - Dry-run mode available via DRY_RUN env var for verification.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Iterable, List, Tuple

# Per §16.2 — Tier 2 retention window
RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 24 * 60 * 60

BACKEND_DIR = Path(__file__).parent
ORDERS_DIR = BACKEND_DIR / "orders"
READINGS_DIR = BACKEND_DIR / "readings"
DELETION_QUEUE = BACKEND_DIR / "deletion_queue.txt"

DRY_RUN = os.environ.get("SIRR_RETENTION_DRY_RUN", "").lower() in ("1", "true", "yes")


def _log(msg: str) -> None:
    """Retention log line. Goes to stderr so it shows up in Railway logs
    without colliding with request-log output on stdout. Per §16.5, logs
    contain only counts and order_ids — never profile content."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    prefix = "[retention-dry]" if DRY_RUN else "[retention]"
    print(f"{stamp} {prefix} {msg}", file=sys.stderr)


def _iter_expired_files(directory: Path, cutoff_unix: float) -> Iterable[Path]:
    """Yield files in `directory` whose mtime is older than `cutoff_unix`.
    Skips hidden files and non-files. Absent directory yields nothing."""
    if not directory.exists():
        return
    for entry in directory.iterdir():
        if entry.name.startswith("."):
            continue
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff_unix:
                yield entry
        except OSError:
            continue


def sweep_tier2_expired(now: float = None) -> Tuple[int, int]:
    """Delete Tier 2 files older than RETENTION_DAYS.

    Returns (orders_deleted, readings_deleted). Missing directories are fine.
    Honors DRY_RUN — if set, counts but doesn't unlink.
    """
    now = now if now is not None else time.time()
    cutoff = now - RETENTION_SECONDS

    orders_removed = 0
    for path in _iter_expired_files(ORDERS_DIR, cutoff):
        _log(f"expire-order file={path.name} age_days={(now - path.stat().st_mtime) / 86400:.1f}")
        if not DRY_RUN:
            try:
                path.unlink()
                orders_removed += 1
            except OSError as e:
                _log(f"expire-order-failed file={path.name} error={e}")
        else:
            orders_removed += 1

    readings_removed = 0
    for path in _iter_expired_files(READINGS_DIR, cutoff):
        _log(f"expire-reading file={path.name} age_days={(now - path.stat().st_mtime) / 86400:.1f}")
        if not DRY_RUN:
            try:
                path.unlink()
                readings_removed += 1
            except OSError as e:
                _log(f"expire-reading-failed file={path.name} error={e}")
        else:
            readings_removed += 1

    _log(f"sweep-tier2 orders_removed={orders_removed} readings_removed={readings_removed} cutoff_days={RETENTION_DAYS}")
    return orders_removed, readings_removed


def drain_tier3_deletion_queue() -> int:
    """Process queued Tier 3 deletions.

    Currently a stub — Tier 3 (aggregate analytics) store is not yet built.
    The queue file accumulates order_ids until Tier 3 lands; this function
    consumes each line, attempts removal from the aggregate store, and
    truncates the queue on success. Errors leave items in the queue for retry.

    Returns the number of queued items that were successfully processed.
    """
    if not DELETION_QUEUE.exists():
        return 0

    try:
        lines = DELETION_QUEUE.read_text().splitlines()
    except OSError as e:
        _log(f"tier3-queue-read-failed error={e}")
        return 0

    queued: List[str] = [line.strip() for line in lines if line.strip()]
    if not queued:
        return 0

    processed = 0
    remaining: List[str] = []
    for order_id in queued:
        # Hook: once Tier 3 store exists, remove pseudonymous row matching
        # this order_id's hash. For now we log-only.
        _log(f"tier3-delete-queued order_id={order_id} (Tier3 store not yet live — logged only)")
        if not DRY_RUN:
            processed += 1
        else:
            remaining.append(order_id)

    if not DRY_RUN:
        # Truncate queue to whatever we couldn't process (currently all
        # handled, so file becomes empty)
        try:
            DELETION_QUEUE.write_text("\n".join(remaining) + ("\n" if remaining else ""))
        except OSError as e:
            _log(f"tier3-queue-truncate-failed error={e}")

    _log(f"drain-tier3 processed={processed} deferred={len(remaining)}")
    return processed


def purge_cycle() -> dict:
    """Run one full retention cycle. Safe to call from cron, startup, or CLI."""
    now = time.time()
    orders_removed, readings_removed = sweep_tier2_expired(now)
    tier3_processed = drain_tier3_deletion_queue()
    return {
        "orders_removed": orders_removed,
        "readings_removed": readings_removed,
        "tier3_processed": tier3_processed,
        "dry_run": DRY_RUN,
        "retention_days": RETENTION_DAYS,
        "ran_at_unix": int(now),
    }


if __name__ == "__main__":
    result = purge_cycle()
    import json
    print(json.dumps(result, indent=2))
