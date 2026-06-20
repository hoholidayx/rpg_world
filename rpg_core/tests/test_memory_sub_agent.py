from __future__ import annotations

import asyncio
from types import SimpleNamespace

from rpg_world.rpg_core.agent.sub_agents.memory_sub_agent import MemoryAgentResult, MemorySubAgent
from rpg_world.rpg_core.context.rpg_context import Role
from rpg_world.rpg_core.session.manager import SessionManager


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
    session.set_last_story_turn_id(t1)

    sub_agent = MemorySubAgent(story_store=DummyStoryStore())

    async def fake_process(context):
        assert [m.content for m in context["story"]] == ["u2", "a2"]
        return MemoryAgentResult(story_details_added=3)

    sub_agent.process = fake_process  # type: ignore[assignment]
    await sub_agent._execute_story_memory(SimpleNamespace(_session=session))
    return session.last_story_turn_id


def test_execute_story_memory_advances_turn_cursor(tmp_path):
    last_turn_id = asyncio.run(_run_execute_story_memory(str(tmp_path)))

    assert last_turn_id == 2
