"""RPG World settings — shared by core and API layers.

Settings are read from ``rpg_world/settings.json``.  Path resolution:

- Absolute path (starts with ``/``) — returned as-is.
- Relative path — resolved relative to ``rpg_world/``.  If
  ``active_workspace`` is set (e.g. ``"data/非公开行程"``), it is used
  as the base directory; otherwise ``data/`` is used as the default base.

See :func:`rpg_world.rpg_core.utils.path_utils.resolve_rpg_path` for details.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.utils.path_utils import resolve_rpg_path

# Location of settings.json relative to this module
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
# Package root used to resolve relative paths
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Known data-type subdirectories inside data/
_KNOWN_DATA_DIRS = frozenset({"character", "lorebook", "milestone", "status", "summary", "story_memory", "history"})


def _load() -> dict[str, Any]:
    if _SETTINGS_PATH.is_file():
        with _SETTINGS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


class Settings:
    """Read-write settings proxy.  Attributes mirror keys in settings.json."""

    def __init__(self) -> None:
        self._raw = _load()

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _resolve(self, key: str, default: str) -> str:
        """Resolve a settings value, delegating to :func:`resolve_rpg_path`."""
        value = self._raw.get(key, default)
        return str(resolve_rpg_path(
            value=value,
            rpg_root=_PACKAGE_ROOT,
            rpg_workspace=self.active_workspace,
        ))

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def active_workspace(self) -> str:
        return self._raw.get("active_workspace", "")

    @property
    def character_path(self) -> str:
        return self._resolve("character_path", "character")

    @property
    def lorebook_path(self) -> str:
        return self._resolve("lorebook_path", "lorebook")

    @property
    def milestone_path(self) -> str:
        return self._resolve("milestone_path", "milestone")

    @property
    def status_path(self) -> str:
        return self._resolve("status_path", "status")

    @property
    def summary_path(self) -> str:
        return self._resolve("summary_path", "summary")

    @property
    def story_memory_path(self) -> str:
        return self._resolve("story_memory_path", "story_memory")

    @property
    def persistent_memory_path(self) -> str:
        return self._resolve("persistent_memory_path", "persistent_memory.md")

    @property
    def history_path(self) -> str:
        return self._resolve("history_path", "history")

    @property
    def max_tool_calls(self) -> int:
        return self._raw.get("agent_config", {}).get("max_tool_call_limit", 10)

    @property
    def include_tool_records(self) -> bool:
        return self._raw.get("agent_config", {}).get("include_tool_records", True)

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, str]]:
        """Discover available workspaces.

        Returns a list of ``{"name": …, "label": …}`` dicts.  The first
        entry is always the default workspace (``name=""``, ``label="默认"``).
        Named workspaces are subdirectories of ``data/`` that are not
        known data-type directories.  Their ``name`` is ``"data/<dir>"`` so
        that ``resolve_rpg_path`` resolves paths under the workspace.
        """
        workspaces: list[dict[str, str]] = [
            {"name": "", "label": "默认（根工作区）"},
        ]
        data_dir = _PACKAGE_ROOT / "data"
        if data_dir.is_dir():
            for entry in sorted(data_dir.iterdir()):
                if entry.is_dir() and entry.name not in _KNOWN_DATA_DIRS:
                    workspaces.append({"name": f"data/{entry.name}", "label": entry.name})
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
