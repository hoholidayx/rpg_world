from __future__ import annotations

import pytest

from rpg_world.rpg_core.summary.compressor import SummaryCompressor
from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.manager import SessionManager
from rpg_world.rpg_core.tests.conftest import FakeBatchStore, FakeMemorySubAgent


@pytest.mark.asyncio
async def test_summary_compressor_triggers_and_truncates():
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
        Message(Role.USER, "u1"),
        Message(Role.ASSISTANT, "a1"),
        Message(Role.USER, "u2"),
        Message(Role.ASSISTANT, "a2"),
        Message(Role.USER, "u3"),
        Message(Role.ASSISTANT, "a3"),
        Message(Role.USER, "u4"),
        Message(Role.ASSISTANT, "a4"),
    ], persist=False)

    result = await compressor.maybe_compress(session)

    assert result.triggered is True
    assert result.summary_generated is True
    assert result.batch_files == ["batch_0.md"]
    assert result.overall_file == "overall.md"
    assert [m.content for m in session.history] == ["system", "u3", "a3", "u4", "a4"]
    assert memory_sub_agent.batch_calls
    assert memory_sub_agent.overall_calls
    assert batch_store.batch_summaries[0]["title"] == "batch-0"


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
    session.replace_history([Message(Role.SYSTEM, "system"), Message(Role.USER, "u1")], persist=False)
    result = await compressor.maybe_compress(session)

    assert result.triggered is False
    assert session.history[0].content == "system"


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
    assert result.batch_files == ["batch_0.md"]
    assert [m.content for m in session.history] == ["system", "a2", "t2"]
