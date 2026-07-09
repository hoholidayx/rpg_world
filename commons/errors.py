"""Shared business exceptions used across process boundaries."""

from __future__ import annotations

TURN_METADATA_INVALID_ERROR_CODE = "TURN_METADATA_INVALID"
TURN_METADATA_INVALID_STATUS_CODE = 409


class InvalidTurnMetadataError(ValueError):
    """Raised when explicit ``turn_id`` / ``seq_in_turn`` metadata is invalid."""


def format_turn_metadata_error_message(error: BaseException) -> str:
    """Return the raw error message; stable code is carried separately."""
    return str(error)
