from __future__ import annotations

__all__ = ["InvalidTurnMetadataError", "SessionManager", "validate_turn_metadata"]


def __getattr__(name: str):
    if name == "SessionManager":
        from rpg_core.session.manager import SessionManager

        return SessionManager
    if name == "InvalidTurnMetadataError":
        from rpg_core.session.turn_metadata import InvalidTurnMetadataError

        return InvalidTurnMetadataError
    if name == "validate_turn_metadata":
        from rpg_core.session.turn_metadata import validate_turn_metadata

        return validate_turn_metadata
    raise AttributeError(name)
