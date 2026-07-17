from __future__ import annotations

import pytest
from types import SimpleNamespace

from rpg_core.summary.compressor import CompressionStatus, SummaryCompressor
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.manager import SessionManager
from rpg_core.tests.conftest import FakeBatchStore, FakeMemorySubAgent


@pytest.mark.asyncio
async def test_summary_compressor_marks_processed_without_truncating_history():
    batch_store = FakeBatchStore()
    memory_sub_agent = FakeMemorySubAgent()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory_sub_agent,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=2,
        compression_threshold=1,
        compress_batch_size=2,
    )

    session = SessionManager(session_id="s1", workspace="data/test_workspace", history_enabled=False)
    session.replace_history([
        Message(Role.SYSTEM, "system"),
        Message(Role.USER, "u1", uid=101, turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", uid=102, turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", uid=103, turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", uid=104, turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u3", uid=105, turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "a3", uid=106, turn_id=3, seq_in_turn=2),
        Message(Role.USER, "u4", uid=107, turn_id=4, seq_in_turn=1),
        Message(Role.ASSISTANT, "a4", uid=108, turn_id=4, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.triggered is True
    assert result.summary_generated is True
    assert result.batch_files == ["batch_2.md"]
    assert result.overall_file == "overall.md"
    assert [m.content for m in session.history] == ["system", "u1", "a1", "u2", "a2", "u3", "a3", "u4", "a4"]
    assert session.summary_turn_groups_for_compression(2) == []
    assert memory_sub_agent.batch_calls
    assert memory_sub_agent.overall_calls
    assert batch_store.batch_summaries[0]["title"] == "batch-2"
    assert batch_store.batch_summaries[0]["source_turn_start"] == 1
    assert batch_store.batch_summaries[0]["source_turn_end"] == 2
    assert batch_store.batch_summaries[0]["source_message_ids"] == [101, 102, 103, 104]

    second = await compressor.maybe_compress(session)
    assert second.triggered is False


@pytest.mark.asyncio
async def test_summary_overall_failure_removes_batches_and_keeps_progress_retryable():
    class FailingOverall(FakeMemorySubAgent):
        async def generate_overall_summary(self, new_batches, existing_overall):  # noqa: ANN001
            return None

    batch_store = FakeBatchStore()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=FailingOverall(),  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=2,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.triggered is True
    assert result.summary_generated is False
    assert result.batch_files is None
    assert batch_store.batch_summaries == []
    assert [group[0].turn_id for group in session.summary_turn_groups_for_compression(1)] == [1]


@pytest.mark.asyncio
async def test_summary_progress_failure_restores_files_and_overall():
    class FailingProgressSession(SessionManager):
        def mark_summary_batches_processed(self, batches):  # noqa: ANN001
            raise RuntimeError("database write failed")

    batch_store = FakeBatchStore()
    batch_store.overall = ("previous overall", 1)
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=FakeMemorySubAgent(),  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=2,
    )
    session = FailingProgressSession(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.summary_generated is False
    assert batch_store.batch_summaries == []
    assert batch_store.overall == ("previous overall", 1)
    assert [group[0].turn_id for group in session.summary_turn_groups_for_compression(1)] == [1]


@pytest.mark.asyncio
async def test_summary_compressor_noop_when_disabled_or_short():
    batch_store = FakeBatchStore()
    memory_sub_agent = FakeMemorySubAgent()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory_sub_agent,  # type: ignore[arg-type]
        enabled=False,
        keep_recent_rounds=2,
        compression_threshold=1,
    )

    session = SessionManager(session_id="s1", workspace="data/test_workspace", history_enabled=False)
    session.replace_history([
        Message(Role.SYSTEM, "system"),
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
    ], persist=False)
    result = await compressor.maybe_compress(session)

    assert result.triggered is False
    assert session.history[0].content == "system"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "processor",
    [None, SimpleNamespace(enabled=False)],
)
async def test_strict_summary_fails_when_required_processor_is_unavailable(
    processor,
):  # noqa: ANN001
    compressor = SummaryCompressor(
        batch_store=FakeBatchStore(),
        memory_sub_agent=processor,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session, strict=True)

    assert result.status is CompressionStatus.FAILED
    assert result.triggered is True
    assert result.error_code == "SUMMARY_PROCESSOR_UNAVAILABLE"


@pytest.mark.asyncio
async def test_strict_summary_fails_when_required_store_is_unavailable():
    compressor = SummaryCompressor(
        batch_store=None,
        memory_sub_agent=FakeMemorySubAgent(),  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session, strict=True)

    assert result.status is CompressionStatus.FAILED
    assert result.triggered is True
    assert result.error_code == "SUMMARY_STORE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_strict_summary_rejects_oversized_turn_without_progress():
    compressor = SummaryCompressor(
        batch_store=FakeBatchStore(),
        memory_sub_agent=FakeMemorySubAgent(),  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        max_batch_chars=4,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "oversized", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "reply", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "kept", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "kept reply", turn_id=2, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session, strict=True)

    assert result.status is CompressionStatus.FAILED
    assert result.error_code == "SUMMARY_INPUT_TOO_LARGE"
    assert [group[0].turn_id for group in session.summary_turn_groups_for_compression(1)] == [1]


@pytest.mark.asyncio
async def test_strict_summary_keeps_disabled_or_unneeded_work_skipped():
    short_session = SessionManager(history_enabled=False)
    short_session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ], persist=False)
    unavailable = SummaryCompressor(
        batch_store=None,
        memory_sub_agent=None,
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
    )

    unneeded = await unavailable.maybe_compress(short_session, strict=True)

    disabled_session = SessionManager(history_enabled=False)
    disabled_session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)
    disabled = SummaryCompressor(
        batch_store=None,
        memory_sub_agent=FakeMemorySubAgent(),  # type: ignore[arg-type]
        enabled=False,
        keep_recent_rounds=1,
        compression_threshold=0,
    )

    configured_off = await disabled.maybe_compress(disabled_session, strict=True)

    assert unneeded.status is CompressionStatus.SKIPPED
    assert unneeded.triggered is False
    assert configured_off.status is CompressionStatus.SKIPPED
    assert configured_off.triggered is False


