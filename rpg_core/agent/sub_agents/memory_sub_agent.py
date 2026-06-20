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

from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent, SubAgentProviderConfig
from rpg_world.rpg_core.agent.agent_types import CallRecord, LLMResponse
from rpg_world.rpg_core.agent.command import CommandDef
from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.turns import iter_turn_groups, slice_recent_turns

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

BATCH_SUMMARY_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "generate_batch_summary",
        "description": "为一组对话轮次生成结构化摘要",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "一句话概括核心事件，10-20字",
                },
                "summary_text": {
                    "type": "string",
                    "description": "详细摘要，捕捉关键剧情、角色行为、决策后果",
                },
                "time": {
                    "type": "string",
                    "description": "剧情内时间点，如'第一天上午'",
                },
                "location": {
                    "type": "string",
                    "description": "主要场景地点",
                },
                "characters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参与的主要角色名列表",
                },
            },
            "required": ["title", "summary_text"],
        },
    },
}

OVERALL_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "generate_overall_summary",
        "description": "生成或更新整体剧情摘要",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "一句话概括整体剧情主线",
                },
                "summary_text": {
                    "type": "string",
                    "description": "完整整体摘要，包含所有已压缩内容的核心脉络",
                },
                "key_events": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键事件时间线列表",
                },
            },
            "required": ["summary_text"],
        },
    },
}


# ── system prompts (one per pipeline) ─────────────────────────────────

RECALL_PROMPT = """\
你是一个 RPG 游戏中的上下文相关性分析器。你的任务是扫描下方的对话，\
找出与用户最新输入直接相关的上下文项。这些项会作为"召回记忆"注入，\
帮助游戏主持人保持一致。

重点关注：
- 未解决的剧情线索或悬而未决的故事钩子
- 最近的角色状态变化（受伤、情绪波动、获得新物品）
- 用户当前互动的即时环境上下文
- 最近的 NPC 言论或承诺

调用 `extract_recalls`，最多包含 {max_items} 项。\
保守——只包含真正相关的。\
"""

STORY_MEMORY_PROMPT = """\
你是一个 RPG 的叙事细节提取器。扫描对话轮次，\
提取值得长期保存的剧情记忆中的角色或剧情细节。

重点关注：
- 首次登场且有显著特征的角色
- 重要的发现或揭示
- 角色关系的发展变化
- 玩家做出的重要选择
- 通过叙事揭示的世界观细节

调用 `extract_story_details`，最多包含 {max_items} 项。\
偏好具体、事实性的陈述。避免模糊的观察。\
"""

SUMMARY_PROMPT = """\
你是一个 RPG 的对话摘要器。为下方的对话生成简洁摘要，\
捕捉关键剧情事件和发展。

重点关注：
- 主要剧情事件和情节发展
- 角色弧线和变化
- 具有持久后果的关键决策
- 当前队伍状态和目标

调用 `generate_summary` 并传入摘要文本。\
"""

BATCH_SUMMARY_PROMPT = """\
你是一个 RPG 的对话批量摘要器。为下方的对话轮次生成结构化摘要。

这批对话包含约 {user_rounds} 轮用户消息。

要求：
1. title: 用一句话概括核心事件（10-20字）
2. summary_text: 详细摘要，捕捉关键剧情事件、角色行为、决策后果
3. time: 判断对话发生的时间点（剧情内时间）
4. location: 主要场景地点
5. characters: 参与的主要角色名

调用 `generate_batch_summary` 并填入所有字段。
"""

