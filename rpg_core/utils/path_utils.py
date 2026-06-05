"""Path resolution for RPG World settings.

Resolution rules (applied in order):

1. Absolute path (starts with ``/``) — returned as-is.
2. Relative path — resolved relative to the **RPG world package root**
   (``rpg_world/``).

   * If ``active_workspace`` is set (e.g. ``"data/非公开行程"``), the
     workspace path is used as the base: ``character`` →
     ``rpg_world/data/非公开行程/character``.
   * If no workspace is set, ``data/`` is used as the base: ``character`` →
     ``rpg_world/data/character``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["resolve_rpg_path", "resolve_workspace_root", "get_session_dir"]


def resolve_rpg_path(
    value: str,
    rpg_root: Path,
    rpg_workspace: str = "",
) -> Path:
    """Resolve a path string according to the rules above.

    Args:
        value: Raw path string from settings.
        rpg_root: RPG world package root directory (``rpg_world/``).
        rpg_workspace: Active RPG workspace path (e.g. ``"data/非公开行程"``).

    Returns:
        Resolved absolute :class:`Path`.
    """
    p = Path(value)
    if p.is_absolute():
        return p

    if rpg_workspace:
        ws = Path(rpg_workspace)
        base = ws if ws.is_absolute() else rpg_root / ws
    else:
        base = rpg_root / "data"

    return (base / p).resolve()


def resolve_workspace_root(
    rpg_root: Path,
    rpg_workspace: str = "",
) -> Path:
    """Return the resolved absolute path to the workspace root directory.

    Cross-session data (character, lorebook) lives directly under this root.
    Session-scoped data lives under ``root / "sessions" / {session_id}``.
    """
    if rpg_workspace:
        ws = Path(rpg_workspace)
        return ws if ws.is_absolute() else (rpg_root / ws).resolve()
    return (rpg_root / "data").resolve()


def get_session_dir(
    rpg_root: Path,
    rpg_workspace: str = "",
    session_id: str = "default",
) -> Path:
    """Return the session directory for a given session_id."""
    ws_root = resolve_workspace_root(rpg_root, rpg_workspace)
    return ws_root / "sessions" / session_id
