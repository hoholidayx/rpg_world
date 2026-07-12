from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from rpg_core.agent.sub_agents.memory_sub_agent import MemoryAgentResult, MemorySubAgent
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.manager import SessionManager


class DummyStoryStore:
    pass


async def _run_execute_story_memory(workspace: str) -> int:
    session = SessionManager(session_id="s1", workspace=workspace, history_enabled=False)
    session.load()
    t1 = session.begin_turn()
    session.append(Role.USER, "u1", turn_id=t1)
    session.append(Role.ASSISTANT, "a1", turn_id=t1)
    session.end_turn(t1)
    t2 = session.begin_turn()
    session.append(Role.USER, "u2", turn_id=t2)
    session.append(Role.ASSISTANT, "a2", turn_id=t2)
    session.end_turn(t2)
    session.mark_story_messages_processed(session.turn_messages(t1))

    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
        enabled=False,
    )

    async def fake_process(context):
        assert [m.content for m in context["story"]] == ["u2", "a2"]
        return MemoryAgentResult(story_details_added=3)

    sub_agent.process = fake_process  # type: ignore[assignment]
    await sub_agent._execute_story_memory(SimpleNamespace(session_manager=session))
    return session.count_new_turns_since_story()


def test_execute_story_memory_marks_messages_processed(tmp_path):
    remaining_turns = asyncio.run(_run_execute_story_memory(str(tmp_path)))

    assert remaining_turns == 0


async def _run_story_progress_restart(workspace: str, make_data_session) -> tuple[list[str], int]:
    make_data_session("s2")
    session = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    session.load()
    t1 = session.begin_turn()
    session.append(Role.USER, "u1", turn_id=t1)
    session.append(Role.ASSISTANT, "a1", turn_id=t1)
    session.end_turn(t1)
    t2 = session.begin_turn()
    session.append(Role.USER, "u2", turn_id=t2)
    session.append(Role.ASSISTANT, "a2", turn_id=t2)
    session.end_turn(t2)
    session.mark_story_messages_processed(session.turn_messages(t1))

    reloaded = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    reloaded.load()
    new_msgs = reloaded.story_messages_since_last_extraction()
    assert [m.content for m in new_msgs] == ["u2", "a2"]
    reloaded.mark_story_messages_processed(new_msgs)
    return [m.content for m in reloaded.story_messages_since_last_extraction()], reloaded.count_new_turns_since_story()


def test_story_progress_restart(tmp_path, make_data_session):
    remaining, remaining_turns = asyncio.run(_run_story_progress_restart(str(tmp_path), make_data_session))

    assert remaining == []
    assert remaining_turns == 0


@pytest.mark.asyncio
async def test_story_memory_failure_keeps_messages_retryable() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ], persist=False)
    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
        enabled=True,
    )

    async def fail_process(_context):
        raise RuntimeError("provider failed")

    sub_agent.process = fail_process  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="provider failed"):
        await sub_agent._execute_story_memory(SimpleNamespace(session_manager=session))

    assert session.count_new_turns_since_story() == 1
