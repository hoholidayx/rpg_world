"""MemorySubAgent — 总结归纳、记忆记录、召回子 Agent.

Structured output via function calling (``memory_analysis``).

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


# ── structured output schema ──────────────────────────────────────────

MEMORY_FUNCTION_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "memory_analysis",
        "description": "分析对话轮次，输出结构化记忆决策",
        "parameters": {
            "type": "object",
            "properties": {
                "recalls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "与当前用户输入直接相关的上下文项，将被注入到召回记忆中。"
                        "保守——只包含真正相关的。"
                    ),
                },
                "story_details": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "需要持久化为剧情记忆的 notable character/plot 细节。"
                        "偏好具体、事实性的陈述。"
                    ),
                },
                "trigger_summary": {
                    "type": "boolean",
                    "description": "是否生成新的对话摘要。",
                },
                "summary_start_round": {
                    "type": "integer",
                    "description": "摘要的起始轮次号。trigger_summary 为 true 时必需。",
                },
                "summary_end_round": {
                    "type": "integer",
                    "description": "摘要的结束轮次号。trigger_summary 为 true 时必需。",
                },
                "summary_text": {
                    "type": "string",
                    "description": "摘录关键事件的摘要文本。trigger_summary 为 true 时必需。",
                },
            },
            "required": ["recalls", "story_details", "trigger_summary"],
        },
    },
}


SYSTEM_PROMPT = """\
You are a memory management subsystem for a text-based RPG game master agent. \
Your job is to analyze conversation turns and output structured memory decisions.

## Your Three Responsibilities

### 1. RECALL
Extract context items from the conversation that are immediately relevant to \
the current user input. These are injected as "recalled memory" to help the \
main agent stay consistent. Focus on:
- Unresolved plot threads or dangling story hooks
- Recent character state changes (injuries, emotional shifts, new items)
- Immediate environmental context the user is interacting with
- Recent NPC statements or promises
Limit: at most MAX_RECALL_ITEMS items. Be conservative.

### 2. STORY DETAILS
Extract notable character or plot details that should be persisted as long-term \
story memory. These accumulate over multiple sessions. Focus on:
- New character introductions with notable traits
- Important revelations or discoveries
- Character relationship developments
- Significant choices made by the player
- World-building details revealed through the narrative
Limit: at most MAX_STORY_DETAILS items. Prefer specific, factual statements.

### 3. SUMMARIZATION
Decide whether to generate a new conversation summary. A summary should be \
triggered when conversation rounds since the last summary reach or exceed \
SUMMARY_TRIGGER_ROUNDS rounds. The summary should capture:
- Major story events and plot developments
- Character arcs and changes
- Key decisions with lasting consequences
- Current party status and objectives

