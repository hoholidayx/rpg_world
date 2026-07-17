"""Domain errors raised by the Dream memory pipeline."""

from __future__ import annotations


class DreamError(Exception):
    """Base class for expected Dream failures."""


class DreamSourceError(DreamError):
    """The persisted source snapshot cannot be analyzed safely."""


class DreamModelContractError(DreamError):
    """The configured model did not satisfy the typed Dream contract."""


class DreamAlreadyRunningError(DreamError):
    """A process-local generation is already active for the session."""
