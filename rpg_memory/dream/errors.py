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


class DreamProposalConflictError(DreamError):
    """A Session already has a generating proposal."""


class DreamProposalStateError(DreamError):
    """A proposal or memory operation is invalid for its current state."""


class DreamProposalStaleError(DreamError):
    """A proposal no longer matches its immutable source snapshot."""


class DreamActiveMemoryLimitError(DreamError):
    """A mutation would exceed the Session active-memory limit."""


class DreamEvidenceInvalidError(DreamError):
    """Immutable memory Evidence no longer matches authoritative history."""