## Output Format
You MUST respond by calling the `memory_analysis` function with all fields. \
Do not include any other text in your response.\
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
    """记忆子 Agent —— 总结归纳、记忆记录、召回。

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
        每次调用传递给 LLM 的最大对话轮次（新内容窗口）。
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
        self._provider = provider  # may be None
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
        """处理本轮新对话内容，更新三个记忆存储。

        幂等安全：连续调用两次，第二次返回 ``skipped=True``。
        """
        # ── guards ────────────────────────────────────────────────
        if self._is_processing:
            logger.debug("[MemorySubAgent] skipped (re-entrancy guard)")
            return MemoryAgentResult(skipped=True)

        if not self._enabled:
            return MemoryAgentResult(skipped=True)

        current_length = len(main_history)
        if current_length <= self._last_processed_length:
            logger.debug(
                "[MemorySubAgent] skipped (no new content: {} ≤ {})",
                current_length,
                self._last_processed_length,
            )
            return MemoryAgentResult(skipped=True)

        self._is_processing = True
        try:
            new_slice = main_history[self._last_processed_length:]
            total_rounds = self._count_main_rounds(main_history)

            messages = self._build_messages(
                history_slice=new_slice,
                total_rounds=total_rounds,
            )

            decision = await self._call_llm(messages)
            result = await self._apply_decisions(decision)

            self._last_processed_length = current_length
            self._save_state()

            return result

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

    # ── internal — message building ────────────────────────────────────

    def _build_messages(
        self,
        history_slice: list[dict],
        total_rounds: int,
    ) -> list[dict]:
        """构建 sub-agent 的 LLM 消息列表。"""
        window = self._format_conversation_window(history_slice)

        # Current store state (for deduplication context)
        existing_story = _format_store_items(
            self._story_store.get_all() if self._story_store else [],
            key=lambda d: d.get("text", str(d)) if isinstance(d, dict) else str(d),
            max_items=self._max_story_details,
        )
        existing_recalls = _format_store_items(
            self._recalled_store.get_items() if self._recalled_store else [],
            max_items=None,
        )

        rounds_since_summary = max(0, total_rounds - self._last_summary_round)

        # Inject config values into system prompt
        sys_prompt = (
            SYSTEM_PROMPT.replace("MAX_RECALL_ITEMS", str(self._max_recall_items))
            .replace("MAX_STORY_DETAILS", str(self._max_story_details))
            .replace("SUMMARY_TRIGGER_ROUNDS", str(self._summary_trigger_rounds))
        )

        user_msg = (
            f"## Conversation Window (new content since last processing)\n\n"
            f"{window}\n\n"
            f"## Current Round\n"
            f"Total user rounds so far: {total_rounds}\n"
            f"Rounds since last summary: {rounds_since_summary}\n\n"
            f"## Existing Story Memory (for deduplication)\n"
            f"{existing_story}\n\n"
            f"## Existing Recalled Memory (for deduplication)\n"
            f"{existing_recalls}\n\n"
            f"Analyze the conversation above and call "
            f"`memory_analysis` with your structured decisions."
        )

        return [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

    def _format_conversation_window(self, history_slice: list[dict]) -> str:
        """Format history slice as readable conversation text, windowed."""
        # Keep only the last ``max_window_rounds`` user-message rounds
        user_indices = [
            i
            for i, m in enumerate(history_slice)
            if m.get("role") == "user"
        ]
        if len(user_indices) > self._max_window_rounds:
            cutoff = user_indices[-self._max_window_rounds]
            history_slice = history_slice[cutoff:]

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

    # ── internal — LLM call ───────────────────────────────────────────

    async def _call_llm(self, messages: list[dict]) -> dict[str, Any]:
        """Call provider and parse structured output from ``memory_analysis``."""
        if self._provider is None:
            self._provider = OpenAIProvider(
                model=self._model,
                api_key=self._api_key,
                base_url=self._base_url,
            )
        try:
            result = await self._provider.chat(
                messages,
                tools=[MEMORY_FUNCTION_SCHEMA],
            )
        except Exception as exc:
            logger.warning("[MemorySubAgent] LLM call failed: {}", exc)
            return {}

        tool_calls = result.get("tool_calls")
        if not tool_calls:
            logger.warning("[MemorySubAgent] LLM returned no tool calls")
            return {}

        try:
            args = json.loads(tool_calls[0]["function"]["arguments"])
        except (KeyError, json.JSONDecodeError, IndexError) as exc:
            logger.warning(
                "[MemorySubAgent] failed to parse function args: {}", exc
            )
            return {}

        return args

    # ── internal — apply decisions ─────────────────────────────────────

    async def _apply_decisions(
        self,
        decision: dict[str, Any],
    ) -> MemoryAgentResult:
        """Write structured decisions to the three stores."""
        result = MemoryAgentResult()

        if not decision:
            return result

        # 1. Recalled Memory — 全量替换
        recalls: list[str] = decision.get("recalls", [])[: self._max_recall_items]
        if recalls and self._recalled_store:
            try:
                self._recalled_store.set_items(recalls)
                result.recalls_injected = len(recalls)
                logger.debug(
                    "[MemorySubAgent] injected {} recall items", len(recalls)
                )
            except Exception as exc:
                logger.warning(
                    "[MemorySubAgent] failed to write recalls: {}", exc
                )

        # 2. Story Memory — 追加
        details: list[str] = decision.get("story_details", [])[
            : self._max_story_details
        ]
        if details and self._story_store:
            for detail in details:
                try:
                    self._story_store.add_detail(
                        detail, {"source": "memory_sub_agent"}
                    )
                    result.story_details_added += 1
                except Exception as exc:
                    logger.warning(
                        "[MemorySubAgent] failed to add story detail: {}", exc
                    )
            if result.story_details_added:
                logger.debug(
                    "[MemorySubAgent] added {} story details",
                    result.story_details_added,
                )

        # 3. Summary — 条件触发
        if decision.get("trigger_summary") and self._summary_store:
            start = decision.get("summary_start_round", 0)
            end = decision.get("summary_end_round", 0)
            text = decision.get("summary_text", "")

            if start >= 0 and end > start and text:
                try:
                    self._summary_store.set_summary(start, end, text)
                    self._last_summary_round = end
                    result.summary_generated = True
                    result.summary_range = (start, end)
                    logger.debug(
                        "[MemorySubAgent] generated summary [{}-{}]",
                        start,
                        end,
                    )
                except Exception as exc:
                    logger.warning(
                        "[MemorySubAgent] failed to write summary: {}", exc
                    )

        return result

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
