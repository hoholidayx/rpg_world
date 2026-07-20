"""Business-neutral errors exposed by the data boundary."""

from __future__ import annotations


class DataServiceError(RuntimeError):
    """Base class for deterministic persistence-boundary failures."""


class DataIntegrityError(DataServiceError):
    """A write was rejected by persisted integrity constraints."""


class DataConditionalWriteError(DataServiceError):
    """A conditional update no longer matched its expected row version."""
