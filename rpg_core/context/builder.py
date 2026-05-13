"""RPGContextBuilder — transform raw messages into the 6-layer RPG structure."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from rpg_world.rpg_core.context.config import RPGContextConfig

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.delta_memory import DeltaMemoryStore
    from rpg_world.rpg_core.memory.persist_memory import PersistentMemoryStore
    from rpg_world.rpg_core.summary.store import SummaryStore


def _count_rounds(messages: list[dict]) -> int:
    """Count user messages in the history portion (exclude last user message)."""
    history = messages[:-1]
    return sum(1 for m in history if m.get("role") == "user")


def _flatten_status_tables(
    status_mgr: Any,
) -> list[dict[str, Any]]:
    """Flatten StatusManager data into a list of ``{name, headers, rows}``."""
    tables: list[dict[str, Any]] = []
    try:
        for type_name in status_mgr.list_types():
            for table_name in status_mgr.list_tables(type_name):
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
    """将原始消息列表转换为 6 层 RPG 结构。

    Layers:
        1. Fixed Layer (system) — system prompt + lorebook + character + persistent memory
        2. Summary Layer (system) — summary index + summary content (conditional)
        3. History Layer (dict list) — raw user/assistant/tool messages (windowed)
        4. Dynamic Layer (system) — milestone index + milestone content + realtime memory + status tables
        5. Dynamic Extension Layer (system) — attention anchor, random events, etc.
        6. User message — user extension modules + user input
    """

    def __init__(
        self,
        config: RPGContextConfig,
        workspace: Path,
        session_id: str = "default",
        world_name: str = "Nanobot Realm",
    ) -> None:
        self.config = config
        self.world_name = world_name

        # Jinja2 environment — resolves {% include %} relative to jinja/
        jinja_dir = Path(__file__).resolve().parent.parent / "jinja"
        self._env = Environment(
            loader=FileSystemLoader(str(jinja_dir)),
            autoescape=False,
        )
        self._jinja_dir = jinja_dir

        # Lazy-initialised stores
        self._summary_store: SummaryStore | None = None
        self._delta_memory: DeltaMemoryStore | None = None
        self._persist_memory: PersistentMemoryStore | None = None
        self._workspace = workspace
        self._session_id = session_id

    # ── store injection (set by hook after construction) ─────────────

    def set_summary_store(self, store: SummaryStore) -> None:
        self._summary_store = store

    def set_delta_memory_store(self, store: DeltaMemoryStore) -> None:
        self._delta_memory = store

    def set_persistent_memory_store(self, store: PersistentMemoryStore) -> None:
        self._persist_memory = store

    # ── main entry ──────────────────────────────────────────────────

    def build(
        self,
        system_prompt: str = "",
        messages: list[dict] | None = None,
        character_mgr: Any = None,
        lorebook_mgr: Any = None,
        milestone_mgr: Any = None,
        status_mgr: Any = None,
    ) -> list[dict]:
        """构建 6 层消息结构。

        Args:
            system_prompt: 系统提示词。
            messages: 原始消息列表。仅用于提取历史记录和当前用户输入。
            character_mgr: 角色卡管理器，为 None 时固定层跳过角色卡模块。
            lorebook_mgr: 世界书管理器，为 None 时固定层跳过世界书模块。
            milestone_mgr: 里程碑管理器，为 None 时动态层跳过里程碑模块。
            status_mgr: 状态管理器，为 None 时动态层跳过状态表格模块。
        """
        if not messages:
            messages = []

        # ── 1. Parse sources ────────────────────────────────────────
        total_rounds = _count_rounds(messages)

        current_user_msg = messages[-1] if messages and messages[-1].get("role") == "user" else None
        user_text = current_user_msg.get("content", "") if current_user_msg else ""

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

        persistent_memory = ""
        if self._persist_memory and self.config.enable_persistent_memory:
            try:
                persistent_memory = self._persist_memory.get_content()
            except Exception:
                pass

        fixed_content = self._render_layer("layers/fixed_layer.jinja", {
            "system_prompt": system_prompt,
            "world_name": self.world_name,
            "lorebook_entries": lorebook_entries,
            "characters": characters,
            "persistent_memory": persistent_memory,
        })

        # ── 3. Build Summary Layer (conditional) ────────────────────
        summary_content: str | None = None
        if (
            self.config.enable_summaries
            and total_rounds > self.config.hot_history_rounds
            and self._summary_store
        ):
            all_summaries = self._summary_store.get_all_summaries()
            max_round = total_rounds - self.config.hot_history_rounds
            relevant = [s for s in all_summaries if s.get("round_end", 0) <= max_round]

            summary_index_items = [
                {"round_start": s["round_start"], "round_end": s["round_end"], "brief": _brief(s.get("text", ""))}
                for s in relevant
            ]

            summary_content = self._render_layer("layers/summary_layer.jinja", {
                "summary_index": summary_index_items,
                "summaries": relevant,
            })
            # Render as None when no content (template returned empty markup)
            if not summary_content or not summary_content.strip():
                summary_content = None

        # ── 4. Extract Hot History ──────────────────────────────────
        history_messages = messages[:-1]  # exclude current user message
        # Filter to keep only rounds >= total_rounds - hot_history_rounds
        hot_history = _slice_hot_history(history_messages, self.config.hot_history_rounds)

        # ── 5. Build Dynamic Layer ──────────────────────────────────
        milestones: list[dict] = []
        if milestone_mgr and self.config.enable_milestones:
            try:
                milestones = milestone_mgr.list_enabled_entries()
            except Exception:
                pass

        realtime_memory = ""
        if self._delta_memory and self.config.enable_realtime_memory:
            try:
                realtime_memory = self._delta_memory.get_content()
            except Exception:
                pass

        status_tables: list[dict] = []
        if status_mgr and self.config.enable_status_tables:
            status_tables = _flatten_status_tables(status_mgr)

        dynamic_content = self._render_layer("layers/dynamic_layer.jinja", {
            "milestone_index": [{"name": ms.get("name", ""), "description": ms.get("description", "")} for ms in milestones],
            "milestones": milestones,
            "realtime_memory": realtime_memory,
            "status_tables": status_tables,
        })

        # ── 6. Build Dynamic Extension Layer ────────────────────────
        ext_content = self._build_extension_content(self.config.dynamic_extension, {
            "attention_anchor": "请专注于当前任务，保持角色设定的一致性。",
            "random_event": "",
        })

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

        # ── 8. Assemble ─────────────────────────────────────────────
        result: list[dict] = []
        result.append({"role": "system", "content": fixed_content})

        if summary_content:
            result.append({"role": "system", "content": summary_content})

        result.extend(hot_history)

        if dynamic_content:
            result.append({"role": "system", "content": dynamic_content})

        if ext_content:
            result.append({"role": "system", "content": ext_content})

        result.append({"role": "user", "content": user_content})

        return result

    # ── internal helpers ─────────────────────────────────────────────

    def _render_layer(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a layer Jinja template with *context* vars."""
        tpl = self._env.get_template(template_name)
        return tpl.render(**context).strip()

    def _build_extension_content(
        self,
        modules: list[Any],
        default_data: dict[str, str],
    ) -> str:
        """Render enabled extension modules and concatenate."""
        blocks: list[str] = []
        for mod in modules:
            if not mod.enabled:
                continue
            try:
                tpl = self._env.get_template(mod.template)
                rendered = tpl.render(**default_data).strip()
                if rendered:
                    blocks.append(rendered)
            except Exception:
                pass
        return "\n\n".join(blocks)


# ── module-level helpers ─────────────────────────────────────────────


def _brief(text: str, max_len: int = 60) -> str:
    """Return the first line of *text*, capped at *max_len* chars."""
    first_line = text.split("\n")[0] if text else ""
    return first_line[:max_len] + "…" if len(first_line) > max_len else first_line


def _slice_hot_history(history: list[dict], hot_rounds: int) -> list[dict]:
    """Keep only the last *hot_rounds* user-message rounds from *history*."""
    if hot_rounds <= 0:
        return []

    user_indices = [i for i, m in enumerate(history) if m.get("role") == "user"]
    if len(user_indices) <= hot_rounds:
        return history

    cutoff = user_indices[-hot_rounds]
    return history[cutoff:]
