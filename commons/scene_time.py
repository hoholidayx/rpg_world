"""Structured scene time shared across data, Agent, and Play boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Mapping

_SCENE_TIME_RE = re.compile(
    r"^\s*第\s*(?P<year>\d+)\s*年\s*"
    r"(?P<month>\d+)\s*月\s*"
    r"(?P<day>\d+)\s*日\s*"
    r"(?P<hour>\d+)\s*时"
    r"(?:\s*(?P<minute>\d+)\s*分)?\s*$"
)


@dataclass(frozen=True, order=True)
class SceneTime:
    """One point on the product's fixed 12-month, 31-day scene calendar."""

    year: int
    month: int
    day: int
    hour: int
    minute: int = 0

    def __post_init__(self) -> None:
        values = (self.year, self.month, self.day, self.hour, self.minute)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("SceneTime fields must be integers")
        if self.year < 1:
            raise ValueError("SceneTime year must be at least 1")
        if not 1 <= self.month <= 12:
            raise ValueError("SceneTime month must be between 1 and 12")
        if not 1 <= self.day <= 31:
            raise ValueError("SceneTime day must be between 1 and 31")
        if not 0 <= self.hour <= 23:
            raise ValueError("SceneTime hour must be between 0 and 23")
        if not 0 <= self.minute <= 59:
            raise ValueError("SceneTime minute must be between 0 and 59")

    @classmethod
    def parse(cls, value: str) -> "SceneTime":
        match = _SCENE_TIME_RE.fullmatch(str(value or ""))
        if match is None:
            raise ValueError("scene time must match '第 Y 年 M 月 D 日 H 时 [M 分]'")
        return cls(**{
            key: int(raw) if raw is not None else 0
            for key, raw in match.groupdict().items()
        })

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "SceneTime":
        required = ("year", "month", "day", "hour")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"SceneTime is missing fields: {', '.join(missing)}")
        return cls(
            year=_integer(value["year"], "year"),
            month=_integer(value["month"], "month"),
            day=_integer(value["day"], "day"),
            hour=_integer(value["hour"], "hour"),
            minute=_integer(value.get("minute", 0), "minute"),
        )

    def update(self, **values: int) -> "SceneTime":
        unexpected = sorted(set(values) - {"year", "month", "day", "hour", "minute"})
        if unexpected:
            raise ValueError(f"unsupported SceneTime fields: {unexpected}")
        return replace(
            self,
            **{key: _integer(value, key) for key, value in values.items()},
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "hour": self.hour,
            "minute": self.minute,
        }

    def format(self) -> str:
        value = f"第 {self.year} 年 {self.month} 月 {self.day} 日 {self.hour} 时"
        return f"{value} {self.minute} 分" if self.minute else value

    @property
    def ordinal_minutes(self) -> int:
        days = ((self.year - 1) * 12 + (self.month - 1)) * 31 + (self.day - 1)
        return ((days * 24) + self.hour) * 60 + self.minute

    def elapsed_minutes_since(self, earlier: "SceneTime") -> int:
        return self.ordinal_minutes - earlier.ordinal_minutes


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"SceneTime {field} must be an integer")
    return value
