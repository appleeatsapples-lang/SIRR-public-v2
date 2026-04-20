"""Tests for paths.py — SIRR_DATA_DIR env var honored.

This is the fix for the ephemeral-filesystem issue. These tests are
the regression guard: if someone refactors paths.py and accidentally
hardcodes a path, these fail loud.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path


def _fresh_import():
    """Force re-import of paths module so it re-reads env vars."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
    if "paths" in sys.modules:
        del sys.modules["paths"]
    import paths  # noqa: E402
    return paths


def test_default_falls_back_to_backend_dir():
    """With SIRR_DATA_DIR unset, paths live next to web_backend code."""
    os.environ.pop("SIRR_DATA_DIR", None)
    paths = _fresh_import()
    backend = Path(paths.__file__).parent
    assert paths.DATA_DIR == backend
    assert paths.ORDERS_DIR == backend / "orders"
    assert paths.READINGS_DIR == backend / "readings"
    assert paths.DELETION_QUEUE == backend / "deletion_queue.txt"


def test_env_var_honored():
    """With SIRR_DATA_DIR set, all paths resolve under it."""
    with tempfile.TemporaryDirectory() as td:
        os.environ["SIRR_DATA_DIR"] = td
        try:
            paths = _fresh_import()
            assert paths.DATA_DIR == Path(td)
            assert paths.ORDERS_DIR == Path(td) / "orders"
            assert paths.READINGS_DIR == Path(td) / "readings"
            assert paths.DELETION_QUEUE == Path(td) / "deletion_queue.txt"
            # Directories auto-created
            assert paths.ORDERS_DIR.exists()
            assert paths.READINGS_DIR.exists()
        finally:
            os.environ.pop("SIRR_DATA_DIR", None)


def test_env_var_empty_string_treated_as_unset():
    """An empty/whitespace SIRR_DATA_DIR falls back to default."""
    os.environ["SIRR_DATA_DIR"] = "  "
    try:
        paths = _fresh_import()
        backend = Path(paths.__file__).parent
        assert paths.DATA_DIR == backend
    finally:
        os.environ.pop("SIRR_DATA_DIR", None)


def test_other_modules_see_configured_paths():
    """metrics, retention, order_store — all three should see the
    same DATA_DIR-rooted paths when SIRR_DATA_DIR is set."""
    with tempfile.TemporaryDirectory() as td:
        os.environ["SIRR_DATA_DIR"] = td
        try:
            # Reset everything — force fresh import of the chain
            for mod in ["paths", "metrics", "retention", "order_store"]:
                if mod in sys.modules:
                    del sys.modules[mod]
            import metrics
            import retention
            import order_store
            assert str(metrics.ORDERS_DIR).startswith(td)
            assert str(metrics.READINGS_DIR).startswith(td)
            assert str(retention.ORDERS_DIR).startswith(td)
            assert str(order_store.ORDERS_DIR).startswith(td)
        finally:
            os.environ.pop("SIRR_DATA_DIR", None)
            for mod in ["paths", "metrics", "retention", "order_store"]:
                if mod in sys.modules:
                    del sys.modules[mod]
