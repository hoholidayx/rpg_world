"""Path resolution for RPG World settings.

Resolution rules (applied in order):

1. Absolute path (starts with ``/``) — returned as-is.
2. Relative path — resolved relative to the **RPG world package root**
   (``rpg_world/``).  If an RPG workspace name is set and the path starts with
   ``data/``, the workspace name is injected: ``data/character`` →
   ``data/<workspace>/character``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["resolve_rpg_path"]


def resolve_rpg_path(
    value: str,
    rpg_root: Path,
    rpg_workspace: str = "",
) -> Path:
    """Resolve a path string according to the rules above.

    Args:
        value: Raw path string from settings.
        rpg_root: RPG world package root directory (``rpg_world/``).
        rpg_workspace: Active RPG workspace name (e.g. ``"非公开行程"``).

    Returns:
        Resolved absolute :class:`Path`.
    """
    p = Path(value)
    if p.is_absolute():
        return p

    # Inject RPG workspace name into data/ paths
    if rpg_workspace and p.parts[0] == "data":
        p = Path(*([p.parts[0], rpg_workspace] + list(p.parts[1:])))
    return (rpg_root / p).resolve()
