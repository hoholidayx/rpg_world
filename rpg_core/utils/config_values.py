"""Small coercion helpers for YAML configuration values."""

from __future__ import annotations

from typing import Any


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}


def optional_bool(value: Any, default: bool | None = None) -> bool | None:
    """Return a bool for common YAML/string forms, or *default* when unset."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
    return default


def optional_int(value: Any, default: int | None = None) -> int | None:
    """Return an int when *value* is parseable, otherwise *default*."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def optional_float(value: Any, default: float | None = None) -> float | None:
    """Return a float when *value* is parseable, otherwise *default*."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def forgiving_int(value: Any, default: int) -> int:
    """Return parsed int or *default* for invalid config values."""
    parsed = optional_int(value, default)
    return default if parsed is None else parsed


def forgiving_float(value: Any, default: float) -> float:
    """Return parsed float or *default* for invalid config values."""
    parsed = optional_float(value, default)
    return default if parsed is None else parsed
