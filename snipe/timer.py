from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone

import ntplib

log = logging.getLogger(__name__)

NTP_HOST = "time.stdtime.gov.tw"


def sync_ntp(host: str = NTP_HOST, timeout: float = 3.0) -> float:
    """Return offset = ntp_time - local_time (seconds). Positive means local clock is slow."""
    client = ntplib.NTPClient()
    try:
        resp = client.request(host, version=3, timeout=timeout)
    except Exception as e:
        log.warning("NTP 對時失敗（%s），使用本機時間：%s", host, e)
        return 0.0
    return resp.offset


def _now_with_offset(offset: float) -> datetime:
    return datetime.fromtimestamp(time.time() + offset, tz=timezone.utc)


def sleep_until(target: datetime, lead_seconds: int, offset: float = 0.0) -> None:
    """Block until target - lead_seconds. Prints countdown every second."""
    if target.tzinfo is None:
        raise ValueError("target datetime must be timezone-aware")

    fire_at = target.timestamp() - lead_seconds
    while True:
        now = time.time() + offset
        remaining = fire_at - now
        if remaining <= 0:
            return
        if remaining > 60:
            sys.stdout.write(f"\r距離開賣還有 {int(remaining)} 秒（含 {lead_seconds}s 提前）  ")
            sys.stdout.flush()
            time.sleep(min(remaining - 60, 5))
        elif remaining > 5:
            sys.stdout.write(f"\r距離開賣還有 {remaining:5.1f} 秒  ")
            sys.stdout.flush()
            time.sleep(0.5)
        else:
            sys.stdout.write(f"\r距離開賣還有 {remaining:5.2f} 秒  ")
            sys.stdout.flush()
            time.sleep(0.05)
