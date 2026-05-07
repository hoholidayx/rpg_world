"""Dependency providers — wire up rpg_core managers for FastAPI routes."""

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


@lru_cache
def get_status_manager() -> StatusManager:
    mgr = StatusManager(settings.status_path)
    _try_start_watcher()
    return mgr
