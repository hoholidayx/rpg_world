"""SummaryCompressor — 对话压缩控制器。

职责：
1. 当历史对话超出保留窗口时触发压缩
2. 选择需要压缩的历史段（保留窗口之前的旧内容）
3. 委托 MemorySubAgent 按批次生成摘要并写入 BatchSummaryStore
4. overall 与批次文件都成功后，在主消息表上原子标记摘要进度

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

触发规则（基于 rpg_session_messages 的 summary_processed 标记）:

    基于完整非 system 历史计算最近 keep_recent_rounds 窗口
    窗口外仍有未处理消息的 turn 数 > compression_threshold → 触发
    压缩后     = 批次摘要与 overall 写入成功，消息行统一标记为已处理
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from rpg_core.session.grouping import (
    MemoryTurnInputTooLargeError,
    batch_memory_turn_groups,
    select_summary_turn_groups,
)

if TYPE_CHECKING:
    from rpg_core.context.models import Message
    from rpg_core.summary.batch_store import BatchSummaryStore
    from rpg_core.session.manager import SessionManager


class SummaryProcessor(Protocol):
    """Agent-independent contract required by ``SummaryCompressor``."""

    @property
    def enabled(self) -> bool: ...

    async def generate_batch_summary(
        self,
        conv: list[Message],
        batch_id: int = 0,
        user_rounds: int = 0,
        call_stats: list[object] | None = None,
    ) -> dict | None: ...

    async def generate_overall_summary(
        self,
        new_batch_summaries: list[str],
        existing_body: str = "",
        call_stats: list[object] | None = None,
    ) -> dict | None: ...


class CompressionStatus(str, Enum):
    """Terminal state of a summary compression attempt."""

    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class CompressResult:
    """压缩操作结果。"""

    status: CompressionStatus = CompressionStatus.SKIPPED

    triggered: bool = False
    """本轮是否触发了压缩。"""

    user_rounds_compressed: int = 0
    """被压缩并标记为已处理的用户轮次数。"""

    batch_files: list[str] | None = None
    """生成的批次摘要文件名列表。"""

    overall_file: str | None = None
    """生成/更新的整体归纳文件名。"""

    summary_generated: bool = False
    """是否成功生成了摘要并写入 BatchSummaryStore。"""

    error_code: str | None = None
    error_message: str | None = None

    @property
    def failed(self) -> bool:
        return self.status is CompressionStatus.FAILED


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
        memory_sub_agent: SummaryProcessor | None = None,
        enabled: bool = True,
        keep_recent_rounds: int = 20,
        compression_threshold: int = 10,
        compress_batch_size: int = 10,
        max_batch_chars: int = 32_000,
    ) -> None:
        self._batch_store = batch_store
        self._memory_sub_agent = memory_sub_agent
        self._enabled = enabled
        self._keep_recent_rounds = keep_recent_rounds
        self._compression_threshold = compression_threshold
        self._compress_batch_size = compress_batch_size
        if (
            isinstance(max_batch_chars, bool)
            or not isinstance(max_batch_chars, int)
            or max_batch_chars <= 0
        ):
            raise ValueError("max_batch_chars must be a positive integer")
        self._max_batch_chars = max_batch_chars

    # ── public API ─────────────────────────────────────────────────────

    def replace_session_resources(
        self,
        *,
        batch_store: "BatchSummaryStore | None",
        memory_sub_agent: SummaryProcessor | None,
    ) -> None:
        """Rebind session-scoped stores without changing compression policy."""
        self._batch_store = batch_store
        self._memory_sub_agent = memory_sub_agent

    async def maybe_compress(
        self,
        session: "SessionManager",
        *,
        strict: bool = False,
    ) -> CompressResult:
        """检查是否需要压缩，是则执行分批压缩。

        当压缩触发时，session 的历史不会被截断；本轮 batch summary 与
        overall 都成功后，对应消息才会被标记为 ``summary_processed``。

        多次调用是安全的 —— 如果历史不够长，直接返回 ``triggered=False``。
        """
        processor_available = (
            self._memory_sub_agent is not None and self._memory_sub_agent.enabled
        )
        # A globally disabled MemorySubAgent owns no normal processing side
        # effects. Strict provisioning still needs to distinguish a genuine
        # no-op from required work that cannot run.
        if not processor_available:
            if strict and self._enabled:
                pending_groups = select_summary_turn_groups(
                    session,
                    keep_recent_turns=self._keep_recent_rounds,
                    mark_excluded=False,
                )
                if len(pending_groups) > self._compression_threshold:
                    return CompressResult(
                        status=CompressionStatus.FAILED,
                        triggered=True,
                        error_code="SUMMARY_PROCESSOR_UNAVAILABLE",
                        error_message="summary processor is unavailable or disabled",
                    )
            return CompressResult()

        compress_groups = select_summary_turn_groups(
            session,
            keep_recent_turns=self._keep_recent_rounds,
        )

        # Auto compression can be disabled independently; OOC exclusion above
        # is still a lightweight continuation step.
        if not self._enabled:
            return CompressResult()

        user_rounds_in_compress = len(compress_groups)
        if user_rounds_in_compress <= self._compression_threshold:
            return CompressResult()
        if self._batch_store is None:
            if strict:
                return CompressResult(
                    status=CompressionStatus.FAILED,
                    triggered=True,
                    error_code="SUMMARY_STORE_UNAVAILABLE",
                    error_message="summary batch store is unavailable",
                )
            return CompressResult()

        try:
            batches = batch_memory_turn_groups(
                compress_groups,
                batch_turns=self._compress_batch_size,
                max_batch_chars=self._max_batch_chars,
            )
        except MemoryTurnInputTooLargeError as exc:
            return CompressResult(
                status=CompressionStatus.FAILED,
                triggered=True,
                error_code="SUMMARY_INPUT_TOO_LARGE",
                error_message=str(exc),
            )

        batch_files: list[str] = []
        batch_paths = []
        pending_progress: list[tuple[list[Message], int]] = []
        processed_turns = 0
        processed_batch_ids: list[int] = []
        overall_snapshot = self._batch_store.snapshot_overall()
        next_batch_id = self._batch_store.next_batch_id()
        batch_error: Exception | None = None
        for offset, batch in enumerate(batches):
            batch_id = next_batch_id + offset
            batch_messages = list(batch.messages)
            batch_user_rounds = batch.turn_count
            try:
                result = await self._memory_sub_agent.generate_batch_summary(
                    conv=batch_messages, batch_id=batch_id, user_rounds=batch_user_rounds
                )
                if not result or not str(result.get("summary_text", "")).strip():
                    raise RuntimeError("batch summary returned no content")
                turn_ids = [
                    int(message.turn_id)
                    for message in batch_messages
                    if int(message.turn_id) > 0
                ]
                path = self._batch_store.save_batch_summary(
                    batch_id=batch_id,
                    title=result.get("title", ""),
                    user_rounds=batch_user_rounds,
                    summary_text=result.get("summary_text", ""),
                    time=result.get("time", ""),
                    location=result.get("location", ""),
                    characters=result.get("characters", []),
                    source_turn_start=min(turn_ids) if turn_ids else None,
                    source_turn_end=max(turn_ids) if turn_ids else None,
                    source_message_ids=[
                        message.uid for message in batch_messages if message.uid > 0
                    ],
                )
                batch_files.append(path.name)
                batch_paths.append(path)
                pending_progress.append((batch_messages, batch_id))
                processed_turns += batch_user_rounds
                processed_batch_ids.append(batch_id)
                logger.info(
                    "[Compressor] batch #{}: {} turns -> {}",
                    batch_id, batch_user_rounds, path.name,
                )
            except Exception as exc:
                batch_error = exc
                logger.warning(
                    "[Compressor] batch #{} failed: {}", batch_id, exc
                )
                # Normal post-commit processing commits the successful prefix
                # through overall below. Strict provisioning rolls the whole
                # attempt back and reports the failure to its caller.
                if strict:
                    self._batch_store.delete_batch_files(batch_paths)
                    self._batch_store.restore_overall(overall_snapshot)
                    return CompressResult(
                        status=CompressionStatus.FAILED,
                        triggered=True,
                        error_code="SUMMARY_BATCH_FAILED",
                        error_message=str(exc) or type(exc).__name__,
                    )
                break

        # 5. 整体归纳（增量更新 overall.md）
        overall_file: str | None = None
        if not batch_files:
            logger.warning(
                "[Compressor] all batches failed; summary processed flags unchanged"
            )
            return CompressResult(
                status=CompressionStatus.FAILED,
                triggered=True,
                error_code="SUMMARY_BATCH_FAILED",
                error_message=(
                    str(batch_error) if batch_error is not None
                    else "no batch summary was written"
                ),
            )
        else:
            try:
                existing_overall, last_batch_id = self._batch_store.load_overall()
                new_batches = self._batch_store.get_new_content(last_batch_id)
                if not new_batches:
                    raise RuntimeError("new summary batches were not visible to overall aggregation")
                overall_result: dict | None = None
                rolling_overall = existing_overall
                for new_batch in new_batches:
                    overall_result = await self._memory_sub_agent.generate_overall_summary(
                        [new_batch], rolling_overall
                    )
                    if not overall_result or not str(
                        overall_result.get("summary_text", "")
                    ).strip():
                        raise RuntimeError("overall summary returned no content")
                    rolling_overall = str(overall_result["summary_text"]).strip()
                if overall_result is None:
                    raise RuntimeError("overall summary returned no content")
                max_batch_id = max(processed_batch_ids)
                overall_path = self._batch_store.save_overall(
                    content=overall_result.get("summary_text", ""),
                    title=overall_result.get("title", ""),
                    key_events=overall_result.get("key_events", []),
                    last_batch_id=max_batch_id,
                )
                session.mark_summary_batches_processed(pending_progress)
                overall_file = overall_path.name
                logger.info(
                    "[Compressor] overall.md updated and progress committed (last_batch_id={})",
                    max_batch_id,
                )
            except Exception as exc:
                logger.warning("[Compressor] overall summary failed: {}", exc)
                self._batch_store.delete_batch_files(batch_paths)
                self._batch_store.restore_overall(overall_snapshot)
                batch_files = []
                processed_turns = 0
                processed_batch_ids = []
                return CompressResult(
                    status=CompressionStatus.FAILED,
                    triggered=True,
                    error_code="SUMMARY_OVERALL_FAILED",
                    error_message=str(exc) or type(exc).__name__,
                )

        logger.info(
            "[Compressor] compressed {} turns, {} batch files",
            processed_turns,
            len(batch_files),
        )

        return CompressResult(
            status=CompressionStatus.SUCCEEDED,
            triggered=True,
            user_rounds_compressed=processed_turns,
            batch_files=batch_files or None,
            overall_file=overall_file,
            summary_generated=len(batch_files) > 0,
        )