OVERALL_PROMPT = """\
你是一个 RPG 的剧情整体摘要器。你的任务是将本次新压缩的批次摘要合并到已有的整体摘要中。

## 已有整体摘要
{existing_overall}

## 本次新压缩的批次摘要
{new_batch_summaries}

要求：
1. 将新批次内容有机融入已有摘要，不要简单拼接
2. 保持时间线和剧情发展的一致性
3. 如果新内容修正了旧摘要中的错误，以新内容为准
4. 输出完整的最新整体摘要（包含新旧全部内容的核心脉络）

调用 `generate_overall_summary` 并填入摘要文本和关键事件。
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
        provider_config: SubAgentProviderConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
        max_recall_items: int = 5,
        max_window_rounds: int = 10,
        batch_store: "BatchSummaryStore | None" = None,
    ) -> None:
        super().__init__(
            provider=provider,
            provider_config=provider_config,
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
        self._batch_store = batch_store
        self._max_recall_items = max_recall_items
        self._max_window_rounds = max_window_rounds

    def _get_provider(self) -> LLMProvider:
        provider = super()._get_provider()
        self._provider = provider
        return provider

    # ── public API ─────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """多管线子 Agent，无统一系统提示。各管线自行提供。"""
        return ""

    # ── Command interface ─────────────────────────────────────────────

    def get_command_def(self) -> list[CommandDef] | None:
        """返回此子 Agent 注册的所有斜杠命令。"""
        if not self.enabled:
            return None
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
        if not self.enabled:
            return False
        return command in (COMMAND_NAME_COMPACT, COMMAND_NAME_EXTRACT_STORY)

    async def execute_command(self, command: str, args: list[str], agent: RPGGameAgent | None = None) -> dict | None:
        if not self.enabled:
            return None
        if command == COMMAND_NAME_EXTRACT_STORY:
            return await self._execute_story_memory(agent)
        if command == COMMAND_NAME_COMPACT:
            return await self._execute_compact(agent, args)
        return None

    async def _execute_story_memory(self, agent: RPGGameAgent | None) -> dict:
        """处理 /story_memory 命令：提取剧情记忆。"""
        if agent is None or not hasattr(agent, "_session"):
            return {"reply": "未绑定主 Agent，无法执行 story_memory"}

        new_msgs = agent._session.story_messages_since_last_extraction()
        if not new_msgs:
            logger.info(_TAG + " story_memory skipped: no new messages since last extraction")
            return {"reply": "剧情记忆提取跳过：没有新消息需要处理。", "stats": None}

        logger.info(
            _TAG + " story_memory processing {} new messages (turn-aware)",
            len(new_msgs),
        )
        result = await self.process({"story": new_msgs})
        added = result.story_details_added
        agent._session.mark_story_messages_processed(new_msgs)

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

        batch_files = result.get("batch_files", [])
        overall_file = result.get("overall_file", "")

        # 读取 overall.md 内容作为摘要
        overall_content = ""
        if self._batch_store and overall_file:
            try:
                body, _ = self._batch_store.load_overall()
                overall_content = body
            except Exception:
                pass

        msg = (
            f"已压缩 {result['compress_rounds']} 轮对话，"
            f"生成 {len(batch_files)} 个批次文件。"
        )
        if batch_files:
            msg += f"\n\n批次文件：{' '.join(batch_files)}"
        msg += f"\n\n历史消息：{result['previous_history_msgs']} → {result['history_after_msgs']}"
        if overall_content:
            msg += f"\n\n## 整体剧情摘要\n\n{overall_content[:1000]}"
        return {"reply": msg, "stats": None}

    async def compact_history(
        self,
        agent: RPGGameAgent,
        compress_batch_size: int | None = None,
        keep_rounds: int | None = None,
    ) -> dict[str, int | str | bool]:
        """压缩最老的对话轮次为批次摘要 + 整体归纳。

        保留最近 *keep_rounds* 轮用户消息不动，将其余历史按 *compress_rounds*
        为批次大小拆分，逐批调用 LLM 生成批次 md 文件（记忆唯一真源）。
        所有批次完成后，调用 LLM 生成/更新 overall.md（注入 context 的聚合概览）。
        最后一次性截断历史。

        Returns:
            包含 ``compress_rounds``、``kept_rounds``、``batch_files``、
            ``batches``、``overall_file``、``previous_history_msgs``、
            ``history_after_msgs`` 的 dict。
        """
        from rpg_world.rpg_core.settings import settings

        compress_batch_size = compress_batch_size or settings.memory_compress_batch_size
        keep_rounds = keep_rounds or settings.memory_keep_rounds

        if self._batch_store is None:
            return {"skipped": True, "reason": "no batch_store configured"}

        history = agent._session.history
        prefix_end = 0
        while prefix_end < len(history) and history[prefix_end].is_system():
            prefix_end += 1
        prefix = history[:prefix_end]
        working_history = history[prefix_end:]
        groups = iter_turn_groups(working_history)
        total = len(groups)
        available = total - keep_rounds
        if available <= 0:
            logger.info(
                _TAG + " compact skipped: history too short ({} turns <= {} keep)",
                total, keep_rounds,
            )
            return {"skipped": True, "reason": f"history too short ({total} <= {keep_rounds})"}

        keep_groups = groups[-keep_rounds:] if keep_rounds > 0 else []
        old_groups = groups[:-keep_rounds] if keep_rounds > 0 else groups
        old_slice = [msg for group in old_groups for msg in group]

        # 拆分为批次
        batches = _split_into_batches(old_slice, compress_batch_size)
        if not batches:
            return {"skipped": True, "reason": "no batches to compress"}

        logger.info(
            _TAG + " compact: total={} turns, keep={}, batches={}",
            total, keep_rounds, len(batches),
        )

        # 逐批生成批次摘要
        batch_files: list[str] = []
        total_compressed = 0
        call_stats: list[CallRecord] = []
        for batch_id, batch_slice, user_rounds_in_batch in batches:
            try:
                result = await self._pipeline_batch_summary(
                    conv=batch_slice,
                    batch_id=batch_id,
                    user_rounds=user_rounds_in_batch,
                    call_stats=call_stats,
                )
                if result:
                    file_path = self._batch_store.save_batch_summary(
                        batch_id=batch_id,
                        title=result["title"],
                        user_rounds=result["user_rounds"],
                        summary_text=result.get("summary_text", ""),
                        time=result.get("time", ""),
                        location=result.get("location", ""),
                        characters=result.get("characters", []),
                    )
                    batch_files.append(file_path.name)
                    total_compressed += user_rounds_in_batch
            except Exception as exc:
                logger.warning(_TAG + " batch #{} failed: {}", batch_id, exc)

        # 整体归纳（仅传入新增批次）
        overall_file = ""
        try:
            existing_overall, last_batch_id = self._batch_store.load_overall()
            new_batches = self._batch_store.get_new_content(last_batch_id)
            if new_batches:
                overall_result = await self._pipeline_overall_summary(
                    new_batches, existing_overall, call_stats=call_stats,
                )
                if overall_result:
                    max_batch_id = self._batch_store._next_batch_id() - 1
                    overall_path = self._batch_store.save_overall(
                        content=overall_result.get("summary_text", ""),
                        title=overall_result.get("title", ""),
                        key_events=overall_result.get("key_events", []),
                        last_batch_id=max_batch_id,
                    )
                    overall_file = overall_path.name
                    logger.info(_TAG + " overall updated: {} (last_batch_id={})", overall_file, max_batch_id)
            else:
                logger.info(_TAG + " overall skipped: no new batches since last_batch_id={}", last_batch_id)
        except Exception as exc:
            logger.warning(_TAG + " overall summary failed: {}", exc)

        # 一次性截断历史
        before_len = len(agent._session.history)
        agent._session.replace_history(
            prefix + [msg for group in keep_groups for msg in group],
            persist=agent._session.history_enabled,
        )
        after_len = len(agent._session.history)

        logger.info(
            _TAG + " compact: {} msgs deleted, history now {} msgs",
            before_len - after_len, after_len,
        )

        return {
            "summary_text": batch_files[0] if batch_files else "",
            "compress_rounds": total_compressed,
            "kept_rounds": keep_rounds,
            "previous_history_msgs": before_len,
            "history_after_msgs": after_len,
            "batch_files": batch_files,
            "batches": len(batch_files),
            "overall_file": overall_file,
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

        new_turns = session.count_new_turns_since_story()
        if new_turns < trigger:
            return
        logger.info(
            _TAG + " auto story extraction: {} new turns >= trigger {}",
            new_turns, trigger,
        )
        new_msgs = session.story_messages_since_last_extraction()
        if not new_msgs:
            return

        await self.process({"story": new_msgs})
        session.mark_story_messages_processed(new_msgs)

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

    # ── Pipeline 4: 批次摘要 ─────────────────────────────────────────

    async def _pipeline_batch_summary(
        self,
        conv: list[Message],
        batch_id: int = 0,
        user_rounds: int = 0,
        call_stats: list[CallRecord] | None = None,
    ) -> dict | None:
        """为单个批次生成结构化摘要。

        Returns:
            {batch_id, title, summary_text, time, location, characters, user_rounds}
            或 None（LLM 调用失败时）。
        """
        window = self._format_conversation_window(conv)
        system_content = self._build_system_context(
            BATCH_SUMMARY_PROMPT.format(user_rounds=user_rounds)
        )

        messages = [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(role=Role.USER, content=(
                f"## 对话内容\n\n{window}\n\n"
                f"Call `generate_batch_summary` with structured summary."
            )).to_dict(),
        ]

        decision, call_rec = await self._call_llm(messages, BATCH_SUMMARY_SCHEMA)
        if call_rec:
            if call_stats is not None:
                call_stats.append(call_rec)
            logger.info(
                _TAG + " batch #{} LLM: {} tokens, {:.0f}ms",
                batch_id,
                call_rec.usage.total_tokens if call_rec.usage else 0,
                call_rec.duration_ms,
            )

        title = decision.get("title", "")
        summary_text = decision.get("summary_text", "")
        if not summary_text:
            logger.warning(_TAG + " batch #{} LLM returned empty summary", batch_id)
            return None

        return {
            "batch_id": batch_id,
            "title": title,
            "summary_text": summary_text,
            "time": decision.get("time", ""),
            "location": decision.get("location", ""),
            "characters": decision.get("characters", []),
            "user_rounds": user_rounds,
        }

    # ── Pipeline 5: 整体归纳 ─────────────────────────────────────────

    async def _pipeline_overall_summary(
        self,
        new_batch_summaries: list[str],
        existing_body: str = "",
        call_stats: list[CallRecord] | None = None,
    ) -> dict | None:
        """生成或更新整体归纳。

        Parameters:
            new_batch_summaries: 本次新产生的批次摘要正文列表（增量部分）。
            existing_body: 已有 overall.md 正文，空字符串表示首次生成。
            call_stats: 可选 LLM 调用记录列表。
        Returns:
            {"summary_text": str, "title": str, "key_events": list[str]} 或 None。
        """
        existing_section = ""
        if existing_body.strip():
            existing_section = f"\n## 已有整体摘要\n\n{existing_body.strip()}\n"

        new_section = "\n".join(
            f"### 批次 {i+1}\n\n{text}"
            for i, text in enumerate(new_batch_summaries)
        )

        prompt = OVERALL_PROMPT.format(
            existing_overall=existing_section,
            new_batch_summaries=new_section,
        )

        system_content = self._build_system_context(prompt)

        messages = [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(role=Role.USER, content=(
                "请根据以上信息生成或更新整体剧情摘要。"
                "Call `generate_overall_summary` with the result."
            )).to_dict(),
        ]

        decision, call_rec = await self._call_llm(messages, OVERALL_SCHEMA)
        if call_rec:
            if call_stats is not None:
                call_stats.append(call_rec)
            logger.info(
                _TAG + " overall LLM: {} tokens, {:.0f}ms",
                call_rec.usage.total_tokens if call_rec.usage else 0,
                call_rec.duration_ms,
            )

        summary_text = decision.get("summary_text", "")
        if not summary_text:
            logger.warning(_TAG + " overall LLM returned empty summary")
            return None

        return {
            "summary_text": summary_text,
            "title": decision.get("title", ""),
            "key_events": decision.get("key_events", []),
        }

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
            history = slice_recent_turns(history, max_rounds)

        lines: list[str] = []
        for msg in history:
            role = msg.role
            content = (msg.content or "").strip()
            if not content or role in (Role.SYSTEM, Role.TOOL):
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


def _split_into_batches(
    messages: list[Message],
    batch_size: int,
) -> list[tuple[int, list[Message], int]]:
    """将消息列表按 turn 拆分。

    Returns:
        ``[(batch_id, batch_messages, 批内 turn 数), ...]``。
        batch_id 从 0 开始递增。最后一批可能小于 batch_size。
    """
    groups = iter_turn_groups(messages)
    if not groups:
        return []

    batches: list[tuple[int, list[Message], int]] = []
    start = 0
    batch_id = 0
    while start < len(groups):
        end = min(start + batch_size, len(groups))
        batch_groups = groups[start:end]
        batch_messages = [msg for group in batch_groups for msg in group]
        batches.append((batch_id, batch_messages, end - start))
        batch_id += 1
        start = end

    return batches
