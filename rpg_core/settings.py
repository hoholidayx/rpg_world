"""RPG World settings — shared by core and API layers.

Settings are read from ``rpg_world/settings.json``.  Relative paths
in the file are resolved against the ``rpg_world/`` package root.

Workspace support:
  - ``active_workspace`` (default ``""``) selects a named subdirectory under
    ``data/`` — paths like ``data/character`` resolve to
    ``data/<workspace>/character`` when set.
  - Workspaces are auto-detected as subdirectories under ``data/`` (excluding
    known data-type directories ``character``, ``lorebook``, ``status``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Location of settings.json relative to this module
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
# Package root used to resolve relative paths
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Known data-type subdirectories inside data/
_KNOWN_DATA_DIRS = frozenset({"character", "lorebook", "milestone", "status"})


def _load() -> dict[str, Any]:
    if _SETTINGS_PATH.is_file():
        with _SETTINGS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def _resolve(value: str, workspace: str = "") -> str:
    """Resolve a path — return as-is if absolute, else relative to package root.

    If *workspace* is non-empty and the relative path starts with ``data/``,
    the workspace name is inserted: ``data/character`` → ``data/<ws>/character``.
    """
    p = Path(value)
    if p.is_absolute():
        return str(p)
    if workspace and p.parts[0] == "data":
        p = Path(*([p.parts[0], workspace] + list(p.parts[1:])))
    return str(_PACKAGE_ROOT / p)


class Settings:
    """Read-write settings proxy.  Attributes mirror keys in settings.json."""

    def __init__(self) -> None:
        self._raw = _load()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def active_workspace(self) -> str:
        return self._raw.get("active_workspace", "")

    @property
    def character_path(self) -> str:
        return _resolve(
            self._raw.get("character_path", "data/character"),
            self.active_workspace,
        )

    @property
    def lorebook_path(self) -> str:
        return _resolve(
            self._raw.get("lorebook_path", "data/lorebook"),
            self.active_workspace,
        )

    @property
    def milestone_path(self) -> str:
        return _resolve(
            self._raw.get("milestone_path", "data/milestone"),
            self.active_workspace,
        )

    @property
    def status_path(self) -> str:
        return _resolve(
            self._raw.get("status_path", "data/status"),
            self.active_workspace,
        )

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, str]]:
        """Discover available workspaces.

        Returns a list of ``{"name": …, "label": …}`` dicts.  The first
        entry is always the default workspace (``name=""``, ``label="默认"``).
        Named workspaces are subdirectories of ``data/`` that are not
        known data-type directories.
        """
        workspaces: list[dict[str, str]] = [
            {"name": "", "label": "默认（根工作区）"},
        ]
        data_dir = _PACKAGE_ROOT / "data"
        if data_dir.is_dir():
            for entry in sorted(data_dir.iterdir()):
                if entry.is_dir() and entry.name not in _KNOWN_DATA_DIRS:
                    workspaces.append({"name": entry.name, "label": entry.name})
        return workspaces

    def set_active_workspace(self, name: str) -> None:
        """Switch the active workspace and persist to disk."""
        self._raw["active_workspace"] = name
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SETTINGS_PATH.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self._raw, f, ensure_ascii=False, indent=2)
            f.write("\n")


# Singleton
settings = Settings()
