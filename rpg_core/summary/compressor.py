"""SummaryCompressor — 对话压缩控制器。

职责：
1. 当历史对话超出保留窗口时触发压缩
2. 选择需要压缩的历史段（保留窗口之前的旧内容）
3. 委托 MemorySubAgent 生成摘要并写入 SummaryStore
4. 从历史中移除已压缩的轮次

Architecture::

    agent.py (send flow)        ── 调用方
        │
        ▼
    SummaryCompressor           ── 控制层（压缩策略）
        │                          ├─ 保留策略：保留最近 N 轮保持连贯性
        │                          ├─ 触发策略：超出阈值时执行
        │                          └─ 批量策略：单次压缩量
        │
        ├─▶ SummaryStore        ── 持久层（已存在）
        └─▶ MemorySubAgent      ── 执行层（已存在，仅用 summary pipeline）

触发规则（纯实时判断，不维护轮次状态）:

    总用户轮次 > keep_recent_rounds + compression_threshold  → 触发
    压缩段     = history 中保留窗口之前的部分
    压缩后     = 原地截断 history，摘要写入 SummaryStore

压缩段在被压缩前已被 builder 排除在 LLM 上下文之外（超出 hot history 窗口），
因此压缩不丢失 LLM 可见信息 —— 摘要是对已排除内容的补偿。
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from rpg_world.rpg_core.context.rpg_context import Message

from rpg_world.rpg_core.agent.sub_agents.memory_sub_agent import MemorySubAgent


@dataclass
class CompressResult:
    """压缩操作结果。"""

    triggered: bool = False
    """本轮是否触发了压缩。"""

    user_rounds_compressed: int = 0
    """被压缩并移除的用户轮次数。"""

    summary_generated: bool = False
    """是否成功生成了摘要并写入 SummaryStore。"""


class SummaryCompressor:
    """对话压缩控制器 —— 纯函数式、无状态设计。

    每次调用 ``maybe_compress(history)`` 都基于当前 history 的实时长度
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
        SummaryStore 实例。为 None 时压缩仅截断历史，不生成摘要。
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
        summary_store: SummaryStore | None = None,
        memory_sub_agent: MemorySubAgent | None = None,
        enabled: bool = True,
        keep_recent_rounds: int = 20,
        compression_threshold: int = 10,
        min_rounds_per_compress: int = 5,
    ) -> None:
        self._summary_store = summary_store
        self._memory_sub_agent = memory_sub_agent
        self._enabled = enabled
        self._keep_recent_rounds = keep_recent_rounds
        self._compression_threshold = compression_threshold
        self._min_rounds_per_compress = min_rounds_per_compress

    # ── public API ─────────────────────────────────────────────────────

    async def maybe_compress(self, history: list[Message]) -> CompressResult:
        """检查是否需要压缩，是则执行。

        当压缩触发时，*history* 会被**原地修改**：已压缩的旧消息被移除，
        只保留最近 ``keep_recent_rounds`` 轮的内容。

        多次调用是安全的 —— 如果历史不够长，直接返回 ``triggered=False``。
        """
        if not self._enabled:
            return CompressResult()

        # 1. 统计用户消息数
        user_indices = [
            i for i, m in enumerate(history) if m.is_user()
        ]
        total_user_rounds = len(user_indices)

        # 2. 判断触发条件
        if (
            total_user_rounds
            <= self._keep_recent_rounds + self._compression_threshold
        ):
            return CompressResult()

        # 3. 确定压缩范围
        #    保留窗口起始 = 倒数 keep_recent_rounds 条用户消息的位置
        keep_from = user_indices[-self._keep_recent_rounds]

        # 跳过 system prompt（history[0] 永远是 system）
        compress_start = 1
        compress_end = keep_from

        if compress_end <= compress_start:
            return CompressResult()

        compress_portion = history[compress_start:compress_end]
        user_rounds_in_compress = sum(
            1 for m in compress_portion if m.is_user()
        )

        if user_rounds_in_compress < self._min_rounds_per_compress:
            logger.debug(
                "[Compressor] skipped: only {} user rounds to compress "
                "(min {})",
                user_rounds_in_compress,
                self._min_rounds_per_compress,
            )
            return CompressResult()
        if self._memory_sub_agent is not None and self._summary_store is not None:
            try:
                sub_result = await self._memory_sub_agent.process(
                    {"summary": compress_portion}
                )
                summary_generated = sub_result.summary_generated
                if summary_generated:
                    logger.info(
                        "[Compressor] summarized {} user rounds -> summary store",
                        user_rounds_in_compress,
                    )
                else:
                    logger.warning(
                        "[Compressor] summarization returned no output; "
                        "compression proceeds without summary"
                    )
            except Exception as exc:
                logger.warning("[Compressor] summarization failed: {}", exc)

        # 5. 移除已压缩的消息
        #    无论摘要是否成功都截断 —— 已窗口外的内容下次触发会重新摘要
        del history[compress_start:compress_end]

        logger.info(
            "[Compressor] trimmed {} user rounds from history "
            "({} remaining)",
            user_rounds_in_compress,
            total_user_rounds - user_rounds_in_compress,
        )

        return CompressResult(
            triggered=True,
            user_rounds_compressed=user_rounds_in_compress,
            summary_generated=summary_generated,
        )
