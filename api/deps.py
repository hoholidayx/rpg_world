"""Dependency providers — wire up rpg_core managers for FastAPI routes.

CharacterManager and LorebookManager are cached per-workspace.
StatusManager is cached per (workspace, session_id) tuple.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from rpg_world.rpg_core.character import CharacterManager
from rpg_world.rpg_core.lorebook import LorebookManager
from rpg_world.rpg_core.status import StatusManager
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.utils.path_utils import (
    ensure_workspace_dir,
    resolve_api_workspace,
)
from rpg_world.rpg_core.utils.path_utils import PACKAGE_ROOT as _PACKAGE_ROOT
from rpg_world.rpg_core.utils.watcher import get_watcher


def _try_start_watcher() -> None:
    """Start the file watcher after managers have registered their paths.

    Safe to call multiple times (singleton start).
    """
    get_watcher().start()


# ------------------------------------------------------------------
# Cross-session managers — cached per workspace
# ------------------------------------------------------------------


@lru_cache
def get_character_manager(workspace: str = "") -> CharacterManager:
    workspace = resolve_api_workspace(workspace)
    ensure_workspace_dir(_PACKAGE_ROOT, workspace)
    mgr = CharacterManager(str(settings.character_path(workspace)))
    _try_start_watcher()
    return mgr


@lru_cache
def get_lorebook_manager(workspace: str = "") -> LorebookManager:
    workspace = resolve_api_workspace(workspace)
    ensure_workspace_dir(_PACKAGE_ROOT, workspace)
    mgr = LorebookManager(str(settings.lorebook_path(workspace)))
    _try_start_watcher()
    return mgr


# ------------------------------------------------------------------
# Session-scoped managers — cached per (workspace, session_id)
# ------------------------------------------------------------------

_session_managers: dict[tuple[str, str], StatusManager] = {}


def get_session_status_manager(workspace: str = "", session_id: str = "default") -> StatusManager:
    """Get or create a StatusManager for the given workspace + session.

    Per-session caching ensures FileWatcher callbacks don't accumulate
    while still supporting multiple concurrent sessions across workspaces.
    """
    workspace = resolve_api_workspace(workspace)
    ensure_workspace_dir(_PACKAGE_ROOT, workspace)
    key = (workspace, session_id)
    if key not in _session_managers:
        mgr = StatusManager(str(settings.get_status_dir(workspace, session_id)))
        _session_managers[key] = mgr
        _try_start_watcher()
    return _session_managers[key]


# ------------------------------------------------------------------
# Cache clearing (for tests / process shutdown)
# ------------------------------------------------------------------


def clear_all_caches() -> None:
    """Clear all manager caches and watcher state.

    Not called by business routes — only used in test fixtures
    or during explicit process cleanup.
    """
    get_character_manager.cache_clear()
    get_lorebook_manager.cache_clear()
    _session_managers.clear()
    from rpg_world.rpg_core.agent.manager import AgentManager

    AgentManager.reset()
    watcher = get_watcher()
    watcher.stop()
    watcher.clear_all()
