from __future__ import annotations

__all__ = ["SessionManager"]


def __getattr__(name: str):
    if name == "SessionManager":
        from rpg_core.session.manager import SessionManager

        return SessionManager
    raise AttributeError(name)
