from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
    session.set_last_story_turn_index(1)

    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
        enabled=False,
    )

    async def fake_process(context):
        assert [m.content for m in context["story"]] == ["u2", "a2"]
        return MemoryAgentResult(story_details_added=3)

    sub_agent.process = fake_process  # type: ignore[assignment]
    await sub_agent._execute_story_memory(SimpleNamespace(_session=session))
    return session.last_story_turn_index


def test_execute_story_memory_advances_turn_cursor(tmp_path):
    last_turn_index = asyncio.run(_run_execute_story_memory(str(tmp_path)))

    assert last_turn_index == 2


async def _run_story_cursor_restart_without_turn_ids(workspace: str) -> tuple[list[str], int]:
    session = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    session.load()
    session.replace_history([
        Message(Role.ASSISTANT, "a1", hid=1, turn_id=0, seq_in_turn=0),
        Message(Role.TOOL, "t1", hid=2, turn_id=0, seq_in_turn=0),
        Message(Role.SYSTEM, "s1", hid=3, turn_id=0, seq_in_turn=0),
    ], persist=True)
    session.set_last_story_turn_index(1)

    reloaded = SessionManager(session_id="s2", workspace=workspace, history_enabled=True)
    reloaded.load()
    new_msgs = reloaded.story_messages_since_last_extraction()
    assert [m.content for m in new_msgs] == ["s1"]
    reloaded.mark_story_messages_processed(new_msgs)
    return [m.content for m in reloaded.story_messages_since_last_extraction()], reloaded.last_story_turn_index


def test_story_cursor_restart_without_turn_ids(tmp_path):
    remaining, last_turn_index = asyncio.run(_run_story_cursor_restart_without_turn_ids(str(tmp_path)))

    assert remaining == []
    assert last_turn_index == 2
