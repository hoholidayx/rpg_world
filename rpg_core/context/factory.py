"""Factory — wire up RPGContextBuilder, managers and stores.

The standalone ``rpg_world/agent`` package uses this directly instead of the
now-removed ``RpgWorldHook`` nanobot integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


def build_rpg_context(
    world_name: str = "Nanobot Realm",
    session_id: str = "default",
) -> dict[str, Any]:
    """Create and wire up the full RPG context stack.

    Returns a dict with keys ``builder``, ``character_mgr``, ``lorebook_mgr``,
    ``milestone_mgr``, ``status_mgr`` — ready to pass to
    ``RPGContextBuilder.build()``.
    """
    from rpg_world.rpg_core.settings import settings as rpg_settings
    from rpg_world.rpg_core.context.builder import RPGContextBuilder
    from rpg_world.rpg_core.context.config import RPGContextConfig
    from rpg_world.rpg_core.memory.persist_memory import PersistentMemoryStore
    from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
    from rpg_world.rpg_core.memory.story_memory import StoryMemoryStore
    from rpg_world.rpg_core.summary.store import SummaryStore

    config = RPGContextConfig()
    builder = RPGContextBuilder(
        config=config,
        world_name=world_name,
    )

    # ── Stores ────────────────────────────────────────────────────────
    summary_path = Path(rpg_settings.summary_path)
    builder.set_summary_store(SummaryStore(summary_path))
    story_path = Path(rpg_settings.story_memory_path)
    builder.set_story_memory_store(StoryMemoryStore(story_path, session_id))
    builder.set_recalled_memory_store(RecalledMemoryStore())
    builder.set_persistent_memory_store(
        PersistentMemoryStore(Path(rpg_settings.persistent_memory_path))
    )

    # ── Managers (lazy, may fail if data directories don't exist) ──────
    character_mgr: Any = None
    lorebook_mgr: Any = None
    milestone_mgr: Any = None
    status_mgr: Any = None

    try:
        from rpg_world.rpg_core.character import CharacterManager

        character_mgr = CharacterManager(rpg_settings.character_path)
    except Exception as exc:
        logger.debug("[RPG World] CharacterManager init skipped: {}", exc)

    try:
        from rpg_world.rpg_core.lorebook import LorebookManager

        lorebook_mgr = LorebookManager(rpg_settings.lorebook_path)
    except Exception as exc:
        logger.debug("[RPG World] LorebookManager init skipped: {}", exc)

    try:
        from rpg_world.rpg_core.milestone import MilestoneManager

        milestone_mgr = MilestoneManager(rpg_settings.milestone_path)
    except Exception as exc:
        logger.debug("[RPG World] MilestoneManager init skipped: {}", exc)

    try:
        from rpg_world.rpg_core.status import StatusManager

        status_mgr = StatusManager(rpg_settings.status_path)
    except Exception as exc:
        logger.debug("[RPG World] StatusManager init skipped: {}", exc)

    return {
        "builder": builder,
        "character_mgr": character_mgr,
        "lorebook_mgr": lorebook_mgr,
        "milestone_mgr": milestone_mgr,
        "status_mgr": status_mgr,
    }
