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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent
from rpg_world.rpg_core.agent.agent_types import CallRecord, LLMResponse
from rpg_world.rpg_core.agent.command import CommandDef
from rpg_world.rpg_core.context.rpg_context import Message, Role

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent
    from rpg_world.rpg_core.agent.base_provider import LLMProvider
    from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
    from rpg_world.rpg_core.memory.story_memory import StoryMemoryStore
    from rpg_world.rpg_core.summary.store import SummaryStore
    from rpg_world.rpg_core.session.manager import SessionManager

# ── constants ──────────────────────────────────────────────────────────

_TAG = "[MemorySubAgent]"
COMMAND_NAME_COMPACT = "/compact"
COMMAND_NAME_EXTRACT_STORY = "/extract_story_memory"
"""此子 Agent 注册到 CommandDispatcher 的斜杠命令名。"""

# ── function schemas (one per pipeline) ───────────────────────────────

RECALL_SCHEMA: dict[str, object] = {
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

STORY_DETAIL_SCHEMA: dict[str, object] = {
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

SUMMARY_SCHEMA: dict[str, object] = {
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
    call_stats: list[CallRecord] = field(default_factory=list)
    """此过程涉及的 LLM 调用记录（usage / timing）。"""


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
    max_window_rounds:
        传入 LLM 的最大对话窗口（用户轮次数）。
    """

    def __init__(
        self,
        *,
        recalled_store: RecalledMemoryStore | None = None,
        story_store: StoryMemoryStore | None = None,
        summary_store: SummaryStore | None = None,
        provider: LLMProvider | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
        max_recall_items: int = 5,
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
        self._provider: LLMProvider | None = provider

        self._recalled_store = recalled_store
        self._story_store = story_store
        self._summary_store = summary_store
        self._max_recall_items = max_recall_items
        self._max_window_rounds = max_window_rounds

    # ── public API ─────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """多管线子 Agent，无统一系统提示。各管线自行提供。"""
        return ""

    # ── Command interface ─────────────────────────────────────────────

    def get_command_def(self) -> list[CommandDef] | None:
        """返回此子 Agent 注册的所有斜杠命令。"""
        defs: list[CommandDef] = [
            CommandDef(
                name=COMMAND_NAME_COMPACT,
                description="压缩最老的对话轮次为摘要",
                detail=f"可传参：{COMMAND_NAME_COMPACT} [压缩轮数] [保留轮数]，如 {COMMAND_NAME_COMPACT} 10 5",
            ),
        ]
        if self._story_store:
            defs.append(CommandDef(
                name=COMMAND_NAME_EXTRACT_STORY,
                description="手动提取剧情记忆",
                detail="扫描对话历史，提取 notable 角色/剧情细节并持久化到剧情记忆。",
            ))
        return defs if defs else None

    def accept_command(self, command: str) -> bool:
        return command in (COMMAND_NAME_COMPACT, COMMAND_NAME_EXTRACT_STORY)

    async def execute_command(self, command: str, args: list[str], agent: RPGGameAgent | None = None) -> dict | None:
        if command == COMMAND_NAME_EXTRACT_STORY:
            return await self._execute_story_memory(agent)
        if command == COMMAND_NAME_COMPACT:
            return await self._execute_compact(agent, args)
        return None

    async def _execute_story_memory(self, agent: RPGGameAgent | None) -> dict:
        """处理 /story_memory 命令：提取剧情记忆。"""
        if agent is None or not hasattr(agent, "_session"):
            return {"reply": "未绑定主 Agent，无法执行 story_memory"}

        conv = agent._session.history
        last_idx = agent._session.last_story_rp_his_id
        new_msgs = [m for m in conv if m.rp_his_id > last_idx]
        if not new_msgs:
            logger.info(_TAG + " story_memory skipped: no new messages since rp_his_id={}", last_idx)
            return {"reply": "剧情记忆提取跳过：没有新消息需要处理。", "stats": None}

        logger.info(
            _TAG + " story_memory processing {} new messages (rp_his_id > {})",
            len(new_msgs), last_idx,
        )
        result = await self.process({"story": new_msgs})
        added = result.story_details_added
        if added > 0:
            last_user = next(
                (m for m in reversed(new_msgs) if m.is_user()),
                None,
            )
            if last_user:
                agent._session.set_last_story_rp_his_id(last_user.rp_his_id)

        stats = _build_call_stats(result)
        if stats:
            logger.info(
                _TAG + " story_memory done: added={}, tokens={}, duration={:.0f}ms",
                added, stats["total_tokens"], stats["total_duration_ms"],
            )
        else:
            logger.info(_TAG + " story_memory done: added={}, no LLM call", added)

        return {"reply": f"已提取 {added} 条剧情记忆。", "stats": stats}

    async def _execute_compact(self, agent: RPGGameAgent | None, args: list[str]) -> dict:
        """处理 /compact 命令：压缩对话历史。"""
        if agent is None:
            return {"reply": f"未绑定主 Agent，无法执行 {COMMAND_NAME_COMPACT}"}

        compress_rounds, err = _parse_int_arg(args, 0)
        if err:
            return {"reply": f"compress_rounds 必须是整数，收到: {args[0]}"}
        keep_rounds, err = _parse_int_arg(args, 1)
        if err:
            return {"reply": f"keep_rounds 必须是整数，收到: {args[1]}"}

        result = await self.compact_history(agent, compress_rounds, keep_rounds)
        if result.get("skipped"):
            return {"reply": f"压缩跳过：{result['reason']}"}

        summary_text = result.get("summary_text", "")
        msg = f"已压缩 {result['compress_rounds']} 轮对话。"
        if summary_text:
            msg += f"\n\n摘要：{summary_text[:500]}"
        msg += f"\n\n历史消息：{result['previous_history_msgs']} → {result['history_after_msgs']}"
        return {"reply": msg, "stats": None}

    async def compact_history(
        self,
        agent: RPGGameAgent,
        compress_rounds: int | None = None,
        keep_rounds: int | None = None,
    ) -> dict[str, int | str | bool]:
        """压缩最老的对话轮次为摘要。

        从最早的 user 轮次开始，压缩 *compress_rounds* 轮，保留最近
        *keep_rounds* 轮不动。压缩完成后从会话历史中移除已压缩的消息。

        Returns:
            包含 ``summary_text``、``compress_rounds``、``kept_rounds``、
            ``previous_history_msgs``、``history_after_msgs`` 的 dict。
        """
        from rpg_world.rpg_core.settings import settings

        compress_rounds = compress_rounds or settings.memory_compress_rounds
        keep_rounds = keep_rounds or settings.memory_keep_rounds

        user_indices = [i for i, m in enumerate(agent._session.history) if m.is_user()]
        total = len(user_indices)
        available = total - keep_rounds
        if available <= 0:
            logger.info(
                _TAG + " compact skipped: history too short ({} user rounds <= {} keep)",
                total, keep_rounds,
            )
            return {"skipped": True, "reason": f"history too short ({total} <= {keep_rounds})"}

        actual = min(compress_rounds, available)
        compress_end = user_indices[actual] if actual < len(user_indices) else len(agent._session.history)

        logger.info(
            _TAG + " compact: total={} user rounds, compress={}, keep={}",
            total, actual, keep_rounds,
        )

        compress_window = agent._session.history[:compress_end]
        result = await self.process({"summary": compress_window})
        summary_text = ""
        if result.summary_generated and self._summary_store is not None:
            summaries = self._summary_store.get_all_summaries()
            summary_text = summaries[-1] if summaries else ""
            logger.info(
                _TAG + " summary generated: {} chars", len(summary_text),
            )

        # 截断
        before_len = len(agent._session.history)
        agent._session.truncate(compress_end)
        after_len = len(agent._session.history)
        agent._session.increment_compacted_rounds(actual)

        logger.info(
            _TAG + " compact: deleted {} msgs, history now {} msgs",
            before_len - after_len, after_len,
        )

        return {
            "summary_text": summary_text,
            "compress_rounds": actual,
            "kept_rounds": keep_rounds,
            "previous_history_msgs": before_len,
            "history_after_msgs": after_len,
        }

    async def process(self, context: dict) -> MemoryAgentResult:
        """处理 *context* 中的内容，更新对应记忆存储。

        *context* 支持的 key:

        ========= =========================  ============================
        key       值类型                     作用
        ========= =========================  ============================
        ``recall`` ``list[Message]`` (optional)  扫描对话提取召回项
        ``story`` ``list[Message]`` (optional)  提取剧情细节追加持久化
        ``summary`` ``list[Message]`` (optional) 生成摘要追加到 SummaryStore
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
            call_stats: list[CallRecord] = []

            if "recall" in context and self._recalled_store:
                result.recalls_injected = await self._pipeline_recall(
                    context["recall"], call_stats
                )

            if "story" in context and self._story_store:
                result.story_details_added = await self._pipeline_story_memory(
                    context["story"], call_stats
                )

            if "summary" in context and self._summary_store:
                result.summary_generated = await self._pipeline_summary(
                    context["summary"], call_stats
                )

            result.call_stats = call_stats
            return result

        finally:
            self._busy = False

    # ── 自动触发剧情记忆提取 ──────────────────────────────────────────

    async def maybe_auto_extract(self, session: SessionManager) -> None:
        """检查自动触发条件，满足时同步提取剧情记忆。

        由主 Agent 在每轮对话结束后编排调用（await 等待完成）。
        """
        if not self._enabled or not self._story_store:
            return
        from rpg_world.rpg_core.settings import settings as _s
        trigger = _s.memory_story_trigger_rounds
        if trigger <= 0:
            return

        new_rounds = session.count_new_user_rounds_since_story()
        if new_rounds < trigger:
            return
        logger.info(
            _TAG + " auto story extraction: {} new rounds >= trigger {}",
            new_rounds, trigger,
        )
        last_idx = session.last_story_rp_his_id
        new_msgs = [m for m in session.history if m.rp_his_id > last_idx]
        if not new_msgs:
            return

        await self.process({"story": new_msgs})

    def update_store_refs(
        self,
        recalled_store: RecalledMemoryStore | None = None,
        story_store: StoryMemoryStore | None = None,
        summary_store: SummaryStore | None = None,
    ) -> None:
        """更新 store 引用（RPG context reload 后调用）。"""
        if recalled_store is not None:
            self._recalled_store = recalled_store
        if story_store is not None:
            self._story_store = story_store
        if summary_store is not None:
            self._summary_store = summary_store

    # ── Pipeline 1: 召回 ─────────────────────────────────────────────

    async def _pipeline_recall(self, conv: list[Message], call_stats: list[CallRecord]) -> int:
        """提取召回项，全量替换 RecalledMemoryStore。"""
        window = self._format_conversation_window(conv, self._max_window_rounds)

        system_content = self._build_system_context(
            RECALL_PROMPT.replace("{max_items}", str(self._max_recall_items))
        )

        messages = [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(role=Role.USER, content=(
                f"## Conversation\n\n{window}\n\n"
                f"Call `extract_recalls` with relevant context items."
            )).to_dict(),
        ]

        decision, call_rec = await self._call_llm(messages, RECALL_SCHEMA)
        if call_rec:
            call_stats.append(call_rec)
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

    async def _pipeline_story_memory(self, conv: list[Message], call_stats: list[CallRecord]) -> int:
        """提取剧情细节，追加到 StoryMemoryStore。"""
        logger.info(_TAG + " story pipeline starting: {} messages in window", len(conv))
        window = self._format_conversation_window(conv)

        # 已有剧情记忆（去重参考）——不限制条数，保留全量参考
        existing_items = self._story_store.get_all() if self._story_store else []
        existing = _format_store_items(
            existing_items,
            key=lambda d: d.get("text", str(d)) if isinstance(d, dict) else str(d),
        )
        if existing_items:
            logger.info(_TAG + " story pipeline: {} existing items for dedup", len(existing_items))

        system_content = self._build_system_context(STORY_MEMORY_PROMPT)

        messages = [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(role=Role.USER, content=(
                f"## Conversation Content\n\n{window}\n\n"
                f"## Existing Story Memory (for deduplication)\n"
                f"{existing}\n\n"
                f"Call `extract_story_details` with notable details."
            )).to_dict(),
        ]

        decision, call_rec = await self._call_llm(messages, STORY_DETAIL_SCHEMA)
        if call_rec:
            call_stats.append(call_rec)
            logger.info(
                _TAG + " story pipeline LLM: {} tokens (prompt={}, completion={}), {:.0f}ms",
                call_rec.usage.total_tokens if call_rec.usage else 0,
                call_rec.usage.prompt_tokens if call_rec.usage else 0,
                call_rec.usage.completion_tokens if call_rec.usage else 0,
                call_rec.duration_ms,
            )
        details = decision.get("story_details", [])

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

    async def _pipeline_summary(self, conv: list[Message], call_stats: list[CallRecord]) -> bool:
        """生成摘要文本，追加到 SummaryStore。"""
        window = self._format_conversation_window(conv)

        system_content = self._build_system_context(SUMMARY_PROMPT)

        messages = [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(role=Role.USER, content=(
                f"## Conversation\n\n{window}\n\n"
                f"Call `generate_summary` with the summary text."
            )).to_dict(),
        ]

        decision, call_rec = await self._call_llm(messages, SUMMARY_SCHEMA)
        if call_rec:
            call_stats.append(call_rec)
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
        schema: dict[str, object],
    ) -> tuple[dict[str, object], CallRecord | None]:
        """Call provider with *messages* and *schema*, return parsed arguments.

        Returns
        -------
        ``(parsed_args, call_record)`` — *parsed_args* 是函数参数字典，
        *call_record* 包含 usage/timing 信息（API 返回时）。
        """
        import time

        t0 = time.monotonic()
        provider = self._get_provider()

        try:
            result = await provider.chat(messages, tools=[schema])
        except Exception as exc:
            logger.warning(_TAG + " LLM call failed: {}", exc)
            return {}, None

        duration_ms = (time.monotonic() - t0) * 1000

        # 捕获 CallRecord
        call_record: CallRecord | None = None
        if isinstance(result, LLMResponse):
            call_record = CallRecord(
                source="memory_sub_agent",
                model=result.model or provider.get_default_model(),
                usage=result.usage,
                duration_ms=duration_ms,
                reasoning_content=result.reasoning_content,
            )

        tool_calls = result.get("tool_calls") if isinstance(result, dict) else result.tool_calls
        if not tool_calls:
            logger.warning(_TAG + " LLM returned no tool calls")
            return {}, call_record

        try:
            parsed = json.loads(tool_calls[0]["function"]["arguments"])
            return parsed, call_record
        except (KeyError, json.JSONDecodeError, IndexError) as exc:
            logger.warning(
                _TAG + " failed to parse function args: {}", exc
            )
            return {}, call_record

    def _format_conversation_window(
        self,
        history: list[Message],
        max_rounds: int | None = None,
    ) -> str:
        """Format conversation as readable ``Role: text`` lines, windowed."""
        if max_rounds is not None:
            user_indices = [
                i for i, m in enumerate(history) if m.is_user()
            ]
            if len(user_indices) > max_rounds:
                history = history[user_indices[-max_rounds]:]

        lines: list[str] = []
        for msg in history:
            role = msg.role
            content = (msg.content or "").strip()
            if not content or role == Role.SYSTEM:
                continue
            label = {Role.USER.value: "User", Role.ASSISTANT.value: "Assistant"}.get(
                role, role.capitalize()
            )
            lines.append(f"{label}: {content[:500]}")

        return "\n\n".join(lines) if lines else "(no conversation content)"


# ── helpers ───────────────────────────────────────────────────────────


def _build_call_stats(result: MemoryAgentResult) -> dict[str, float | str | int] | None:
    """从 ``MemoryAgentResult`` 提取 LLM 调用统计 dict。"""
    if not result.call_stats:
        return None
    cr = result.call_stats[0]
    return {
        "total_duration_ms": cr.duration_ms,
        "model": cr.model,
        "prompt_tokens": cr.usage.prompt_tokens if cr.usage else 0,
        "completion_tokens": cr.usage.completion_tokens if cr.usage else 0,
        "total_tokens": cr.usage.total_tokens if cr.usage else 0,
        "cached_tokens": cr.usage.cached_tokens if cr.usage else 0,
    }


def _parse_int_arg(args: list[str], index: int) -> tuple[int | None, str | None]:
    """从命令参数列表中安全解析 ``int`` 值。

    Returns:
        ``(value, error)`` — 成功时 error 为 ``None``，失败时 value 为 ``None``。
    """
    if index >= len(args):
        return None, None  # 参数不存在不算错误
    try:
        return int(args[index]), None
    except ValueError:
        return None, args[index]


def _format_store_items(
    items: list[dict],
    *,
    key: type = str,
    max_items: int | None = None,
) -> str:
    """Format store items as a bullet list string."""
    if max_items is not None:
        items = items[-max_items:]
    if not items:
        return "(empty)"
    return "\n".join(f"- {key(item)}" for item in items)
