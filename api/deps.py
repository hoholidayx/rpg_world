"""Dependency providers — wire up rpg_core managers for FastAPI routes.

CharacterManager and LorebookManager are cross-session singletons (cached).
StatusManager is per-session — each session gets its own instance so that
FileWatcher callbacks target the correct data directory.
"""

from __future__ import annotations

from functools import lru_cache

from rpg_world.rpg_core.character import CharacterManager
from rpg_world.rpg_core.lorebook import LorebookManager
from rpg_world.rpg_core.status import StatusManager
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.utils.watcher import get_watcher


def _try_start_watcher() -> None:
    """Start the file watcher after managers have registered their paths.

    Safe to call multiple times (singleton start).
    """
    get_watcher().start()


# ------------------------------------------------------------------
# Cross-session managers — cached singletons
# ------------------------------------------------------------------


@lru_cache
def get_character_manager() -> CharacterManager:
    mgr = CharacterManager(settings.character_path)
    _try_start_watcher()
    return mgr


@lru_cache
def get_lorebook_manager() -> LorebookManager:
    mgr = LorebookManager(settings.lorebook_path)
    _try_start_watcher()
    return mgr


# ------------------------------------------------------------------
# Session-scoped managers — per-session cache
# ------------------------------------------------------------------

_session_managers: dict[str, StatusManager] = {}


def get_session_status_manager(session_id: str = "default") -> StatusManager:
    """Get or create a StatusManager for the given session.

    Per-session caching ensures FileWatcher callbacks don't accumulate
    while still supporting multiple concurrent sessions.
    """
    if session_id not in _session_managers:
        mgr = StatusManager(str(settings.get_status_dir(session_id)))
        _session_managers[session_id] = mgr
        _try_start_watcher()
    return _session_managers[session_id]


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------


def reset_all() -> None:
    """Reset all manager caches and watcher state.

    Called after switching workspaces so the next request creates fresh
    managers pointing at the new data paths.
    """
    get_character_manager.cache_clear()
    get_lorebook_manager.cache_clear()
    _session_managers.clear()
    from rpg_world.api.routers.chat import _agent_instances

    _agent_instances.clear()
    watcher = get_watcher()
    watcher.stop()
    watcher.clear_all()
