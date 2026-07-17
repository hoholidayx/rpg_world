from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from rpg_core.agent.agent_types import TurnStats
from rpg_core.agent.resources import AgentContextResources
from rpg_core.agent.sub_agents import (
    StatusSubAgentPreflightOutcome,
    StatusSubAgentResult,
)
from rpg_core.agent.turn.hooks import (
    MemoryRecallHook,
    PostCommitHooks,
    StatusPreflightHook,
)
from rpg_core.session.manager import SessionManager
from rpg_core.context.rpg_context import Message, Role


class _StatusScratch:
    def __init__(self) -> None:
        self.value = 0
        self.change_token = 0

    def create_checkpoint(self) -> int:
        return self.value

    def restore_checkpoint(self, checkpoint: int) -> None:
        self.value = checkpoint


class _Scene:
    def __init__(self) -> None:
        self.time = "old"

    def get_time_state(self) -> str:
        return self.time

    def set_time_state(self, value: str) -> None:
        self.time = value

    def get_context(self) -> str:
        return "scene"


class _SubAgent:
    def __init__(self, scratch: _StatusScratch, scene: _Scene) -> None:
        self.scratch = scratch
        self.scene = scene
        self.bound_tools = []
        self.preflight_kwargs = {}

    @contextmanager
    def use_turn_tools(
        self,
        tools,
        *,
        create_checkpoint,
        restore_checkpoint,
        **_kwargs,
    ):
        self.bound_tools = list(tools)
        checkpoint = create_checkpoint()
        self.scratch.value = 9
        self.scene.time = "new"
        restore_checkpoint(checkpoint)
        yield

    async def run_preflight(self, **_kwargs) -> StatusSubAgentResult:
        self.preflight_kwargs = dict(_kwargs)
        return StatusSubAgentResult(updated=True)


class _Tools:
    @staticmethod
    def narrative_outcome_tools(_input, _runtime):  # noqa: ANN001, ANN205
        return []

    @staticmethod
    def state_tools(_scene, _status):  # noqa: ANN001, ANN205
        return [SimpleNamespace(name="scene_time")]


@pytest.mark.asyncio
async def test_status_preflight_hook_binds_scratch_checkpoint_restore() -> None:
    status_scratch = _StatusScratch()
    scene = _Scene()
    sub_agent = _SubAgent(status_scratch, scene)
    hook = StatusPreflightHook(
        status_sub_agent=lambda: sub_agent,
        tool_service=_Tools(),
    )
    scratch = SimpleNamespace(
        status_scratch=status_scratch,
        scene_tracker=scene,
        status_manager=None,
        base_history=[],
        narrative_outcome=None,
    )

    result = await hook.run(
        turn_scratch=scratch,
        user_input="行动",
        turn_stats=TurnStats(),
        player_character=SimpleNamespace(name="Alice"),
    )

    assert result.updated is True
    assert status_scratch.value == 0
    assert scene.time == "old"
    assert [tool.name for tool in sub_agent.bound_tools] == ["scene_time"]
    assert sub_agent.preflight_kwargs["player_character"].name == "Alice"


def test_status_preflight_outcome_state_is_structured() -> None:
    staged = SimpleNamespace(narrative_outcome=object())
    assert (
        StatusPreflightHook.outcome_state(staged, None)
        is StatusSubAgentPreflightOutcome.STAGED
    )
    fallback = SimpleNamespace(narrative_outcome=None)
    assert (
        StatusPreflightHook.outcome_state(
            fallback,
            StatusSubAgentResult(failed=True),
        )
        is StatusSubAgentPreflightOutcome.FALLBACK
    )
    assert (
        StatusPreflightHook.outcome_state(fallback, None)
        is StatusSubAgentPreflightOutcome.NONE
    )


async def test_memory_recall_hook_warns_and_continues_on_failure() -> None:
    class _Memory:
        @staticmethod
        async def recall(_input: str) -> None:
            raise RuntimeError("recall failed")

    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=_Memory(),
    )

    await MemoryRecallHook(
        lambda: resources,
        SessionManager(history_enabled=False),
    ).run("hello")


@pytest.mark.asyncio
async def test_memory_recall_hook_builds_turn_local_rp_query_context() -> None:
    captured = []

    class _Memory:
        async def recall(self, context) -> None:  # noqa: ANN001
            captured.append(context)

    class _Scene:
        @staticmethod
        def get_recall_context():
            return {"time": "第二天清晨", "location": "雾港"}

    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "old", mode="ic", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "old answer", mode="ic", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "debug", mode="ooc", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "debug answer", mode="ooc", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "艾琳提出钟楼会合", mode="gm", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "她答应明早前往", mode="gm", turn_id=3, seq_in_turn=2),
    ], persist=False)
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=_Memory(),
    )

    await MemoryRecallHook(lambda: resources, session).run(
        "她答应了什么？",
        player_character=SimpleNamespace(name="洛恩"),
        scene_tracker=_Scene(),  # type: ignore[arg-type]
    )

    assert captured[0].current_input == "她答应了什么？"
    assert captured[0].player_character == "洛恩"
    assert captured[0].scene_time == "第二天清晨"
    assert captured[0].scene_location == "雾港"
    assert len(captured[0].recent_turns) == 2
    assert all("debug" not in turn for turn in captured[0].recent_turns)
    assert "艾琳" in captured[0].recent_turns[-1]


@pytest.mark.asyncio
async def test_post_commit_hooks_isolate_each_failure() -> None:
    calls: list[str] = []

    class _Memory:
        async def maybe_auto_extract(self, _session) -> None:  # noqa: ANN001
            calls.append("memory")
            raise RuntimeError("memory failed")

    class _Compressor:
        async def maybe_compress(self, _session):  # noqa: ANN001, ANN201
            calls.append("compressor")
            return SimpleNamespace(
                triggered=False,
                user_rounds_compressed=0,
                batch_files=[],
            )

    lifecycle = SimpleNamespace(
        memory_sub_agent=_Memory(),
        compressor=_Compressor(),
    )
    await PostCommitHooks(
        lifecycle=lifecycle,
        session_manager=SimpleNamespace(),
    ).run()

    assert calls == ["memory", "compressor"]
