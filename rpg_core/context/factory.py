"""Factory — wire up RPGContextBuilder, managers and stores."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from rpg_core.character import CharacterManager
    from rpg_core.lorebook import LorebookManager
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

    ``workspace`` is kept for compatibility with older callers and is ignored.
    Character, lorebook, and status data are read from the rpg_data catalog by
    *session_id* and its bound story. Status table documents, Story Memory, and
    history use their SQLite sources of truth; only summary and online-memory
    runtime artifacts are resolved from the Session runtime directory.
    """
    from rpg_core.settings import settings as rpg_settings
    from rpg_core.context.builder import RPGContextBuilder
    from rpg_core.context.config import RPGContextConfig
    from rp_memory.persist_memory import PersistentMemoryStore
    from rp_memory.dream.application import DreamApplicationService
    from rp_memory.recalled_memory import RecalledMemoryStore
    from rp_memory.story_memory import StoryMemoryStore
    from rp_memory.story_memory_service import StoryMemoryApplicationService
    from rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_core.summary.store import SummaryStore
    from rpg_data.services import get_data_service_gateway

    config = RPGContextConfig()
    builder = RPGContextBuilder(
        config=config,
        world_name=world_name,
    )

    gateway = get_data_service_gateway()
    session_root = gateway.catalog.get_session_runtime_dir(session_id)

    # ── Session-scoped Stores ─────────────────────────────────────────
    builder.set_summary_store(
        SummaryStore(session_root / "rpg_summaries.json")
    )
    builder.set_batch_summary_store(
        BatchSummaryStore(session_root)
    )
    builder.set_story_memory_store(
        StoryMemoryStore(
            session_id,
            StoryMemoryApplicationService(gateway.story_memory),
        )
    )
    recalled_store = RecalledMemoryStore()
    builder.set_recalled_memory_store(recalled_store)
    builder.set_persistent_memory_store(
        PersistentMemoryStore(
            session_id,
            DreamApplicationService(gateway.dream_memory),
            close_worker_connection=gateway.close_thread_connection,
        )
    )

    # ── MemoryManager（封装向量记忆检索） ─────────────────────────
    memory_manager: object | None = None

    try:
        from rp_memory.memory_manager import MemoryManager

        memory_manager = MemoryManager.create(
            recalled_store=recalled_store,  # type: ignore[arg-type]
            session_dir=str(session_root),
            get_vector_db_path=str(session_root / "memory_vectors.db"),
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

        character_mgr = CharacterManager(session_id)
    except Exception as exc:
        logger.debug("[RPG World] CharacterManager init skipped: {}", exc)

    try:
        from rpg_core.lorebook import LorebookManager

        lorebook_mgr = LorebookManager(session_id)
    except Exception as exc:
        logger.debug("[RPG World] LorebookManager init skipped: {}", exc)

    # ── Session-scoped rpg_data Status Manager ────────────────────────
    try:
        from rpg_core.status import StatusManager

        status_mgr = StatusManager(session_id, gateway.status)
    except Exception as exc:
        logger.debug("[RPG World] StatusManager init skipped: {}", exc)

    # ── SceneTracker (only when story-mounted scene table exists) ──────
    scene_tracker: SceneTracker | None = None
    if status_mgr is not None:
        try:
            from rpg_core.scene import SceneTracker

            if status_mgr.get_active_scene_table() is not None:
                scene_tracker = SceneTracker(
                    allow_runtime_key_changes=(
                        rpg_settings.scene_settings.allow_runtime_key_changes
                    )
                )
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
