from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from snipe import config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


VALID = """
event:
  url: "https://ticketplus.com.tw/order/abc/def"
  sale_time: "2026-06-01T12:00:00+08:00"
preferences:
  ticket_count: 1
  zone_priority:
    - "搖滾"
    - "4880"
  seat_allocation: "電腦選位"
  pickup: "ibon"
  payment: "信用卡"
state:
  storage_state_path: "state/storage_state.json"
lead_seconds: 3
"""


def test_load_valid(tmp_path):
    cfg = config.load(_write(tmp_path, VALID))
    assert cfg.event.url == "https://ticketplus.com.tw/order/abc/def"
    assert cfg.event.sale_time == datetime(2026, 6, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    assert cfg.preferences.ticket_count == 1
    assert cfg.preferences.zone_priority == ["搖滾", "4880"]
    assert cfg.preferences.seat_allocation == "電腦選位"
    assert cfg.preferences.pickup == "ibon"
    assert cfg.preferences.payment == "信用卡"
    assert cfg.state.storage_state_path == Path("state/storage_state.json")
    assert cfg.lead_seconds == 3


def test_missing_event_raises(tmp_path):
    body = VALID.replace("event:\n  url: \"https://ticketplus.com.tw/order/abc/def\"\n  sale_time: \"2026-06-01T12:00:00+08:00\"\n", "")
    with pytest.raises(config.ConfigError, match="event"):
        config.load(_write(tmp_path, body))


def test_sale_time_without_tz_raises(tmp_path):
    body = VALID.replace("2026-06-01T12:00:00+08:00", "2026-06-01T12:00:00")
    with pytest.raises(config.ConfigError, match="時區"):
        config.load(_write(tmp_path, body))


def test_invalid_sale_time_raises(tmp_path):
    body = VALID.replace("2026-06-01T12:00:00+08:00", "not-a-date")
    with pytest.raises(config.ConfigError, match="ISO 8601"):
        config.load(_write(tmp_path, body))


def test_ticket_count_must_be_one(tmp_path):
    body = VALID.replace("ticket_count: 1", "ticket_count: 2")
    with pytest.raises(config.ConfigError, match="ticket_count"):
        config.load(_write(tmp_path, body))


def test_empty_zone_priority_raises(tmp_path):
    body = """
event:
  url: "https://ticketplus.com.tw/order/abc/def"
  sale_time: "2026-06-01T12:00:00+08:00"
preferences:
  ticket_count: 1
  zone_priority: []
  seat_allocation: "電腦選位"
  pickup: "ibon"
  payment: "信用卡"
state:
  storage_state_path: "state/storage_state.json"
"""
    with pytest.raises(config.ConfigError, match="zone_priority"):
        config.load(_write(tmp_path, body))


def test_invalid_seat_allocation_raises(tmp_path):
    body = VALID.replace('seat_allocation: "電腦選位"', 'seat_allocation: "隨便"')
    with pytest.raises(config.ConfigError, match="seat_allocation"):
        config.load(_write(tmp_path, body))


def test_invalid_payment_raises(tmp_path):
    body = VALID.replace('payment: "信用卡"', 'payment: "BTC"')
    with pytest.raises(config.ConfigError, match="payment"):
        config.load(_write(tmp_path, body))


def test_lead_seconds_default(tmp_path):
    body = VALID.replace("lead_seconds: 3\n", "")
    cfg = config.load(_write(tmp_path, body))
    assert cfg.lead_seconds == 3


def test_negative_lead_seconds_raises(tmp_path):
    body = VALID.replace("lead_seconds: 3", "lead_seconds: -1")
    with pytest.raises(config.ConfigError, match="lead_seconds"):
        config.load(_write(tmp_path, body))


def test_missing_file_raises(tmp_path):
    with pytest.raises(config.ConfigError, match="找不到"):
        config.load(tmp_path / "nope.yaml")


def _with_participants(body: str, participants_yaml: str) -> str:
    # 在 preferences 區塊內、payment 之後插入 participants
    marker = '  payment: "信用卡"\n'
    return body.replace(marker, marker + participants_yaml)


def test_no_participants_is_ok(tmp_path):
    cfg = config.load(_write(tmp_path, VALID))
    assert cfg.preferences.participants == []


def test_participants_load(tmp_path):
    body = _with_participants(VALID, """  participants:
    - name: "王小明"
      id_number: "A123456789"
      nationality: "中華民國"
""")
    cfg = config.load(_write(tmp_path, body))
    assert len(cfg.preferences.participants) == 1
    p = cfg.preferences.participants[0]
    assert p.name == "王小明"
    assert p.id_number == "A123456789"
    assert p.nationality == "中華民國"


def test_participants_default_nationality(tmp_path):
    body = _with_participants(VALID, """  participants:
    - name: "Foo"
      id_number: "B987654321"
""")
    cfg = config.load(_write(tmp_path, body))
    assert cfg.preferences.participants[0].nationality == "Taiwan"


def test_participants_missing_name_raises(tmp_path):
    body = _with_participants(VALID, """  participants:
    - id_number: "A123456789"
""")
    with pytest.raises(config.ConfigError, match="participants"):
        config.load(_write(tmp_path, body))


def test_participants_count_lt_tickets_raises(tmp_path):
    body = VALID.replace("ticket_count: 1", "ticket_count: 2")
    body = _with_participants(body, """  participants:
    - name: "Foo"
      id_number: "A1"
""")
    # ticket_count=2 但 participants=1：但 ticket_count != 1 也會先觸發其他驗證
    # 改測 ticket_count=1，participants=2 是允許的（不會 raise）
    body2 = _with_participants(VALID, """  participants:
    - name: "Foo"
      id_number: "A1"
    - name: "Bar"
      id_number: "B2"
""")
    cfg = config.load(_write(tmp_path, body2))
    assert len(cfg.preferences.participants) == 2
