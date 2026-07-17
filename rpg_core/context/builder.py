"""RPGContextBuilder — transform raw messages into the 5-layer RPG structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context.config import RPGContextConfig
from rpg_core.context.models import (
    FixedLayerData,
    HotHistoryLayer,
    Message,
    PersistentMemoryFact,
    PersistentMemoryLayer,
    RecalledMemoryLayer,
    RPGContext,
    RPModuleRuntimeSection,
    RPModulesLayer,
    StatusTablesLayer,
    StoryMemoryLayer,
    SummaryLayer,
    UserExtensionBlock,
    UserMessageLayer,
)
from rpg_core.session.grouping import slice_recent_turns
from rpg_core.status.context import prepare_status_context_tables

if TYPE_CHECKING:
    from rp_memory.persist_memory import PersistentMemoryStore
    from rp_memory.recalled_memory import RecalledMemoryStore
    from rp_memory.story_memory import StoryMemoryStore
    from rpg_core.scene.tracker import SceneTracker
    from rpg_core.status.manager import StatusManager
    from rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_core.summary.store import SummaryStore


def _flatten_status_tables(
    status_mgr: StatusManager | None,
) -> list[dict[str, object]]:
    """Return normal status tables for context rendering."""

    if status_mgr is None:
        return []
    try:
        return prepare_status_context_tables(status_mgr.list_context_tables())
    except Exception as exc:
        logger.debug("[RPGContextBuilder] flatten status tables failed: {}", exc)
        return []


# ── builder ──────────────────────────────────────────────────────────


class RPGContextBuilder:
    """将原始消息列表转换为 5 层 RPG 结构。

    Structured layers (conceptual order, not provider wire-message boundaries):

        Index  Role       Content                         Change frequency
        ─────  ─────────  ─────────────────────────────── ─────────────────
        [0]    system     Fixed Layer (prompt/lore/char)   ★ almost never
        [1]    system     Persistent Memory (常驻记忆)      ★ offline update only
        [2]    system     Summary Layer (conditional)      ★☆ rarely
        [3..N] mixed      Hot History (windowed)           ★★☆ every turn (appended)
        [N+1]  system     Story Memory (剧情记忆)          ★★☆ accumulated details
        [N+2]  system     Status Tables                    ★★★★ current state
        [N+3]  system     Recalled Memory (召回)            ★★★ dynamically injected
        [N+4]  system     RP Modules (optional)            ★★★★ dynamic module state
        [N+5]  user       User Message                     always new

    Provider prefix caching follows the serialized/tokenized request, not these
    dataclass layers. ``ContextRenderer`` emits every rendered non-history layer
    as its own ordered message and expands Hot History in place. A volatile
    layer change can preserve every serialized message before it, but prevents
    that layer and all following messages from belonging to the same reusable
    provider prefix.

    Story Memory and Summary are derived Dream inputs.  The independent Dream
    service reconciles them or the current main history into the SQL-backed
    Persistent Memory ledger; this builder only reads its evidence-valid active
    projection and never performs consolidation writes.
    """

    def __init__(
        self,
        config: RPGContextConfig,
        world_name: str = "Nanobot Realm",
    ) -> None:
        self.config = config
        self.world_name = world_name

        # Lazy-initialised stores
        self._summary_store: SummaryStore | None = None
        self._persist_memory: PersistentMemoryStore | None = None
        self._story_memory: StoryMemoryStore | None = None
        self._recalled_memory: RecalledMemoryStore | None = None
        self._batch_summary_store: BatchSummaryStore | None = None

    # ── store injection (set by hook after construction) ─────────────

    def set_summary_store(self, store: SummaryStore) -> None:
        self._summary_store = store

    def set_recalled_memory_store(self, store: RecalledMemoryStore) -> None:
        self._recalled_memory = store

    def set_story_memory_store(self, store: StoryMemoryStore) -> None:
        self._story_memory = store

    def set_persistent_memory_store(self, store: PersistentMemoryStore) -> None:
        self._persist_memory = store

    def set_batch_summary_store(self, store: BatchSummaryStore) -> None:
        self._batch_summary_store = store

    async def load_persistent_memory_snapshot(
        self,
    ) -> tuple[PersistentMemoryFact, ...]:
        """Load one immutable SQL projection for a turn or preview."""

        if self._persist_memory is None or not self.config.enable_persistent_memory:
            return ()
        items = await self._persist_memory.load_snapshot()
        return tuple(
            PersistentMemoryFact(
                memory_id=item.memory_id,
                revision_number=item.revision_number,
                text=item.text,
                memory_kind=item.memory_kind,
                epistemic_status=item.epistemic_status,
                salience=item.salience,
            )
            for item in items
        )

    def close(self) -> None:
        """Release session-local store registrations and transient context."""

        if self._summary_store is not None:
            self._summary_store.close()
        if self._batch_summary_store is not None:
            self._batch_summary_store.close()
        if self._recalled_memory is not None:
            self._recalled_memory.clear()

    @property
    def summary_store(self) -> SummaryStore | None:
        """Read-only access for runtime composition."""
        return self._summary_store

    @property
    def story_memory_store(self) -> StoryMemoryStore | None:
        """Read-only access for runtime composition."""
        return self._story_memory

    @property
    def batch_summary_store(self) -> BatchSummaryStore | None:
        """Read-only access for runtime composition."""
        return self._batch_summary_store

    # ── main entry ──────────────────────────────────────────────────

    def build(
        self,
        fixed_layer: FixedLayerData | None = None,
        history_messages: list[Message] | None = None,
        current_user_message: Message | None = None,
        summarized_message_count: int = 0,
        status_mgr: StatusManager | None = None,
        scene_tracker: SceneTracker | None = None,
        rp_module_sections: list[RPModuleRuntimeSection] | None = None,
        persistent_memory_snapshot: tuple[PersistentMemoryFact, ...] = (),
    ) -> RPGContext:
        """构建 5 层 RPGContext。

        Args:
            fixed_layer: 预组装好的固定层快照，包含 sections 及角色卡/世界书结构化数据。
            history_messages: 已投影的主 Agent 历史，不包含当前用户消息。
            current_user_message: 当前 turn 的用户消息；预览时可以为空。
            summarized_message_count: 被 ``summary_processed`` 排除的消息数。
            status_mgr: 状态管理器，为 None 时动态层跳过状态表格模块。
            rp_module_sections: 可选 RP module 运行态；静态契约应放在 fixed_layer.sections。
        """
        resolved_history = list(history_messages or [])
        user_text = (
            current_user_message.content
            if current_user_message is not None and current_user_message.is_user()
            else ""
        )

        # ── 2. Fixed Layer 已在 builder 外完成装配 ─────────────────
        resolved_fixed_layer = fixed_layer or FixedLayerData(world_name=self.world_name)

        # ── 3. Build Persistent Memory Layer ─────────────────────────
        persistent_memories = list(persistent_memory_snapshot)

        # ── 4. Build Summary Layer (overall.md only) ──────────────────
        summary_text: str | None = None
        if (
            self.config.enable_summaries
            and summarized_message_count > 0
            and self._batch_summary_store
        ):
            try:
                overall, _ = self._batch_summary_store.load_overall()
                if overall:
                    summary_text = overall
            except Exception as exc:
                logger.debug("[RPGContextBuilder] summary layer skipped: {}", exc)

        # ── 5. Extract Hot History ──────────────────────────────────
        # Filter to keep only the most recent turns.
        hot_history = slice_recent_turns(resolved_history, self.config.hot_history_rounds)

        # ── 6. Build Dynamic Layer modules ──────────────────────────
        # Keep the conceptual dynamic-layer order deterministic. ContextRenderer
        # owns the final provider message layout and its cache-prefix boundary.
        story_details: list[dict] = []
        if self._story_memory and self.config.enable_story_memory:
            try:
                story_details = self._story_memory.get_all()
            except Exception as exc:
                logger.debug("[RPGContextBuilder] story memory layer skipped: {}", exc)

        status_tables: list[dict] = []
        if status_mgr and self.config.enable_status_tables:
            status_tables = _flatten_status_tables(status_mgr)

        recalled_items: list[str] = []
        if self._recalled_memory and self.config.enable_recalled_memory:
            try:
                recalled_items = self._recalled_memory.get_items()
            except Exception as exc:
                logger.debug("[RPGContextBuilder] recalled memory layer skipped: {}", exc)

        # ── 7. Build user message with User Extension Layer ─────────
        user_before = self._build_extension_blocks(
            [m for m in self.config.user_extension if m.position == "before"],
            {"user_reply_prefix": "接下来是用户的输入："},
        )
        user_after = self._build_extension_blocks(
            [m for m in self.config.user_extension if m.position == "after"],
            {"user_reply_suffix": "请用中文回复，保持角色设定。"},
        )

        # ── 8. Assemble structured RPGContext ─────────────────────────
        return RPGContext(
            fixed_layer=resolved_fixed_layer,
            persistent_memory=PersistentMemoryLayer(memories=persistent_memories),
            summary=SummaryLayer(text=summary_text),
            hot_history=HotHistoryLayer(messages=hot_history),
            story_memory=StoryMemoryLayer(details=story_details),
            recalled_memory=RecalledMemoryLayer(items=recalled_items),
            status_tables=StatusTablesLayer(tables=status_tables),
            rp_modules=RPModulesLayer(sections=list(rp_module_sections or [])),
            user_message=UserMessageLayer(
                before=user_before,
                user_input=user_text,
                after=user_after,
            ),
        )

    # ── internal helpers ─────────────────────────────────────────────

    def _build_extension_blocks(
        self,
        modules: list[object],
        default_data: dict[str, str],
    ) -> list[UserExtensionBlock]:
        """Collect enabled user extension templates without rendering."""
        blocks: list[UserExtensionBlock] = []
        for mod in modules:
            if not mod.enabled:
                continue
            blocks.append(UserExtensionBlock.from_def(mod, default_data))
        return blocks
