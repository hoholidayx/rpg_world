"""RPGContextBuilder — transform raw messages into the 5-layer RPG structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

from rpg_world.rpg_core.context.config import RPGContextConfig
from rpg_world.rpg_core.context.rpg_context import Message, Role, RPGContext
from rpg_world.rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_world.rpg_core.character.manager import CharacterManager
    from rpg_world.rpg_core.lorebook.manager import LorebookManager
    from rpg_world.rpg_core.memory.persist_memory import PersistentMemoryStore
    from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
    from rpg_world.rpg_core.memory.story_memory import StoryMemoryStore
    from rpg_world.rpg_core.scene.tracker import SceneTracker
    from rpg_world.rpg_core.status.manager import StatusManager
    from rpg_world.rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_world.rpg_core.summary.store import SummaryStore


# ── shared Jinja environment ──────────────────────────────────────────

_JINJA_ENV: Environment | None = None


def render_jinja_template(template_name: str, **context: object) -> str:
    """Render a Jinja template from the ``rpg_core/jinja/`` directory.

    Uses a module-level cached Environment to avoid repeated setup cost.
    """
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(settings.jinja_dir)),
            autoescape=False,
        )
    tpl = _JINJA_ENV.get_template(template_name)
    return tpl.render(**context).strip()


def _count_rounds(messages: list[Message]) -> int:
    """Count user messages in the history portion (exclude last user message)."""
    history = messages[:-1]
    return sum(1 for m in history if m.is_user())


def _flatten_status_tables(
    status_mgr: StatusManager | None,
    exclude_tables: set[tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Flatten StatusManager data into a list of ``{name, headers, rows}``.

    If *exclude_tables* is given (set of ``(type_name, table_name)`` tuples),
    those tables are skipped — used by SceneTracker to avoid duplicating the
    ``当前场景`` table in the generic status layer.
    """
    tables: list[dict[str, object]] = []
    try:
        for type_name in status_mgr.list_types():
            for table_name in status_mgr.list_tables(type_name):
                if exclude_tables and (type_name, table_name) in exclude_tables:
                    continue
                try:
                    tbl = status_mgr.get_table(type_name, table_name)
                    tables.append(tbl)
                except Exception:
                    continue
    except Exception:
        pass
    return tables


# ── builder ──────────────────────────────────────────────────────────


