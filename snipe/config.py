from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EventConfig:
    url: str
    sale_time: datetime


@dataclass(frozen=True)
class Participant:
    name: str
    id_number: str
    nationality: str = "Taiwan"


@dataclass(frozen=True)
class Preferences:
    ticket_count: int
    zone_priority: list[str]
    seat_allocation: str
    pickup: str
    payment: str
    participants: list[Participant] = field(default_factory=list)
    session_keyword: str | None = None


@dataclass(frozen=True)
class StateConfig:
    storage_state_path: Path


@dataclass(frozen=True)
class Config:
    event: EventConfig
    preferences: Preferences
    state: StateConfig
    lead_seconds: int


ALLOWED_SEAT_ALLOCATION = {"電腦選位", "自行選位"}
ALLOWED_PAYMENT = {"信用卡", "ATM"}


def _require(d: dict, key: str, where: str):
    if key not in d:
        raise ConfigError(f"{where}: 缺少必填欄位 '{key}'")
    return d[key]


def _parse_sale_time(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"event.sale_time 不是合法 ISO 8601 格式: {raw!r}") from e
    if dt.tzinfo is None:
        raise ConfigError("event.sale_time 必須包含時區（例如 +08:00）")
    return dt


def load(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"找不到設定檔: {p}")

    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("設定檔最外層必須是 mapping (key: value)")

    event_raw = _require(raw, "event", "config")
    preferences_raw = _require(raw, "preferences", "config")
    state_raw = _require(raw, "state", "config")

    event = EventConfig(
        url=_require(event_raw, "url", "event"),
        sale_time=_parse_sale_time(_require(event_raw, "sale_time", "event")),
    )

    ticket_count = _require(preferences_raw, "ticket_count", "preferences")
    if ticket_count != 1:
        raise ConfigError("目前只支援 ticket_count = 1")

    zone_priority = _require(preferences_raw, "zone_priority", "preferences")
    if not isinstance(zone_priority, list) or not zone_priority:
        raise ConfigError("preferences.zone_priority 必須是非空陣列")
    if not all(isinstance(z, str) and z.strip() for z in zone_priority):
        raise ConfigError("preferences.zone_priority 內每個元素必須是非空字串")

    seat_allocation = _require(preferences_raw, "seat_allocation", "preferences")
    if seat_allocation not in ALLOWED_SEAT_ALLOCATION:
        raise ConfigError(
            f"preferences.seat_allocation 必須是 {ALLOWED_SEAT_ALLOCATION}，得到 {seat_allocation!r}"
        )

    payment = _require(preferences_raw, "payment", "preferences")
    if payment not in ALLOWED_PAYMENT:
        raise ConfigError(
            f"preferences.payment 必須是 {ALLOWED_PAYMENT}，得到 {payment!r}"
        )

    session_keyword = preferences_raw.get("session_keyword")
    if session_keyword is not None and not isinstance(session_keyword, str):
        raise ConfigError("preferences.session_keyword 必須是字串")
    if isinstance(session_keyword, str):
        session_keyword = session_keyword.strip() or None

    participants_raw = preferences_raw.get("participants", []) or []
    if not isinstance(participants_raw, list):
        raise ConfigError("preferences.participants 必須是陣列")
    participants: list[Participant] = []
    for idx, p in enumerate(participants_raw):
        if not isinstance(p, dict):
            raise ConfigError(f"preferences.participants[{idx}] 必須是 mapping")
        name = p.get("name")
        id_number = p.get("id_number")
        nationality = p.get("nationality", "Taiwan")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"preferences.participants[{idx}].name 必須是非空字串")
        if not isinstance(id_number, str) or not id_number.strip():
            raise ConfigError(f"preferences.participants[{idx}].id_number 必須是非空字串")
        if not isinstance(nationality, str) or not nationality.strip():
            raise ConfigError(f"preferences.participants[{idx}].nationality 必須是非空字串")
        participants.append(Participant(name=name.strip(), id_number=id_number.strip(),
                                        nationality=nationality.strip()))

    # 若有設定 participants，數量必須 >= ticket_count（實名制需要每張票一份）
    if participants and len(participants) < ticket_count:
        raise ConfigError(
            f"preferences.participants 數量 ({len(participants)}) 不能少於 ticket_count ({ticket_count})"
        )

    preferences = Preferences(
        ticket_count=ticket_count,
        zone_priority=list(zone_priority),
        seat_allocation=seat_allocation,
        pickup=_require(preferences_raw, "pickup", "preferences"),
        payment=payment,
        participants=participants,
        session_keyword=session_keyword,
    )

    state = StateConfig(
        storage_state_path=Path(_require(state_raw, "storage_state_path", "state")),
    )

    lead_seconds = raw.get("lead_seconds", 3)
    if not isinstance(lead_seconds, int) or lead_seconds < 0:
        raise ConfigError("lead_seconds 必須是非負整數")

    return Config(
        event=event,
        preferences=preferences,
        state=state,
        lead_seconds=lead_seconds,
    )
