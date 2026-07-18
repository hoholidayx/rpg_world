from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rpg_core.agent.sub_agents.memory.agent as memory_module
from llm_client.types import LLMResponse, LLMUsage
from rpg_core.agent.sub_agents.memory.agent import (
    MEMORY_LLM_SOURCE_STORY,
    MemoryAgentResult,
    MemorySubAgent,
    STORY_DETAIL_SCHEMA,
    StoryMemoryExtractionStatus,
)
from rpg_core.context.models import Message, Role
from rpg_core.session.manager import SessionManager


async def _async_value(value):  # noqa: ANN001, ANN201
    return value


class DummyStoryStore:
    pass


class CapturingStoryStore:
    def __init__(self, items: list[dict[str, object]] | None = None) -> None:
        self.items = list(items or [])
        self.persist_calls = 0

    def get_all(self) -> list[dict[str, object]]:
        return list(self.items)

    def add_details_and_mark_processed(self, details, **_kwargs) -> int:  # noqa: ANN001
        self.persist_calls += 1
        return len(list(details))


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
async def test_pending_story_memory_is_turn_batched_and_keeps_successful_prefix() -> None:
    session = SessionManager(history_enabled=False)
    history: list[Message] = []
    for turn_id in range(1, 6):
        history.extend([
            Message(Role.USER, f"u{turn_id}", turn_id=turn_id, seq_in_turn=1),
            Message(Role.ASSISTANT, f"a{turn_id}", turn_id=turn_id, seq_in_turn=2),
        ])
    session.replace_history(history, persist=False)
    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
    )
    calls: list[list[int]] = []

    async def process(context):  # noqa: ANN001
        turn_ids = sorted({message.turn_id for message in context["story"]})
        calls.append(turn_ids)
        if len(calls) == 2:
            raise RuntimeError("second batch failed")
        return MemoryAgentResult(story_details_added=turn_ids[-1])

    sub_agent.process = process  # type: ignore[assignment]

    result = await sub_agent.extract_pending_story_memory(
        session,
        strict=True,
        batch_turns=2,
    )

    assert result.status is StoryMemoryExtractionStatus.FAILED
    assert result.pending_turns == 5
    assert result.completed_turns == 2
    assert result.completed_batches == 1
    assert result.story_details_added == 2
    assert calls == [[1, 2], [3, 4]]
    assert [group[0].turn_id for group in session.story_turn_groups_since_last_extraction()] == [3, 4, 5]


@pytest.mark.asyncio
async def test_pending_story_memory_marks_ooc_and_batches_all_ic_gm() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "ooc", mode="ooc", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "ooc answer", mode="ooc", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "ic", mode="ic", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "ic answer", mode="ic", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "gm", mode="gm", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "gm answer", mode="gm", turn_id=3, seq_in_turn=2),
    ], persist=False)
    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
    )
    calls: list[list[int]] = []

    async def process(context):  # noqa: ANN001
        calls.append(sorted({message.turn_id for message in context["story"]}))
        return MemoryAgentResult()

    sub_agent.process = process  # type: ignore[assignment]

    result = await sub_agent.extract_pending_story_memory(session, batch_turns=1)

    assert result.status is StoryMemoryExtractionStatus.SUCCEEDED
    assert result.pending_turns == 2
    assert result.completed_batches == 2
    assert calls == [[2], [3]]
    assert session.count_new_turns_since_story() == 0


@pytest.mark.asyncio
async def test_pending_story_memory_respects_character_budget_at_turn_boundaries() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "a2", turn_id=2, seq_in_turn=2),
    ], persist=False)
    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
    )
    calls: list[list[int]] = []

    async def process(context):  # noqa: ANN001
        calls.append(sorted({message.turn_id for message in context["story"]}))
        return MemoryAgentResult()

    sub_agent.process = process  # type: ignore[assignment]

    result = await sub_agent.extract_pending_story_memory(
        session,
        batch_turns=10,
        max_batch_chars=5,
    )

    assert result.status is StoryMemoryExtractionStatus.SUCCEEDED
    assert calls == [[1], [2]]


@pytest.mark.asyncio
async def test_pending_story_memory_rejects_oversized_turn_without_progress() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "oversized", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "reply", turn_id=1, seq_in_turn=2),
    ], persist=False)
    sub_agent = MemorySubAgent(
        story_store=DummyStoryStore(),
        provider_biz_key="agent.memory_sub_agent",
    )

    result = await sub_agent.extract_pending_story_memory(
        session,
        strict=True,
        max_batch_chars=4,
    )

    assert result.status is StoryMemoryExtractionStatus.FAILED
    assert result.error_code == "STORY_MEMORY_INPUT_TOO_LARGE"
    assert session.count_new_turns_since_story() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("wrong_memory_tool", '{"story_details": []}'),
        ("extract_story_details", "[]"),
        ("extract_story_details", "{}"),
    ],
)
async def test_strict_story_memory_rejects_malformed_tool_response_without_progress(
    tool_name: str,
    arguments: str,
) -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ], persist=False)
    store = CapturingStoryStore()
    sub_agent = MemorySubAgent(
        story_store=store,  # type: ignore[arg-type]
        provider_biz_key="agent.memory_sub_agent",
    )

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools == [STORY_DETAIL_SCHEMA]
            return {
                "tool_calls": [{
                    "function": {
                        "name": tool_name,
                        "arguments": arguments,
                    }
                }]
            }

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]

    result = await sub_agent.extract_pending_story_memory(session, strict=True)

    assert result.status is StoryMemoryExtractionStatus.FAILED
    assert result.error_code == "STORY_MEMORY_BATCH_FAILED"
    assert store.persist_calls == 0
    assert session.count_new_turns_since_story() == 1


