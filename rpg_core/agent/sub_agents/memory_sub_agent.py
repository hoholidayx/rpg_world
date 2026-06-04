"""MemorySubAgent — 总结归纳、记忆记录、召回子 Agent.

继承 ``BaseSubAgent``，通过 ``SubAgentContext`` 获取世界书 + 角色卡上下文，
确保记忆提取/召回/摘要判断不会 OOC。

纯函数式设计：接受 ``context: dict``，处理，返回结果，不维护轮次状态。
调用方决定传入什么内容、何时触发摘要。

Usage::

    from rpg_world.rpg_core.agent.sub_agents import MemorySubAgent, SubAgentContext

    agent = MemorySubAgent(
        recalled_store=recalled_store,
        story_store=story_store,
        summary_store=summary_store,
    )
    agent.bind_context(sub_agent_context)
    result = await agent.process({
        "recall": recent_conversation,
        "story": new_content,
        "summary": content_to_summarize,
    })
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger

from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent

# ── constants ──────────────────────────────────────────────────────────

_TAG = "[MemorySubAgent]"

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
                    "description": "与当前上下文直接相关的项。保守——只包含真正相关的。",
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
        "description": "生成对话摘要",
        "parameters": {
            "type": "object",
            "properties": {
                "summary_text": {
                    "type": "string",
                    "description": "摘要文本，捕捉关键剧情事件和发展。",
                },
            },
            "required": ["summary_text"],
        },
    },
}


# ── system prompts (one per pipeline) ─────────────────────────────────

RECALL_PROMPT = """\
You are a context-relevance analyzer for an RPG game master. Your job is to \
scan the conversation below and identify context items immediately relevant \
to the user's latest input. These are injected as "recalled memory" to help \
the game master stay consistent.

Focus on:
- Unresolved plot threads or dangling story hooks
- Recent character state changes (injuries, emotional shifts, new items)
- Immediate environmental context the user is interacting with
- Recent NPC statements or promises

Call `extract_recalls` with at most {max_items} items. \
Be conservative — only include what is truly relevant.\
"""

STORY_MEMORY_PROMPT = """\
You are a narrative detail extractor for an RPG. Scan the conversation turns \
and extract notable character or plot details for long-term story memory.

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
You are a conversation summarizer for an RPG. Generate a concise summary of \
the conversation below, capturing key story events and developments.

Focus on:
- Major story events and plot developments
- Character arcs and changes
- Key decisions with lasting consequences
- Current party status and objectives

