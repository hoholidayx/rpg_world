from __future__ import annotations

import pytest
from types import SimpleNamespace

from rpg_core.summary.compressor import SummaryCompressor
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

    assert result.triggered is True
    assert result.summary_generated is True
    assert result.batch_files == ["batch_2.md"]
    assert result.overall_file == "overall.md"
    assert [m.content for m in session.history] == ["system", "u1", "a1", "u2", "a2", "u3", "a3", "u4", "a4"]
    assert session.summary_turn_groups_for_compression(2) == []
    assert memory_sub_agent.batch_calls
    assert memory_sub_agent.overall_calls
    assert batch_store.batch_summaries[0]["title"] == "batch-2"

    second = await compressor.maybe_compress(session)
    assert second.triggered is False


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
