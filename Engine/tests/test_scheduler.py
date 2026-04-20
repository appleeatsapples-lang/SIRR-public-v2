"""Tests for scheduler.py — in-process retention loop."""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))


def _reimport():
    for mod in ("scheduler",):
        if mod in sys.modules:
            del sys.modules[mod]
    import scheduler
    return scheduler


def test_disabled_by_default():
    os.environ.pop("SIRR_IN_PROCESS_CRON", None)
    scheduler = _reimport()
    assert not scheduler._is_enabled()
    assert scheduler.start() is None


def test_enabled_by_env():
    os.environ["SIRR_IN_PROCESS_CRON"] = "1"
    try:
        scheduler = _reimport()
        assert scheduler._is_enabled()
    finally:
        os.environ.pop("SIRR_IN_PROCESS_CRON", None)


def test_interval_default():
    os.environ.pop("SIRR_CRON_INTERVAL_SECONDS", None)
    scheduler = _reimport()
    assert scheduler._get_interval() == scheduler.DEFAULT_INTERVAL


def test_interval_override():
    os.environ["SIRR_CRON_INTERVAL_SECONDS"] = "600"
    try:
        scheduler = _reimport()
        assert scheduler._get_interval() == 600
    finally:
        os.environ.pop("SIRR_CRON_INTERVAL_SECONDS", None)


def test_interval_floor_60s():
    # Can't configure below 60s — DoS guard
    os.environ["SIRR_CRON_INTERVAL_SECONDS"] = "5"
    try:
        scheduler = _reimport()
        assert scheduler._get_interval() == 60
    finally:
        os.environ.pop("SIRR_CRON_INTERVAL_SECONDS", None)


def test_interval_handles_garbage():
    os.environ["SIRR_CRON_INTERVAL_SECONDS"] = "not-a-number"
    try:
        scheduler = _reimport()
        assert scheduler._get_interval() == scheduler.DEFAULT_INTERVAL
    finally:
        os.environ.pop("SIRR_CRON_INTERVAL_SECONDS", None)


def test_startup_delay_clamped_nonneg():
    os.environ["SIRR_CRON_STARTUP_DELAY_SECONDS"] = "-100"
    try:
        scheduler = _reimport()
        assert scheduler._get_startup_delay() == 0
    finally:
        os.environ.pop("SIRR_CRON_STARTUP_DELAY_SECONDS", None)


@pytest.mark.asyncio
async def test_start_returns_task_when_enabled():
    os.environ["SIRR_IN_PROCESS_CRON"] = "1"
    os.environ["SIRR_CRON_STARTUP_DELAY_SECONDS"] = "3600"  # never fires
    try:
        scheduler = _reimport()
        task = scheduler.start()
        assert task is not None
        assert not task.done()
        await scheduler.stop()
        assert task.done() or task.cancelled()
    finally:
        os.environ.pop("SIRR_IN_PROCESS_CRON", None)
        os.environ.pop("SIRR_CRON_STARTUP_DELAY_SECONDS", None)


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    scheduler = _reimport()
    # No task running — stop should be a no-op
    await scheduler.stop()
    await scheduler.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent_when_running():
    os.environ["SIRR_IN_PROCESS_CRON"] = "1"
    os.environ["SIRR_CRON_STARTUP_DELAY_SECONDS"] = "3600"
    try:
        scheduler = _reimport()
        t1 = scheduler.start()
        t2 = scheduler.start()  # already running
        assert t1 is t2  # same task
        await scheduler.stop()
    finally:
        os.environ.pop("SIRR_IN_PROCESS_CRON", None)
        os.environ.pop("SIRR_CRON_STARTUP_DELAY_SECONDS", None)