Call `generate_summary` with the summary text.\
"""


# ── result ────────────────────────────────────────────────────────────


@dataclass
class MemoryAgentResult:
    """Result returned by :meth:`MemorySubAgent.process`."""

    recalls_injected: int = 0
    story_details_added: int = 0
    summary_generated: bool = False
    skipped: bool = False


# ── sub-agent ─────────────────────────────────────────────────────────


class MemorySubAgent(BaseSubAgent):
    """记忆子 Agent —— 三个独立处理管道：召回 / 剧情记忆 / 摘要。

    继承自 ``BaseSubAgent``，使用基类的 provider 管理、重入守卫以及
    SubAgentContext 绑定。每个 pipeline 的提示词中都会注入世界书 + 角色卡上下文。

    纯函数式、无状态设计。``process()`` 接受一个 ``context`` dict，
    调用方决定传入什么内容，sub_agent 不维护轮次或进度状态。

    Parameters
    ----------
    recalled_store:
        召回记忆存储。
    story_store:
        剧情记忆存储。
    summary_store:
        摘要存储。
    provider:
        可选独立 LLM provider。未提供时内部按 *model* / *api_key* / *base_url* 创建。
    model:
        LLM 模型名（provider 为 None 时生效）。
    api_key:
        LLM API key（provider 为 None 时生效）。
    base_url:
        LLM base URL（provider 为 None 时生效）。
    enabled:
        总开关。
    max_recall_items:
        每轮最大召回项数。
    max_story_details:
        每轮最大剧情记忆条目数。
    max_window_rounds:
        传入 LLM 的最大对话窗口（用户轮次数）。
    """

    def __init__(
        self,
        *,
        recalled_store: Any = None,
        story_store: Any = None,
        summary_store: Any = None,
        provider: Any = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
        max_recall_items: int = 5,
        max_story_details: int = 10,
        max_window_rounds: int = 10,
    ) -> None:
        super().__init__(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            enabled=enabled,
        )

        # MemorySubAgent 不使用独立的 _own_provider（通过基类 _get_provider 获取）
        # 但保留旧的 _provider 属性用于兼容（如果有外部代码直接访问）
        self._provider: Any = provider

        self._recalled_store = recalled_store
        self._story_store = story_store
        self._summary_store = summary_store
        self._max_recall_items = max_recall_items
        self._max_story_details = max_story_details
        self._max_window_rounds = max_window_rounds

    # ── public API ─────────────────────────────────────────────────────

    async def process(self, context: dict) -> MemoryAgentResult:
        """处理 *context* 中的内容，更新对应记忆存储。

        *context* 支持的 key:

        ========= =========================  ============================
        key       值类型                     作用
        ========= =========================  ============================
        ``recall`` ``list[dict]`` (optional)  扫描对话提取召回项
        ``story`` ``list[dict]`` (optional)  提取剧情细节追加持久化
        ``summary`` ``list[dict]`` (optional) 生成摘要追加到 SummaryStore
        ========= =========================  ============================

        每个 key 独立处理，互不影响。
        """
        if self._busy:
            logger.debug(_TAG + " skipped (re-entrancy guard)")
            return MemoryAgentResult(skipped=True)

        if not self._enabled:
            return MemoryAgentResult(skipped=True)

        self._busy = True
        try:
            result = MemoryAgentResult()

            if "recall" in context and self._recalled_store:
                result.recalls_injected = await self._pipeline_recall(
                    context["recall"]
                )

            if "story" in context and self._story_store:
                result.story_details_added = await self._pipeline_story_memory(
                    context["story"]
                )

            if "summary" in context and self._summary_store:
                result.summary_generated = await self._pipeline_summary(
                    context["summary"]
                )

            return result

        finally:
            self._busy = False

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

    async def _pipeline_recall(self, conv: list[dict]) -> int:
        """提取召回项，全量替换 RecalledMemoryStore。"""
        window = self._format_conversation_window(conv, self._max_window_rounds)

        system_content = self._build_system_context(
            RECALL_PROMPT.replace("{max_items}", str(self._max_recall_items))
        )

        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    f"## Conversation\n\n{window}\n\n"
                    f"Call `extract_recalls` with relevant context items."
                ),
            },
        ]

        decision = await self._call_llm(messages, RECALL_SCHEMA)
        recalls = decision.get("recalls", [])[: self._max_recall_items]

        if recalls and self._recalled_store:
            try:
                self._recalled_store.set_items(recalls)
                logger.debug(_TAG + " injected {} recall items", len(recalls))
                return len(recalls)
            except Exception as exc:
                logger.warning(_TAG + " failed to write recalls: {}", exc)

        return 0

    # ── Pipeline 2: 剧情记忆 ─────────────────────────────────────────

    async def _pipeline_story_memory(self, conv: list[dict]) -> int:
        """提取剧情细节，追加到 StoryMemoryStore。"""
        window = self._format_conversation_window(conv)

        # 已有剧情记忆（去重参考）
        existing = _format_store_items(
            self._story_store.get_all() if self._story_store else [],
            key=lambda d: d.get("text", str(d)) if isinstance(d, dict) else str(d),
            max_items=self._max_story_details,
        )

        system_content = self._build_system_context(
            STORY_MEMORY_PROMPT.replace("{max_items}", str(self._max_story_details))
        )

        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    f"## Conversation Content\n\n{window}\n\n"
                    f"## Existing Story Memory (for deduplication)\n"
                    f"{existing}\n\n"
                    f"Call `extract_story_details` with notable details."
                ),
            },
        ]

        decision = await self._call_llm(messages, STORY_DETAIL_SCHEMA)
        details = decision.get("story_details", [])[: self._max_story_details]

        added = 0
        if details and self._story_store:
            for detail in details:
                try:
                    self._story_store.add_detail(detail, {"source": "memory_sub_agent"})
                    added += 1
                except Exception as exc:
                    logger.warning(
                        _TAG + " failed to add story detail: {}", exc
                    )
            if added:
                logger.debug(_TAG + " added {} story details", added)

        return added

    # ── Pipeline 3: 摘要 ─────────────────────────────────────────────

    async def _pipeline_summary(self, conv: list[dict]) -> bool:
        """生成摘要文本，追加到 SummaryStore。"""
        window = self._format_conversation_window(conv)

        system_content = self._build_system_context(SUMMARY_PROMPT)

        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    f"## Conversation\n\n{window}\n\n"
                    f"Call `generate_summary` with the summary text."
                ),
            },
        ]

        decision = await self._call_llm(messages, SUMMARY_SCHEMA)
        text = decision.get("summary_text", "")

        if text and self._summary_store:
            try:
                self._summary_store.set_summary(text)
                logger.debug(_TAG + " generated summary")
                return True
            except Exception as exc:
                logger.warning(
                    _TAG + " failed to write summary: {}", exc
                )

        return False

    # ── internal — shared helpers ──────────────────────────────────────

    async def _call_llm(
        self,
        messages: list[dict],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Call provider with *messages* and *schema*, return parsed arguments."""
        # _provider 字段保留给 old _call_llm 兼容；新代码通过基类 _get_provider() 获取
        provider = self._get_provider()

        try:
            result = await provider.chat(messages, tools=[schema])
        except Exception as exc:
            logger.warning(_TAG + " LLM call failed: {}", exc)
            return {}

        tool_calls = result.get("tool_calls")
        if not tool_calls:
            logger.warning(_TAG + " LLM returned no tool calls")
            return {}

        try:
            return json.loads(tool_calls[0]["function"]["arguments"])
        except (KeyError, json.JSONDecodeError, IndexError) as exc:
            logger.warning(
                _TAG + " failed to parse function args: {}", exc
            )
            return {}

    def _format_conversation_window(
        self,
        history: list[dict],
        max_rounds: int | None = None,
    ) -> str:
        """Format conversation as readable ``Role: text`` lines, windowed."""
        if max_rounds is not None:
            user_indices = [
                i for i, m in enumerate(history) if m.get("role") == "user"
            ]
            if len(user_indices) > max_rounds:
                history = history[user_indices[-max_rounds]:]

        lines: list[str] = []
        for msg in history:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content or role == "system":
                continue
            label = {"user": "User", "assistant": "Assistant"}.get(
                role, role.capitalize()
            )
            lines.append(f"{label}: {content[:500]}")

        return "\n\n".join(lines) if lines else "(no conversation content)"


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
