"""MemorySubAgent — 总结归纳、记忆记录、召回子 Agent.

三个职责完全解耦，各自独立提示词、独立 LLM 调用、独立容错。

Usage::

    from rpg_world.rpg_core.memory import StoryMemoryStore, RecalledMemoryStore
    from rpg_world.rpg_core.summary.store import SummaryStore
    from rpg_world.rpg_core.agent.memory_sub_agent import MemorySubAgent

    agent = MemorySubAgent(
        recalled_store=recalled_store,
        story_store=story_store,
        summary_store=summary_store,
        model="gpt-4o",
    )
    result = await agent.process(history)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider


# ── function schemas (one per pipeline) ───────────────────────────────

RECALL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_recalls",
        "description": "从对话中提取与当前上下文直接相关的召回项",
        "parameters": {
            "type": "object",
            "properties": {
                "recalls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "与当前用户输入直接相关的上下文项。保守——只包含真正相关的。",
                },
            },
            "required": ["recalls"],
        },
    },
}

STORY_DETAIL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_story_details",
        "description": "从对话中提取 notable 角色/剧情细节用于持久化",
        "parameters": {
            "type": "object",
            "properties": {
                "story_details": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要持久化为剧情记忆的 notable 细节。偏好具体、事实性的陈述。",
                },
            },
            "required": ["story_details"],
        },
    },
}

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_summary",
        "description": "生成对话摘要，总结关键剧情事件和发展",
        "parameters": {
            "type": "object",
            "properties": {
                "summary_start_round": {
                    "type": "integer",
                    "description": "摘要的起始轮次号。",
                },
                "summary_end_round": {
                    "type": "integer",
                    "description": "摘要的结束轮次号。",
                },
                "summary_text": {
                    "type": "string",
                    "description": "摘录关键事件的摘要文本。",
                },
            },
            "required": ["summary_start_round", "summary_end_round", "summary_text"],
        },
    },
}


# ── system prompts (one per pipeline) ─────────────────────────────────

RECALL_PROMPT = """\
You are a context-relevance analyzer for an RPG game master. Your job is to \
scan the recent conversation and identify context items that are immediately \
relevant to the user's latest input. These will be injected as "recalled \
memory" to help the game master stay consistent.

Focus on:
- Unresolved plot threads or dangling story hooks
- Recent character state changes (injuries, emotional shifts, new items)
- Immediate environmental context the user is interacting with
- Recent NPC statements or promises

Call `extract_recalls` with at most {max_items} items. \
Be conservative — only include what is truly relevant to the current moment.\
"""

STORY_MEMORY_PROMPT = """\
You are a narrative detail extractor for an RPG. Your job is to scan \
conversation turns and extract notable character or plot details that \
should be persisted as long-term story memory. These accumulate across \
sessions.

Focus on:
- New character introductions with notable traits
- Important revelations or discoveries
- Character relationship developments
- Significant choices made by the player
- World-building details revealed through the narrative

Call `extract_story_details` with at most {max_items} items. \
Prefer specific, factual statements. Avoid vague observations.\
"""

SUMMARY_PROMPT = """\
You are a conversation summarizer for an RPG. Your job is to generate a \
concise summary of recent conversation rounds, capturing key story events \
and developments.

Focus on:
- Major story events and plot developments
- Character arcs and changes
- Key decisions with lasting consequences
- Current party status and objectives