class RPGContextBuilder:
    """将原始消息列表转换为 5 层 RPG 结构。

    Layers (ordered for LLM prefix-cache efficiency):

        Index  Role       Content                         Change frequency
        ─────  ─────────  ─────────────────────────────── ─────────────────
        [0]    system     Fixed Layer (prompt/lore/char)   ★ almost never
        [1]    system     Persistent Memory (常驻记忆)      ★ offline update only
        [2]    system     Summary Layer (conditional)      ★☆ rarely
        [3..N] mixed      Hot History (windowed)           ★★☆ every turn (appended)
        [N+1]  system     Milestones                       ★★☆ plot-driven
        [N+2]  system     Story Memory (剧情记忆)          ★★☆ accumulated details
        [N+3]  system     Recalled Memory (召回)            ★★★ dynamically injected
        [N+4]  system     Status Tables                    ★★★★ most volatile
        [N+5]  user       User Message                     always new

    Prefix cache rule: content after the first changed position is a miss.
    Persistent Memory is split out of Fixed Layer as its own [1] because
    it changes offline (MEMORY.md update) — without the split, any offline
    memory update would invalidate the entire Fixed Layer cache.
    Volatile modules are placed AFTER history so a status-table update only
    evicts [N+3..N+4]; the Fixed + Persistent + Summary + History + Milestones
    prefix remains cached.

    Story Memory lifecycle: records accumulate in day-to-day play, then get
    distilled into Persistent Memory during offline summary — after which
    the store is cleared and the cycle repeats.  This moves the expensive
    cache-miss (PM write) out of the online path.
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

    # ── main entry ──────────────────────────────────────────────────

    def build(
        self,
        system_prompt: str = "",
        messages: list[Message] | None = None,
        character_mgr: CharacterManager | None = None,
        lorebook_mgr: LorebookManager | None = None,
        status_mgr: StatusManager | None = None,
        scene_tracker: SceneTracker | None = None,
    ) -> RPGContext:
        """构建 5 层 RPGContext。

        Args:
            system_prompt: 系统提示词。
            messages: 原始消息列表。仅用于提取历史记录和当前用户输入。
            character_mgr: 角色卡管理器，为 None 时固定层跳过角色卡模块。
            lorebook_mgr: 世界书管理器，为 None 时固定层跳过世界书模块。
            status_mgr: 状态管理器，为 None 时动态层跳过状态表格模块。
        """
        if not messages:
            messages = []

        # ── 1. Parse sources ────────────────────────────────────────
        total_rounds = _count_rounds(messages)

        current_user_msg = messages[-1] if messages and messages[-1].is_user() else None
        user_text = current_user_msg.content if current_user_msg else ""

        # ── 2. Build Fixed Layer ────────────────────────────────────
        lorebook_entries: list[dict] = []
        if lorebook_mgr and self.config.enable_lorebook:
            try:
                lorebook_entries = lorebook_mgr.list_enabled_entries()
            except Exception:
                pass

        characters: list[dict] = []
        if character_mgr and self.config.enable_character:
            try:
                characters = character_mgr.list_enabled_characters()
            except Exception:
                pass

        fixed_content = self._render_layer("layers/fixed_layer.jinja", {
            "system_prompt": system_prompt,
            "world_name": self.world_name,
            "lorebook_entries": lorebook_entries,
            "characters": characters,
        })

        # ── 3. Build Persistent Memory Layer ─────────────────────────
        persistent_content: str | None = None
        if self._persist_memory and self.config.enable_persistent_memory:
            try:
                pm = self._persist_memory.get_sections()
                if pm:
                    persistent_content = self._render_layer("modules/persistent_memory.jinja", {
                        "persistent_memory": pm,
                    })
                    if not persistent_content.strip():
                        persistent_content = None
            except Exception:
                pass

        # ── 4. Build Summary Layer (overall.md only) ──────────────────
        summary_content: str | None = None
        if (
            self.config.enable_summaries
            and total_rounds > self.config.hot_history_rounds
            and self._batch_summary_store
        ):
            try:
                overall, _ = self._batch_summary_store.load_overall()
                if overall:
                    summary_content = self._render_layer("modules/overall_summary.jinja", {
                        "text": overall,
                    })
            except Exception:
                pass

        # ── 5. Extract Hot History ──────────────────────────────────
        history_messages = messages[:-1]  # exclude current user message
        # Filter to keep only rounds >= total_rounds - hot_history_rounds
        hot_history = _slice_hot_history(history_messages, self.config.hot_history_rounds)

        # ── 6. Build Dynamic Layer modules ──────────────────────────
        # Ordered by change frequency (low → high) for prefix cache efficiency:
        #   story memory → recalled memory → status tables (most volatile)
        story_memory_content: str | None = None
        story_details: list[dict] = []
        if self._story_memory and self.config.enable_story_memory:
            try:
                story_details = self._story_memory.get_all()
            except Exception:
                pass
        sm = self._render_layer("modules/story_memory.jinja", {
            "story_details": story_details,
        })
        story_memory_content = sm if sm.strip() else None

        recalled_memory_content: str | None = None
        recalled_items: list[str] = []
        if self._recalled_memory and self.config.enable_recalled_memory:
            try:
                recalled_items = self._recalled_memory.get_items()
            except Exception:
                pass
        rm = self._render_layer("modules/recalled_memory.jinja", {
            "recalled_items": recalled_items,
        })
        recalled_memory_content = rm if rm.strip() else None

        status_tables_content: str | None = None
        status_tables: list[dict] = []
        if status_mgr and self.config.enable_status_tables:
            # 排除 SceneTracker 持有的场景表，避免重复
            exclude = None
            if scene_tracker:
                try:
                    exclude = {scene_tracker.table_key}
                except Exception:
                    pass
            status_tables = _flatten_status_tables(status_mgr, exclude_tables=exclude)
        st = self._render_layer("modules/status_tables.jinja", {
            "status_tables": status_tables,
        })
        status_tables_content = st if st.strip() else None

        # ── 7. Build user message with User Extension Layer ─────────
        user_before = self._build_extension_content(
            [m for m in self.config.user_extension if m.position == "before"],
            {"user_reply_prefix": "接下来是用户的输入："},
        )
        user_after = self._build_extension_content(
            [m for m in self.config.user_extension if m.position == "after"],
            {"user_reply_suffix": "请用中文回复，保持角色设定。"},
        )

        parts = []
        if user_before:
            parts.append(user_before)
        if user_text:
            parts.append(user_text)
        if user_after:
            parts.append(user_after)
        user_content = "\n\n".join(parts)

        # ── 8. Assemble into RPGContext (stable-first for prefix cache) ─
        return RPGContext(
            fixed_layer=fixed_content,
            persistent_memory=persistent_content,
            summary=summary_content,
            hot_history=hot_history,
            story_memory=story_memory_content,
            recalled_memory=recalled_memory_content,
            status_tables=status_tables_content,
            user_before=user_before or None,
            user_input=user_text,
            user_after=user_after or None,
        )

    # ── internal helpers ─────────────────────────────────────────────

    def _render_layer(self, template_name: str, context: dict[str, object]) -> str:
        """Render a layer Jinja template with *context* vars."""
        return render_jinja_template(template_name, **context)

    def _build_extension_content(
        self,
        modules: list[object],
        default_data: dict[str, str],
    ) -> str:
        """Render enabled extension modules and concatenate."""
        blocks: list[str] = []
        for mod in modules:
            if not mod.enabled:
                continue
            try:
                rendered = render_jinja_template(mod.template, **default_data)
                if rendered:
                    blocks.append(rendered)
            except Exception:
                pass
        return "\n\n".join(blocks)


# ── module-level helpers ─────────────────────────────────────────────


def _slice_hot_history(history: list[Message], hot_rounds: int) -> list[Message]:
    """Keep only the last *hot_rounds* user-message rounds from *history*."""
    if hot_rounds <= 0:
        return []

    user_indices = [i for i, m in enumerate(history) if m.is_user()]
    if len(user_indices) <= hot_rounds:
        return history

    cutoff = user_indices[-hot_rounds]
    return history[cutoff:]
