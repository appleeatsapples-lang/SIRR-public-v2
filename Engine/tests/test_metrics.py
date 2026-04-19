"""Tests for metrics.py — zero-knowledge aggregate snapshot (§16.3).

Uses monkeypatch on the module's ORDERS_DIR/READINGS_DIR/DELETION_QUEUE
to point at a tempdir with synthetic order rows. Verifies k-anonymity,
age bucketing, and the no-PII contract.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
import metrics  # noqa: E402


def _setup_tempdir(tmp: Path, rows: list, readings: list = None,
                   unified: list = None, outputs: list = None,
                   deletion_queue_lines: list = None):
    """Populate a synthetic order store layout under `tmp`."""
    orders = tmp / "orders"
    orders.mkdir()
    readings_dir = tmp / "readings"
    readings_dir.mkdir()

    for row in rows:
        (orders / f"{row['order_id']}.json").write_text(json.dumps(row))
    for name in (outputs or []):
        (orders / name).write_text("{}")
    for name in (readings or []):
        (readings_dir / name).write_text("<html></html>")
    for name in (unified or []):
        (readings_dir / name).write_text("<html></html>")

    if deletion_queue_lines is not None:
        (tmp / "deletion_queue.txt").write_text("\n".join(deletion_queue_lines) + "\n")

    # Point module at tempdir
    metrics.ORDERS_DIR = orders
    metrics.READINGS_DIR = readings_dir
    metrics.DELETION_QUEUE = tmp / "deletion_queue.txt"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_empty_store_returns_zeros():
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=[])
        snap = metrics.compute_snapshot()
    assert snap["orders"]["total"] == 0
    assert snap["tier2_files"]["orders_json"] == 0
    assert snap["deletion_queue"]["pending"] == 0
    assert snap["health"]["ready_rate_pct"] is None
    assert snap["health"]["oldest_order_age_bucket"] == "none"


def test_counts_correctly():
    now = datetime.now(timezone.utc)
    rows = [
        {"order_id": f"ord{i}", "status": "ready", "created_at": _iso(now),
         "lang": "en", "error": None}
        for i in range(10)
    ]
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["total"] == 10
    assert snap["orders"]["by_status"] == {"ready": 10}
    assert snap["orders"]["by_age"] == {"today": 10}
    assert snap["health"]["ready_rate_pct"] == 100.0


def test_k_anonymity_collapses_rare_buckets():
    """If a status has only 2 orders (below MIN_BUCKET_SIZE=5), it should
    collapse into '<5' rather than surfacing the exact count."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(8):  # 8 ready
        rows.append({"order_id": f"r{i}", "status": "ready", "created_at": _iso(now), "lang": "en"})
    for i in range(2):  # 2 failed — should be hidden
        rows.append({"order_id": f"f{i}", "status": "failed", "created_at": _iso(now), "lang": "en"})
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["by_status"]["ready"] == 8
    assert "failed" not in snap["orders"]["by_status"]
    assert snap["orders"]["by_status"]["<5"] == 2


def test_ready_rate_hidden_when_total_below_threshold():
    """With fewer than MIN_BUCKET_SIZE total orders, don't publish a
    percentage — it leaks too much info about the business."""
    now = datetime.now(timezone.utc)
    rows = [{"order_id": f"o{i}", "status": "ready", "created_at": _iso(now), "lang": "en"}
            for i in range(3)]
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["total"] == 3
    assert snap["health"]["ready_rate_pct"] is None


def test_age_buckets():
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {"order_id": "t", "status": "ready", "created_at": _iso(now - timedelta(hours=3)), "lang": "en"},
        {"order_id": "w1", "status": "ready", "created_at": _iso(now - timedelta(days=3)), "lang": "en"},
        {"order_id": "w2", "status": "ready", "created_at": _iso(now - timedelta(days=6)), "lang": "en"},
        {"order_id": "m", "status": "ready", "created_at": _iso(now - timedelta(days=15)), "lang": "en"},
        {"order_id": "old", "status": "ready", "created_at": _iso(now - timedelta(days=45)), "lang": "en"},
    ]
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["by_age"]["today"] == 1
    assert snap["orders"]["by_age"]["1-7d"] == 2
    assert snap["orders"]["by_age"]["8-30d"] == 1
    assert snap["orders"]["by_age"][">30d"] == 1
    assert snap["health"]["oldest_order_age_bucket"] == ">30d"


def test_tier2_file_counting():
    now = datetime.now(timezone.utc)
    rows = [{"order_id": "o1", "status": "ready", "created_at": _iso(now), "lang": "en"}]
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(
            Path(td), rows=rows,
            outputs=["o1_output.json", "o2_output.json"],
            readings=["o1.html", "o2.html", "o3.html"],
            unified=["o1_unified.html", "o2_unified.html"],
        )
        snap = metrics.compute_snapshot(now=now)
    assert snap["tier2_files"]["orders_json"] == 2
    assert snap["tier2_files"]["readings_html"] == 3
    assert snap["tier2_files"]["unified_html"] == 2


def test_deletion_queue_depth():
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(
            Path(td), rows=[],
            deletion_queue_lines=["ord_a", "ord_b", "ord_c"],
        )
        snap = metrics.compute_snapshot(now=now)
    assert snap["deletion_queue"]["pending"] == 3


def test_no_pii_anywhere_in_snapshot():
    """Critical contract: compute_snapshot must NEVER return order_ids,
    names, DOBs, or emails. Walk the entire response structure and
    assert none of those fields' known strings leak."""
    now = datetime.now(timezone.utc)
    rows = [
        {"order_id": "fatima-alkatib-15mar1990-a7f3", "status": "ready",
         "created_at": _iso(now), "name_latin": "FATIMA ALKATIB",
         "dob": "1990-03-15", "lang": "en", "email": "test@example.com"}
        for _ in range(10)
    ]
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    # Stringify the whole snapshot, then grep for PII patterns
    serialized = json.dumps(snap).lower()
    for forbidden in ("fatima", "alkatib", "1990-03-15", "test@example.com",
                      "15mar1990", "a7f3"):
        assert forbidden not in serialized, f"PII '{forbidden}' leaked into snapshot"


def test_error_category_bucketing():
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(5):
        rows.append({"order_id": f"v{i}", "status": "failed",
                     "error": "Traceback...\nValueError: <message-redacted>",
                     "created_at": _iso(now), "lang": "en"})
    for i in range(5):
        rows.append({"order_id": f"r{i}", "status": "failed",
                     "error": "Traceback...\nRuntimeError: <message-redacted>",
                     "created_at": _iso(now), "lang": "en"})
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=rows)
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["error_categories"]["ValueError"] == 5
    assert snap["orders"]["error_categories"]["RuntimeError"] == 5


def test_ignores_nonjson_files_in_orders_dir():
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        _setup_tempdir(Path(td), rows=[])
        (Path(td) / "orders" / "stray.txt").write_text("not json")
        (Path(td) / "orders" / ".DS_Store").write_bytes(b"\x00\x01")
        snap = metrics.compute_snapshot(now=now)
    assert snap["orders"]["total"] == 0
