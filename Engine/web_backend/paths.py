"""Centralized data-path configuration.

Controls where user-data (orders, readings, deletion queue) lives on disk.

Default (SIRR_DATA_DIR unset): paths resolve next to web_backend code —
the legacy layout. Local dev, CI, and any Railway deploy without a volume
mount fall into this path.

Production (SIRR_DATA_DIR=/data): all user data lands in the mount point.
Set this env var to the Railway volume mount target. Deploys can then
come and go without wiping customer data.

Single source of truth:
    ORDERS_DIR       — per-order JSON rows + engine output files
    READINGS_DIR     — rendered HTML readings (legacy + unified)
    DELETION_QUEUE   — right-to-delete append-only file

Other modules import these names and use them — tests may rebind the
module attributes (e.g., metrics.ORDERS_DIR = tmp/...) for isolation.
"""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent  # Engine/web_backend

_configured = os.environ.get("SIRR_DATA_DIR", "").strip()
DATA_DIR: Path = Path(_configured) if _configured else _BACKEND_DIR

ORDERS_DIR: Path = DATA_DIR / "orders"
READINGS_DIR: Path = DATA_DIR / "readings"
DELETION_QUEUE: Path = DATA_DIR / "deletion_queue.txt"

# Ensure directories exist at import time (idempotent, safe on read-only FS
# as long as the configured path is writable — which is the whole point
# of attaching the volume).
ORDERS_DIR.mkdir(parents=True, exist_ok=True)
READINGS_DIR.mkdir(parents=True, exist_ok=True)