@pytest.mark.asyncio
async def test_disabled_auto_compression_still_marks_ooc_unless_memory_is_global_disabled():
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "ooc", mode="ooc", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "answer", mode="ooc", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "ic", mode="ic", turn_id=2, seq_in_turn=1),
    ], persist=False)
    compressor = SummaryCompressor(
        batch_store=None,
        memory_sub_agent=FakeMemorySubAgent(),  # type: ignore[arg-type]
        enabled=False,
        keep_recent_rounds=1,
    )

    result = await compressor.maybe_compress(session)

    assert result.triggered is False
    assert [message.content for message in session.context_history().messages] == ["ic"]

    globally_disabled_session = SessionManager(history_enabled=False)
    globally_disabled_session.replace_history([
        Message(Role.USER, "ooc", mode="ooc", turn_id=1, seq_in_turn=1),
    ], persist=False)
    globally_disabled = SummaryCompressor(
        memory_sub_agent=SimpleNamespace(enabled=False),  # type: ignore[arg-type]
        enabled=False,
    )
    await globally_disabled.maybe_compress(globally_disabled_session)
    assert [message.content for message in globally_disabled_session.context_history().messages] == ["ooc"]


@pytest.mark.asyncio
async def test_summary_compressor_falls_back_to_message_windows_without_user_anchor():
    batch_store = FakeBatchStore()
    memory_sub_agent = FakeMemorySubAgent()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory_sub_agent,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=2,
    )

    session = SessionManager(session_id="s1", workspace="data/test_workspace", history_enabled=False)
    session.replace_history([
        Message(Role.SYSTEM, "system"),
        Message(Role.ASSISTANT, "a1"),
        Message(Role.TOOL, "t1"),
        Message(Role.ASSISTANT, "a2"),
        Message(Role.TOOL, "t2"),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.triggered is True
    assert result.batch_files == ["batch_2.md"]
    assert [m.content for m in session.history] == ["system", "a1", "t1", "a2", "t2"]
    assert session.summary_turn_groups_for_compression(1) == []


@pytest.mark.asyncio
async def test_strict_summary_rolls_back_successful_batches_after_later_failure():
    class FailsSecondBatch(FakeMemorySubAgent):
        async def generate_batch_summary(self, conv, batch_id, user_rounds):  # noqa: ANN001
            if len(self.batch_calls) == 1:
                self.batch_calls.append({"batch_id": batch_id})
                return None
            return await super().generate_batch_summary(conv, batch_id, user_rounds)

    batch_store = FakeBatchStore()
    memory = FailsSecondBatch()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=1,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u3", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "a3", turn_id=3, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session, strict=True)

    assert result.status is CompressionStatus.FAILED
    assert result.error_code == "SUMMARY_BATCH_FAILED"
    assert result.summary_generated is False
    assert batch_store.batch_summaries == []
    assert [group[0].turn_id for group in session.summary_turn_groups_for_compression(1)] == [1, 2]


@pytest.mark.asyncio
async def test_normal_summary_commits_successful_prefix_and_stops_after_failure():
    class FailsSecondBatch(FakeMemorySubAgent):
        async def generate_batch_summary(self, conv, batch_id, user_rounds):  # noqa: ANN001
            if len(self.batch_calls) == 1:
                self.batch_calls.append({"batch_id": batch_id})
                return None
            return await super().generate_batch_summary(conv, batch_id, user_rounds)

    batch_store = FakeBatchStore()
    memory = FailsSecondBatch()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=1,
    )
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u3", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "a3", turn_id=3, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.status is CompressionStatus.SUCCEEDED
    assert result.user_rounds_compressed == 1
    assert len(memory.batch_calls) == 2
    assert [group[0].turn_id for group in session.summary_turn_groups_for_compression(1)] == [2]


@pytest.mark.asyncio
async def test_summary_overall_merges_new_batches_one_at_a_time_then_commits_once():
    class IncrementalBatchStore(FakeBatchStore):
        def __init__(self) -> None:
            super().__init__()
            self.overall = ("existing overall", 1)
            self.save_overall_calls = 0

        def get_new_content(self, last_batch_id: int):
            return [
                str(item["summary_text"])
                for item in self.batch_summaries
                if int(item["batch_id"]) > last_batch_id
            ]

        def save_overall(self, **kwargs):
            self.save_overall_calls += 1
            return super().save_overall(**kwargs)

    class IncrementalMemory(FakeMemorySubAgent):
        async def generate_batch_summary(self, conv, batch_id, user_rounds):  # noqa: ANN001
            result = await super().generate_batch_summary(conv, batch_id, user_rounds)
            result["summary_text"] = f"batch-summary-{batch_id}"
            return result

        async def generate_overall_summary(self, new_batches, existing_overall):  # noqa: ANN001
            self.overall_calls.append({
                "new_batches": list(new_batches),
                "existing_overall": existing_overall,
            })
            return {
                "title": "overall",
                "summary_text": f"{existing_overall}|{new_batches[0]}",
                "key_events": [],
            }

    class TrackingSession(SessionManager):
        def __init__(self) -> None:
            super().__init__(history_enabled=False)
            self.progress_commits = 0

        def mark_summary_batches_processed(self, batches):  # noqa: ANN001
            self.progress_commits += 1
            return super().mark_summary_batches_processed(batches)

    batch_store = IncrementalBatchStore()
    memory = IncrementalMemory()
    compressor = SummaryCompressor(
        batch_store=batch_store,
        memory_sub_agent=memory,  # type: ignore[arg-type]
        enabled=True,
        keep_recent_rounds=1,
        compression_threshold=0,
        compress_batch_size=1,
    )
    session = TrackingSession()
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "u3", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "a3", turn_id=3, seq_in_turn=2),
        Message(Role.USER, "u4", turn_id=4, seq_in_turn=1),
        Message(Role.ASSISTANT, "a4", turn_id=4, seq_in_turn=2),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.status is CompressionStatus.SUCCEEDED
    assert [call["new_batches"] for call in memory.overall_calls] == [
        ["batch-summary-2"],
        ["batch-summary-3"],
        ["batch-summary-4"],
    ]
    assert [call["existing_overall"] for call in memory.overall_calls] == [
        "existing overall",
        "existing overall|batch-summary-2",
        "existing overall|batch-summary-2|batch-summary-3",
    ]
    assert batch_store.overall == (
        "existing overall|batch-summary-2|batch-summary-3|batch-summary-4",
        4,
    )
    assert batch_store.save_overall_calls == 1
    assert session.progress_commits == 1