@pytest.mark.asyncio
async def test_strict_story_memory_accepts_explicit_empty_details_and_advances() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ], persist=False)
    store = CapturingStoryStore()
    sub_agent = MemorySubAgent(
        story_store=store,  # type: ignore[arg-type]
        provider_biz_key="agent.memory_sub_agent",
    )

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools == [STORY_DETAIL_SCHEMA]
            return {
                "tool_calls": [{
                    "function": {
                        "name": "extract_story_details",
                        "arguments": '{"story_details": []}',
                    }
                }]
            }

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]

    result = await sub_agent.extract_pending_story_memory(session, strict=True)

    assert result.status is StoryMemoryExtractionStatus.SUCCEEDED
    assert result.story_details_added == 0
    assert store.persist_calls == 1
    assert session.count_new_turns_since_story() == 0


@pytest.mark.asyncio
async def test_disabled_story_memory_skips_non_strict_but_fails_strict() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ], persist=False)
    sub_agent = MemorySubAgent(
        story_store=CapturingStoryStore(),  # type: ignore[arg-type]
        provider_biz_key="agent.memory_sub_agent",
        enabled=False,
    )

    non_strict = await sub_agent.extract_pending_story_memory(session)
    strict = await sub_agent.extract_pending_story_memory(session, strict=True)

    assert non_strict.status is StoryMemoryExtractionStatus.SKIPPED
    assert non_strict.error_code is None
    assert strict.status is StoryMemoryExtractionStatus.FAILED
    assert strict.error_code == "STORY_MEMORY_PROCESSOR_BUSY"
    assert session.count_new_turns_since_story() == 1


@pytest.mark.asyncio
async def test_story_memory_and_summary_prompts_keep_long_message_tail() -> None:
    tail_marker = "TAIL-MUST-REACH-THE-LLM"
    long_content = "x" * 900 + tail_marker
    store = CapturingStoryStore()
    sub_agent = MemorySubAgent(
        story_store=store,  # type: ignore[arg-type]
        provider_biz_key="agent.memory_sub_agent",
    )
    prompts: dict[str, str] = {}

    async def capture(messages, _schema, *, source, **_kwargs):  # noqa: ANN001
        prompts[source] = str(messages[1]["content"])
        if source == memory_module.MEMORY_LLM_SOURCE_STORY:
            return {"story_details": []}, None
        return {
            "title": "batch",
            "summary_text": "summary",
            "characters": [],
        }, None

    sub_agent._call_llm = capture  # type: ignore[method-assign]
    conversation = [
        Message(
            Role.USER,
            long_content,
            uid=1,
            turn_id=1,
            seq_in_turn=1,
        ),
    ]

    await sub_agent._pipeline_story_memory(conversation, [])
    await sub_agent.generate_batch_summary(conversation, batch_id=1, user_rounds=1)

    assert tail_marker in prompts[memory_module.MEMORY_LLM_SOURCE_STORY]
    assert tail_marker in prompts[memory_module.MEMORY_LLM_SOURCE_BATCH_SUMMARY]


@pytest.mark.asyncio
async def test_story_memory_semantic_dedupe_prompt_has_hard_limits() -> None:
    item_count = memory_module.STORY_MEMORY_DEDUPE_MAX_ITEMS + 7
    items = [
        {
            "text": (
                f"memory-{index:03d}:"
                + "x" * (memory_module.STORY_MEMORY_DEDUPE_MAX_ITEM_CHARS + 100)
            ),
        }
        for index in range(item_count)
    ]
    store = CapturingStoryStore(items)
    sub_agent = MemorySubAgent(
        story_store=store,  # type: ignore[arg-type]
        provider_biz_key="agent.memory_sub_agent",
    )
    captured_prompt = ""

    async def capture(messages, _schema, **_kwargs):  # noqa: ANN001
        nonlocal captured_prompt
        captured_prompt = str(messages[1]["content"])
        return {"story_details": []}, None

    sub_agent._call_llm = capture  # type: ignore[method-assign]
    await sub_agent._pipeline_story_memory(
        [Message(Role.USER, "new event", uid=1, turn_id=1, seq_in_turn=1)],
        [],
    )

    dedupe_section = captured_prompt.split(
        "## Existing Story Memory (for deduplication)\n", 1
    )[1].split("\n\nCall `extract_story_details`", 1)[0]
    dedupe_lines = dedupe_section.splitlines()

    assert len(dedupe_lines) == memory_module.STORY_MEMORY_DEDUPE_MAX_ITEMS
    assert dedupe_lines[0].startswith("- memory-007:")
    assert dedupe_lines[-1].startswith(f"- memory-{item_count - 1:03d}:")
    assert all(
        len(line.removeprefix("- "))
        <= memory_module.STORY_MEMORY_DEDUPE_MAX_ITEM_CHARS
        for line in dedupe_lines
    )


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
