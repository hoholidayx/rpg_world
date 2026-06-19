"""SummaryCompressor — 对话压缩控制器。

职责：
1. 当历史对话超出保留窗口时触发压缩
2. 选择需要压缩的历史段（保留窗口之前的旧内容）
3. 委托 MemorySubAgent 按批次生成摘要并写入 BatchSummaryStore
4. 从历史中移除已压缩的轮次

Architecture::

    agent.py (send flow)        ── 调用方
        │
        ▼
    SummaryCompressor           ── 控制层（压缩策略）
        │                          ├─ 保留策略：保留最近 N 轮保持连贯性
        │                          ├─ 触发策略：超出阈值时执行
        │                          └─ 批量策略：每批 compress_batch_size 轮
        │
        ├─▶ BatchSummaryStore   ── 持久层（批次 md 文件 + overall.md）
        └─▶ MemorySubAgent      ── 执行层（batch pipeline + overall pipeline）

触发规则（纯实时判断，不维护轮次状态）:

    总用户轮次 > keep_recent_rounds + compression_threshold  → 触发
    压缩段     = history 中保留窗口之前的部分
    压缩后     = 原地截断 history，批次摘要写入 BatchSummaryStore
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from rpg_world.rpg_core.context.rpg_context import Message
from rpg_world.rpg_core.session.turns import count_turns, iter_turn_groups, split_into_turn_batches

from rpg_world.rpg_core.agent.sub_agents.memory_sub_agent import MemorySubAgent

if TYPE_CHECKING:
    from rpg_world.rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_world.rpg_core.session.manager import SessionManager


@dataclass
class CompressResult:
    """压缩操作结果。"""

    triggered: bool = False
    """本轮是否触发了压缩。"""

    user_rounds_compressed: int = 0
    """被压缩并移除的用户轮次数。"""

    batch_files: list[str] | None = None
    """生成的批次摘要文件名列表。"""

    overall_file: str | None = None
    """生成/更新的整体归纳文件名。"""

    summary_generated: bool = False
    """是否成功生成了摘要并写入 BatchSummaryStore。"""


class SummaryCompressor:
    """对话压缩控制器 —— 纯函数式、无状态设计。

    每次调用 ``maybe_compress(session)`` 都基于当前 session 的实时历史
    做判断，不维护内部轮次计数器。可安全地重复调用。

    压缩策略由三个独立维度组成：

    ==================  =====================  =================================
    维度                 参数                   作用
    ==================  =====================  =================================
    保留策略            ``keep_recent_rounds``  保留最近 N 轮不动以维持连贯性
    触发策略            ``compression_threshold`` 超出保留窗口多少后触发
    批量策略            ``min_rounds_per_compress`` 单次至少压缩轮次，避免碎片化
    ==================  =====================  =================================

    Parameters
    ----------
    summary_store:
        BatchSummaryStore 实例。为 None 时压缩仅回写历史，不生成摘要。
    memory_sub_agent:
        MemorySubAgent 实例。为 None 时跳过摘要生成。
    enabled:
        总开关。
    keep_recent_rounds:
        保留策略 —— 保留最近 N 轮用户消息不压缩，用于维持对话连贯性。
    compression_threshold:
        触发策略 —— 允许保留窗口之上额外叠加的轮次，超出此值才触发。
    min_rounds_per_compress:
        批量策略 —— 单次压缩至少处理这么多用户轮次，低于此值跳过。
    """

    def __init__(
        self,
        batch_store: "BatchSummaryStore | None" = None,
        memory_sub_agent: MemorySubAgent | None = None,
        enabled: bool = True,
        keep_recent_rounds: int = 20,
        compression_threshold: int = 10,
        compress_batch_size: int = 10,
    ) -> None:
        self._batch_store = batch_store
        self._memory_sub_agent = memory_sub_agent
        self._enabled = enabled
        self._keep_recent_rounds = keep_recent_rounds
        self._compression_threshold = compression_threshold
        self._compress_batch_size = compress_batch_size

    # ── public API ─────────────────────────────────────────────────────

    async def maybe_compress(self, session: "SessionManager") -> CompressResult:
        """检查是否需要压缩，是则执行分批压缩。

        当压缩触发时，session 的历史会通过 ``replace_history()`` 回写，
        已压缩的旧消息被移除，只保留最近 ``keep_recent_rounds`` 轮的内容。

        多次调用是安全的 —— 如果历史不够长，直接返回 ``triggered=False``。
        """
        if not self._enabled:
            return CompressResult()

        if self._memory_sub_agent is None or self._batch_store is None:
            return CompressResult()

        history = session.history

        # Keep leading system messages untouched.
        prefix_end = 0
        while prefix_end < len(history) and history[prefix_end].is_system():
            prefix_end += 1
        prefix = history[:prefix_end]
        working_history = history[prefix_end:]

        # 1. 统计 turn 数
        total_turns = count_turns(working_history)

        # 2. 判断触发条件
        if (
            total_turns
            <= self._keep_recent_rounds + self._compression_threshold
        ):
            return CompressResult()

        # 3. 确定压缩范围
        groups = iter_turn_groups(working_history)
        if len(groups) <= self._keep_recent_rounds:
            return CompressResult()

        compress_groups = groups[:-self._keep_recent_rounds]
        keep_groups = groups[-self._keep_recent_rounds:]
        compress_portion = [msg for group in compress_groups for msg in group]
        user_rounds_in_compress = len(compress_groups)

        if user_rounds_in_compress == 0:
            return CompressResult()

        # 4. 分批处理
        batches = split_into_turn_batches(compress_portion, self._compress_batch_size)

        batch_files: list[str] = []
        for batch_id, batch_messages, batch_user_rounds in batches:
            try:
                result = await self._memory_sub_agent._pipeline_batch_summary(
                    conv=batch_messages, batch_id=batch_id, user_rounds=batch_user_rounds
                )
                if result:
                    path = self._batch_store.save_batch_summary(
                        batch_id=batch_id,
                        title=result.get("title", ""),
                        user_rounds=batch_user_rounds,
                        summary_text=result.get("summary_text", ""),
                        time=result.get("time", ""),
                        location=result.get("location", ""),
                        characters=result.get("characters", []),
                    )
                    batch_files.append(path.name)
                    logger.info(
                        "[Compressor] batch #{}: {} turns -> {}",
                        batch_id, batch_user_rounds, path.name,
                    )
            except Exception as exc:
                logger.warning(
                    "[Compressor] batch #{} failed: {}", batch_id, exc
                )

        # 5. 整体归纳（增量更新 overall.md）
        overall_file: str | None = None
        if not batch_files:
            logger.warning(
                "[Compressor] all batches failed; history will still be truncated"
            )
        else:
            try:
                existing_overall, last_batch_id = self._batch_store.load_overall()
                new_batches = self._batch_store.get_new_content(last_batch_id)
                if not new_batches:
                    logger.info(
                        "[Compressor] overall skipped: no new batches since last_batch_id={}",
                        last_batch_id,
                    )
                else:
                    overall_result = await self._memory_sub_agent._pipeline_overall_summary(
                        new_batches, existing_overall
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
                        logger.info(
                            "[Compressor] overall.md updated (last_batch_id={})",
                            max_batch_id,
                        )
            except Exception as exc:
                logger.warning("[Compressor] overall summary failed: {}", exc)

        # 6. 一次性截断历史
        session.replace_history(
            prefix + [msg for group in keep_groups for msg in group],
            persist=session.history_enabled,
        )

        logger.info(
            "[Compressor] compressed {} turns ({} remaining), {} batch files",
            user_rounds_in_compress,
            total_turns - user_rounds_in_compress,
            len(batch_files),
        )

        return CompressResult(
            triggered=True,
            user_rounds_compressed=user_rounds_in_compress,
            batch_files=batch_files or None,
            overall_file=overall_file,
            summary_generated=len(batch_files) > 0,
        )