Call `generate_summary` with the round range and summary text.\
"""


# ── result ────────────────────────────────────────────────────────────


@dataclass
class MemoryAgentResult:
    """Result returned by :meth:`MemorySubAgent.process`."""

    recalls_injected: int = 0
    story_details_added: int = 0
    summary_generated: bool = False
    summary_range: tuple[int, int] | None = None
    skipped: bool = False


# ── sub-agent ─────────────────────────────────────────────────────────


class MemorySubAgent:
    """记忆子 Agent —— 三个独立处理管道：召回 / 剧情记忆 / 摘要。

    Parameters
    ----------
    recalled_store:
        召回记忆存储（write-only 接入点）。
    story_store:
        剧情记忆存储。
    summary_store:
        摘要存储。
    provider:
        可选的独立 LLM provider。未提供时由本类根据 *model* /
        *api_key* / *base_url* 内部创建。
    model:
        默认 LLM 模型名（provider 为 None 时生效）。
    api_key:
        默认 LLM API key（provider 为 None 时生效）。
    base_url:
        默认 LLM base URL（provider 为 None 时生效）。
    session_id:
        会话标识，用于内部状态持久化文件路径。
    persistence_path:
        内部状态持久化目录。为 None 时使用 settings 中的 sub_agent_path。
    enabled:
        总开关。
    summary_trigger_rounds:
        距离上次摘要多少轮后触发新摘要。
    max_recall_items:
        每轮最大召回项数。
    max_story_details:
        每轮最大剧情记忆条目数。
    max_window_rounds:
        每次调用传递给 LLM 的最大对话轮次。
    """

    def __init__(
        self,
        *,
        recalled_store: Any = None,
        story_store: Any = None,
        summary_store: Any = None,
        provider: OpenAIProvider | None = None,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        session_id: str = "default",
        persistence_path: str | Path | None = None,
        enabled: bool = True,
        summary_trigger_rounds: int = 20,
        max_recall_items: int = 5,
        max_story_details: int = 10,
        max_window_rounds: int = 10,
    ) -> None:
        self._recalled_store = recalled_store
        self._story_store = story_store
        self._summary_store = summary_store
        self._session_id = session_id
        self._enabled = enabled
        self._summary_trigger_rounds = summary_trigger_rounds
        self._max_recall_items = max_recall_items
        self._max_story_details = max_story_details
        self._max_window_rounds = max_window_rounds

        # LLM provider (lazy — avoid creating OpenAI client if disabled)
        self._provider: OpenAIProvider | None = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url

        # Internal state
        self._is_processing: bool = False
        self._last_processed_length: int = 0
        self._last_summary_round: int = 0

        # Persistence path
        if persistence_path is not None:
            p = Path(persistence_path)
        else:
            try:
                from rpg_world.rpg_core.settings import settings

                p = Path(settings.sub_agent_path)
            except Exception:
                p = Path("data") / "memory_sub_agent"
        self._state_file = p / f"{session_id}.json"

        self._load_state()

    # ── public API ─────────────────────────────────────────────────────

    async def process(self, main_history: list[dict]) -> MemoryAgentResult:
        """处理本轮新对话内容，依次执行三个独立管道。

        幂等安全：连续调用两次，第二次返回 ``skipped=True``。
        """
        # ── guards ────────────────────────────────────────────────
        if self._is_processing:
            logger.debug("[MemorySubAgent] skipped (re-entrancy guard)")
            return MemoryAgentResult(skipped=True)

        if not self._enabled:
            return MemoryAgentResult(skipped=True)

        if len(main_history) <= self._last_processed_length:
            logger.debug(
                "[MemorySubAgent] skipped (no new content: {} ≤ {})",
                len(main_history),
                self._last_processed_length,
            )
            return MemoryAgentResult(skipped=True)

        self._is_processing = True
        try:
            total_rounds = self._count_main_rounds(main_history)

            # 三个独立管道，每个有自己的提示词 / LLM 调用 / 容错
            recall_count = await self._pipeline_recall(main_history, total_rounds)
            story_count = await self._pipeline_story_memory(main_history, total_rounds)
            summary_gen, summary_range = await self._pipeline_summary(
                main_history, total_rounds
            )

            self._last_processed_length = len(main_history)
            self._save_state()

            return MemoryAgentResult(
                recalls_injected=recall_count,
                story_details_added=story_count,
                summary_generated=summary_gen,
                summary_range=summary_range,
            )

        finally:
            self._is_processing = False

    def update_store_refs(
        self,
        recalled_store: Any = None,
        story_store: Any = None,
        summary_store: Any = None,
    ) -> None:
        """更新 store 引用（RPG context reload 后调用）。"""
        if recalled_store is not None:
            self._recalled_store = recalled_store
        if story_store is not None:
            self._story_store = story_store
        if summary_store is not None:
            self._summary_store = summary_store

    # ── Pipeline 1: 召回 ─────────────────────────────────────────────

    async def _pipeline_recall(
        self,
        main_history: list[dict],
        total_rounds: int,
    ) -> int:
        """提取与当前上下文直接相关的召回项，写入 RecalledMemoryStore。"""
        # 窗口：最近几轮对话（包括当前用户输入）
        window = self._slice_recent_rounds(main_history, self._max_window_rounds)

        messages = [
            {
                "role": "system",
                "content": RECALL_PROMPT.replace(
                    "{max_items}", str(self._max_recall_items)
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## Conversation (last {self._max_window_rounds} rounds)\n\n"
                    f"{window}\n\n"
                    f"Extract context items relevant to the current user input "
                    f"and call `extract_recalls`."
                ),
            },
        ]

        decision = await self._call_llm(messages, RECALL_SCHEMA)
        recalls: list[str] = decision.get("recalls", [])[: self._max_recall_items]

        if recalls and self._recalled_store:
            try:
                self._recalled_store.set_items(recalls)
                logger.debug("[MemorySubAgent] injected {} recall items", len(recalls))
                return len(recalls)
            except Exception as exc:
                logger.warning("[MemorySubAgent] failed to write recalls: {}", exc)

        return 0

    # ── Pipeline 2: 剧情记忆 ─────────────────────────────────────────

    async def _pipeline_story_memory(
        self,
        main_history: list[dict],
        total_rounds: int,
    ) -> int:
        """提取 notable 角色/剧情细节，追加到 StoryMemoryStore。"""
        # 窗口：本轮新增内容（上次处理到现在的切片）
        new_slice = main_history[self._last_processed_length:]
        window = self._format_conversation_window(new_slice)

        # 已有剧情记忆（去重参考）
        existing = _format_store_items(
            self._story_store.get_all() if self._story_store else [],
            key=lambda d: d.get("text", str(d)) if isinstance(d, dict) else str(d),
            max_items=self._max_story_details,
        )

        messages = [
            {
                "role": "system",
                "content": STORY_MEMORY_PROMPT.replace(
                    "{max_items}", str(self._max_story_details)
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## New Conversation Content\n\n"
                    f"{window}\n\n"
                    f"## Existing Story Memory (for deduplication)\n"
                    f"{existing}\n\n"
                    f"Extract notable details from the new content above "
                    f"and call `extract_story_details`."
                ),
            },
        ]

        decision = await self._call_llm(messages, STORY_DETAIL_SCHEMA)
        details: list[str] = decision.get("story_details", [])[
            : self._max_story_details
        ]

        added = 0
        if details and self._story_store:
            for detail in details:
                try:
                    self._story_store.add_detail(detail, {"source": "memory_sub_agent"})
                    added += 1
                except Exception as exc:
                    logger.warning(
                        "[MemorySubAgent] failed to add story detail: {}", exc
                    )
            if added:
                logger.debug("[MemorySubAgent] added {} story details", added)

        return added

    # ── Pipeline 3: 摘要 ─────────────────────────────────────────────

    async def _pipeline_summary(
        self,
        main_history: list[dict],
        total_rounds: int,
    ) -> tuple[bool, tuple[int, int] | None]:
        """条件触发：轮次达到阈值时生成对话摘要写入 SummaryStore。"""
        rounds_since = total_rounds - self._last_summary_round
        if rounds_since < self._summary_trigger_rounds:
            return False, None

        if not self._summary_store:
            return False, None

        # 窗口：上次摘要至今的对话内容
        window = self._slice_recent_rounds(main_history, rounds_since)

        messages = [
            {"role": "system", "content": SUMMARY_PROMPT},
            {
                "role": "user",
                "content": (
                    f"## Conversation Content (rounds {self._last_summary_round}"
                    f"–{total_rounds})\n\n"
                    f"{window}\n\n"
                    f"Generate a summary of the above conversation and "
                    f"call `generate_summary`."
                ),
            },
        ]

        decision = await self._call_llm(messages, SUMMARY_SCHEMA)
        start = decision.get("summary_start_round", 0)
        end = decision.get("summary_end_round", 0)
        text = decision.get("summary_text", "")

        if start >= 0 and end > start and text:
            try:
                self._summary_store.set_summary(start, end, text)
                self._last_summary_round = end
                logger.debug(
                    "[MemorySubAgent] generated summary [{}-{}]", start, end
                )
                return True, (start, end)
            except Exception as exc:
                logger.warning(
                    "[MemorySubAgent] failed to write summary: {}", exc
                )

        return False, None

    # ── internal — shared helpers ──────────────────────────────────────

    async def _call_llm(
        self,
        messages: list[dict],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Call provider with *messages* and *schema*, return parsed arguments."""
        if self._provider is None:
            self._provider = OpenAIProvider(
                model=self._model,
                api_key=self._api_key,
                base_url=self._base_url,
            )

        try:
            result = await self._provider.chat(messages, tools=[schema])
        except Exception as exc:
            logger.warning("[MemorySubAgent] LLM call failed: {}", exc)
            return {}

        tool_calls = result.get("tool_calls")
        if not tool_calls:
            logger.warning("[MemorySubAgent] LLM returned no tool calls")
            return {}

        try:
            return json.loads(tool_calls[0]["function"]["arguments"])
        except (KeyError, json.JSONDecodeError, IndexError) as exc:
            logger.warning(
                "[MemorySubAgent] failed to parse function args: {}", exc
            )
            return {}

    def _slice_recent_rounds(
        self,
        history: list[dict],
        n_rounds: int,
    ) -> str:
        """取最近 *n_rounds* 轮用户消息的对话文本。"""
        user_indices = [
            i for i, m in enumerate(history) if m.get("role") == "user"
        ]
        if not user_indices:
            return "(no conversation)"

        cutoff = user_indices[-n_rounds] if n_rounds < len(user_indices) else 0
        return self._format_conversation_window(history[cutoff:])

    def _format_conversation_window(self, history_slice: list[dict]) -> str:
        """Format history slice as readable ``Role: text`` lines."""
        lines: list[str] = []
        for msg in history_slice:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content or role == "system":
                continue
            label = {"user": "User", "assistant": "Assistant"}.get(
                role, role.capitalize()
            )
            lines.append(f"{label}: {content[:500]}")
        return "\n\n".join(lines) if lines else "(no conversation content)"

    # ── internal — state persistence ───────────────────────────────────

    @staticmethod
    def _count_main_rounds(main_history: list[dict]) -> int:
        """Count user messages in main_history."""
        return sum(1 for m in main_history if m.get("role") == "user")

    def _save_state(self) -> None:
        """Persist internal state to disk."""
        data = {
            "last_processed_length": self._last_processed_length,
            "last_summary_round": self._last_summary_round,
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[MemorySubAgent] failed to save state: {}", exc)

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        try:
            raw = self._state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._last_processed_length = data.get("last_processed_length", 0)
            self._last_summary_round = data.get("last_summary_round", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        except Exception as exc:
            logger.warning("[MemorySubAgent] failed to load state: {}", exc)


# ── helpers ───────────────────────────────────────────────────────────


def _format_store_items(
    items: list[Any],
    *,
    key: Any = str,
    max_items: int | None = None,
) -> str:
    """Format store items as a bullet list string."""
    if max_items is not None:
        items = items[-max_items:]
    if not items:
        return "(empty)"
    return "\n".join(f"- {key(item)}" for item in items)
