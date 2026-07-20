"""Typed transaction modes shared by data services and application layers."""

from __future__ import annotations

from enum import StrEnum


class DataTransactionMode(StrEnum):
    """SQLite transaction modes supported by the public data boundary."""

    DEFERRED = "DEFERRED"
    IMMEDIATE = "IMMEDIATE"
