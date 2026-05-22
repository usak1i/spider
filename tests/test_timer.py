from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pytest

from snipe import timer


def test_sleep_until_returns_when_target_passed():
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    start = time.time()
    timer.sleep_until(past, lead_seconds=0)
    assert time.time() - start < 0.1


def test_sleep_until_blocks_near_target():
    target = datetime.now(timezone.utc) + timedelta(seconds=0.3)
    start = time.time()
    timer.sleep_until(target, lead_seconds=0)
    elapsed = time.time() - start
    assert 0.15 <= elapsed <= 0.6, f"elapsed={elapsed}"


def test_sleep_until_respects_lead_seconds():
    target = datetime.now(timezone.utc) + timedelta(seconds=0.5)
    start = time.time()
    timer.sleep_until(target, lead_seconds=1)
    elapsed = time.time() - start
    assert elapsed < 0.1


def test_sleep_until_requires_tz():
    naive = datetime.now()
    with pytest.raises(ValueError, match="timezone-aware"):
        timer.sleep_until(naive, lead_seconds=0)


def test_sync_ntp_returns_float():
    offset = timer.sync_ntp(timeout=1.0)
    assert isinstance(offset, float)
