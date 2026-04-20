"""In-process retention scheduler.

Runs retention.purge_cycle() periodically inside the web service. No
separate Railway cron service, no APScheduler dep — just an asyncio task
started at app launch and cancelled on shutdown.

Gated by SIRR_IN_PROCESS_CRON=1. Default OFF so adding this module is a
no-op until an operator flips the switch in Railway env vars.

Runs once at SCHEDULER_INTERVAL_SECONDS intervals (default 24h = 86400s).
First run is delayed by SCHEDULER_STARTUP_DELAY_SECONDS (default 60s) so
a burst of container restarts doesn't thrash the purge.

Caveats:
- Single-replica assumption. If Railway ever scales to >1 web replica,
  the purges will run in all of them at once. Safe (purge is idempotent)
  but wasteful. Migrate to a dedicated cron service at that point.
- Shares the web service's event loop. Purge is I/O-bound file walking,
  so it won't block request handling noticeably, but a truly massive
  data directory could introduce latency. Monitor /api/internal/metrics
  after enabling.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Optional

# Defaults
DEFAULT_INTERVAL = 24 * 60 * 60  # 24 hours
DEFAULT_STARTUP_DELAY = 60  # 1 minute


def _is_enabled() -> bool:
    return os.environ.get("SIRR_IN_PROCESS_CRON", "").lower() in ("1", "true", "yes")


def _log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{stamp} [in-process-cron] {msg}", file=sys.stderr)


def _get_interval() -> int:
    try:
        return max(60, int(os.environ.get("SIRR_CRON_INTERVAL_SECONDS", DEFAULT_INTERVAL)))
    except ValueError:
        return DEFAULT_INTERVAL


def _get_startup_delay() -> int:
    try:
        return max(0, int(os.environ.get("SIRR_CRON_STARTUP_DELAY_SECONDS", DEFAULT_STARTUP_DELAY)))
    except ValueError:
        return DEFAULT_STARTUP_DELAY


async def _purge_loop() -> None:
    """Main scheduler loop. Runs forever until cancelled."""
    interval = _get_interval()
    startup_delay = _get_startup_delay()
    _log(f"started — startup_delay={startup_delay}s interval={interval}s")

    # Initial delay so container restarts don't stampede
    try:
        await asyncio.sleep(startup_delay)
    except asyncio.CancelledError:
        _log("cancelled during startup delay")
        raise

    while True:
        try:
            # Run the blocking purge in a thread so we don't stall the event loop
            from retention import purge_cycle
            summary = await asyncio.to_thread(purge_cycle)
            _log(f"run ok: {summary}")
        except asyncio.CancelledError:
            _log("cancelled mid-cycle")
            raise
        except Exception as e:
            # Never let one bad run kill the loop
            _log(f"run failed: {type(e).__name__} (continuing)")

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            _log("cancelled during sleep")
            raise


_task: Optional[asyncio.Task] = None


def start() -> Optional[asyncio.Task]:
    """Start the scheduler if enabled. Safe to call multiple times.
    Returns the task handle or None if disabled."""
    global _task
    if not _is_enabled():
        _log("disabled (set SIRR_IN_PROCESS_CRON=1 to enable)")
        return None
    if _task is not None and not _task.done():
        _log("already running")
        return _task
    _task = asyncio.create_task(_purge_loop(), name="sirr-retention-cron")
    return _task


async def stop() -> None:
    """Cancel the scheduler task if running. Called on app shutdown."""
    global _task
    if _task is None or _task.done():
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    _log("stopped")
