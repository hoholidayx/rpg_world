from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rpg_core.agent.sub_agents.memory_sub_agent as memory_module
from rpg_core.agent.agent_types import LLMResponse, LLMUsage
from rpg_core.agent.sub_agents.memory_sub_agent import (
    MEMORY_LLM_SOURCE_STORY,
    MemoryAgentResult,
    MemorySubAgent,
    STORY_DETAIL_SCHEMA,
)
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.manager import SessionManager


async def _async_value(value):  # noqa: ANN001, ANN201
    return value


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


@pytest.mark.asyncio
async def test_memory_sub_agent_logs_request_shape_and_cache_by_pipeline(
    monkeypatch,
) -> None:
    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools == [STORY_DETAIL_SCHEMA]
            return LLMResponse(
                content="",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "extract_story_details",
                        "arguments": '{"story_details": []}',
                    },
                }],
                finish_reason="tool_calls",
                usage=LLMUsage(
                    prompt_tokens=80,
                    completion_tokens=5,
                    total_tokens=85,
                    prompt_cache_hit_tokens=50,
                    prompt_cache_miss_tokens=30,
                ),
                model="qwen",
            )

        def get_default_model(self) -> str:
            return "qwen"

    info = MagicMock()
    monkeypatch.setattr(
        memory_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(memory_module.logger, "info", info)
    sub_agent = MemorySubAgent(provider_biz_key="agent.memory_sub_agent")
    sub_agent._get_provider = lambda: _async_value(Provider())  # type: ignore[method-assign]

    decision, record = await sub_agent._call_llm(
        [
            {"role": "system", "content": "stable memory system"},
            {"role": "user", "content": "dynamic memory input"},
        ],
        STORY_DETAIL_SCHEMA,
        source=MEMORY_LLM_SOURCE_STORY,
    )

    assert decision == {"story_details": []}
    assert record is not None
    assert record.source == MEMORY_LLM_SOURCE_STORY

    fingerprint = next(
        call
        for call in info.call_args_list
        if "LLM request fingerprint" in call.args[0]
    )
    assert fingerprint.args[1] == MEMORY_LLM_SOURCE_STORY
    assert [item["role"] for item in fingerprint.args[11]] == ["system", "user"]
    assert [item["chars"] for item in fingerprint.args[11]] == [
        len("stable memory system"),
        len("dynamic memory input"),
    ]
    assert "stable memory system" not in repr(fingerprint)
    assert "dynamic memory input" not in repr(fingerprint)

    cache_usage = next(
        call
        for call in info.call_args_list
        if "LLM cache usage" in call.args[0]
    )
    assert cache_usage.args[1:] == (MEMORY_LLM_SOURCE_STORY, 50, 30, 62.5)
