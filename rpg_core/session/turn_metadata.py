"""Shared validation for explicit session turn metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from commons.errors import InvalidTurnMetadataError


def validate_turn_metadata(records: Sequence[object], *, label: str = "history") -> None:
    """Validate explicit turn metadata without falling back to legacy grouping."""
    last_turn_id = 0
    last_seq_in_turn = 0
    for index, record in enumerate(records):
        turn_id = _positive_int(_turn_value(record))
        seq_in_turn = _positive_int(_seq_value(record))
        if turn_id is None or seq_in_turn is None:
            raise InvalidTurnMetadataError(
                f"invalid turn metadata at {label}[{index}]: turn_id and seq_in_turn must be positive integers"
            )
        if turn_id < last_turn_id:
            raise InvalidTurnMetadataError(
                f"invalid turn metadata at {label}[{index}]: turn_id must be nondecreasing"
            )
        if turn_id == last_turn_id and seq_in_turn <= last_seq_in_turn:
            raise InvalidTurnMetadataError(
                f"invalid turn metadata at {label}[{index}]: seq_in_turn must increase inside the same turn"
            )
        last_seq_in_turn = seq_in_turn
        last_turn_id = turn_id


def has_trustworthy_turn_metadata(records: Sequence[object]) -> bool:
    if not records:
        return False
    try:
        validate_turn_metadata(records)
    except InvalidTurnMetadataError:
        return False
    return True


def _turn_value(record: object) -> object | None:
    return _first_value(record, ("turn_id", "turnId"))


def _seq_value(record: object) -> object | None:
    return _first_value(record, ("seq_in_turn", "seqInTurn"))


def _first_value(record: object, keys: tuple[str, ...]) -> object | None:
    if isinstance(record, Mapping):
        for key in keys:
            value = record.get(key)
            if value is not None and value != "":
                return value
        return None
    for key in keys:
        value = getattr(record, key, None)
        if value is not None and value != "":
            return value
    return None


def _positive_int(value: object | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
