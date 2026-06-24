"""Factory — wire up RPGContextBuilder, managers and stores."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from rpg_core.character.manager import CharacterManager
    from rpg_core.lorebook.manager import LorebookManager
    from rpg_core.scene.tracker import SceneTracker
    from rpg_core.status.manager import StatusManager


def build_rpg_context(
    world_name: str = "Nanobot Realm",
    workspace: str = "",
    session_id: str = "default",
) -> dict[str, object]:
    """Create and wire up the full RPG context stack.

    Returns a dict with keys ``builder``, ``character_mgr``, ``lorebook_mgr``,
    ``status_mgr``, ``scene_tracker`` — ready to pass to
    ``RPGContextBuilder.build()``.

    Cross-session data (character, lorebook) is loaded from *workspace* root.
    Session-scoped data (status, summary, memory, history) is loaded from
    ``sessions/{session_id}/`` under *workspace*.
    """
    from rpg_core.settings import settings as rpg_settings
    from rpg_core.context.builder import RPGContextBuilder
    from rpg_core.context.config import RPGContextConfig
    from rp_memory.persist_memory import PersistentMemoryStore
    from rp_memory.recalled_memory import RecalledMemoryStore
    from rp_memory.story_memory import StoryMemoryStore
    from rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_core.summary.store import SummaryStore

    config = RPGContextConfig()
    builder = RPGContextBuilder(
        config=config,
        world_name=world_name,
    )

    # ── Session-scoped Stores ─────────────────────────────────────────
    builder.set_summary_store(
        SummaryStore(rpg_settings.get_summary_path(workspace, session_id))
    )
    builder.set_batch_summary_store(
        BatchSummaryStore(workspace, session_id)
    )
    builder.set_story_memory_store(
        StoryMemoryStore(rpg_settings.get_story_memory_path(workspace, session_id))
    )
    recalled_store = RecalledMemoryStore()
    builder.set_recalled_memory_store(recalled_store)
    builder.set_persistent_memory_store(
        PersistentMemoryStore(rpg_settings.get_persistent_memory_path(workspace, session_id))
    )

    # ── MemoryManager（封装向量记忆检索） ─────────────────────────
    memory_manager: object | None = None

    try:
        from rp_memory.memory_manager import MemoryManager

        memory_manager = MemoryManager.create(
            recalled_store=recalled_store,  # type: ignore[arg-type]
            session_dir=rpg_settings.session_dir(workspace, session_id),
            get_vector_db_path=rpg_settings.get_vector_db_path(workspace, session_id),
            mem_cfg=rpg_settings.memory_settings,
        )
    except Exception as exc:
        logger.warning("[RPG World] MemoryManager creation failed: {}", exc)

    # ── Cross-session Managers ────────────────────────────────────────
    character_mgr: CharacterManager | None = None
    lorebook_mgr: LorebookManager | None = None
    status_mgr: StatusManager | None = None

    try:
        from rpg_core.character import CharacterManager

        character_mgr = CharacterManager(rpg_settings.character_path(workspace))
    except Exception as exc:
        logger.debug("[RPG World] CharacterManager init skipped: {}", exc)

    try:
        from rpg_core.lorebook import LorebookManager

        lorebook_mgr = LorebookManager(rpg_settings.lorebook_path(workspace))
    except Exception as exc:
        logger.debug("[RPG World] LorebookManager init skipped: {}", exc)

    # ── Session-scoped Manager ────────────────────────────────────────
    try:
        from rpg_core.status import StatusManager

        status_mgr = StatusManager(str(rpg_settings.get_status_dir(workspace, session_id)))
    except Exception as exc:
        logger.debug("[RPG World] StatusManager init skipped: {}", exc)

    # ── SceneTracker (binds to status_mgr, both session-scoped) ────────
    scene_tracker: SceneTracker | None = None
    if status_mgr is not None:
        try:
            from rpg_core.scene import SceneTracker

            scene_tracker = SceneTracker()
            scene_tracker.bind_status_manager(status_mgr)
            scene_tracker.load_from_status_table()
        except Exception as exc:
            logger.debug("[RPG World] SceneTracker init skipped: {}", exc)

    return {
        "builder": builder,
        "character_mgr": character_mgr,
        "lorebook_mgr": lorebook_mgr,
        "status_mgr": status_mgr,
        "scene_tracker": scene_tracker,
        "memory_manager": memory_manager,
    }
