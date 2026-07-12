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
        self.update_kwargs = {}

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

    async def update(self, **_kwargs) -> StatusSubAgentResult:
        self.update_kwargs = dict(_kwargs)
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
    assert sub_agent.update_kwargs["player_character"].name == "Alice"


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


def test_memory_recall_hook_warns_and_continues_on_failure() -> None:
    class _Memory:
        @staticmethod
        def recall(_input: str) -> None:
            raise RuntimeError("recall failed")

    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=_Memory(),
    )

    MemoryRecallHook(lambda: resources).run("hello")


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
