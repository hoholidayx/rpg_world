from types import SimpleNamespace

import pytest

from rpg_core.agent.resources import AgentContextResources
from rpg_core.agent.turn import (
    TurnExecutionPlan,
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnMode,
    TurnRequest,
)
from rpg_core.agent.turn.factory import TurnRuntimeFactory
from rpg_core.agent.sub_agents import StatusSubAgentPreflightOutcome
from rpg_core.session import SessionManager


def _plan(mode: TurnMode = TurnMode.IC) -> TurnExecutionPlan:
    request = TurnRequest.create("行动", mode=mode)
    return TurnExecutionPlan(
        execution=TurnExecutionSnapshot(
            request=request,
            mode_prompt="",
            narrative_style_id=None,
            narrative_style_name="",
            narrative_style_prompt="",
            policy=TurnExecutionPolicy.for_mode(mode),
        ),
        main_llm=SimpleNamespace(effective_provider_key="main"),
        rp_modules=SimpleNamespace(modules=()),
    )


def _lifecycle(session: SessionManager):  # noqa: ANN201
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=None,
    )
    return SimpleNamespace(
        session_id="s1",
        session_manager=session,
        resources=resources,
        rp_module_registry=None,
    )


class _StatusHook:
    def __init__(self) -> None:
        self.calls = 0
        self.error: BaseException | None = None

    async def run(self, **_kwargs):  # noqa: ANN201
        self.calls += 1
        if self.error is not None:
            raise self.error
        return None

    @staticmethod
    def outcome_state(_scratch, _result):  # noqa: ANN001, ANN205
        return StatusSubAgentPreflightOutcome.NONE


@pytest.mark.asyncio
async def test_context_gate_runs_before_provider_and_transaction() -> None:
    session = SessionManager(history_enabled=False)
    calls: list[str] = []

    class _Context:
        @staticmethod
        def enforce_window_threshold(*_args, **_kwargs) -> None:
            calls.append("gate")
            raise RuntimeError("context full")

    class _Model:
        @staticmethod
        def provider_for(*_args, **_kwargs):  # noqa: ANN205
            calls.append("provider")
            return object()

    factory = TurnRuntimeFactory(
        lifecycle=_lifecycle(session),
        context_service=_Context(),
        model_runtime=_Model(),
        status_preflight=_StatusHook(),
    )
    with pytest.raises(RuntimeError, match="context full"):
        await factory.create(_plan())

    assert calls == ["gate"]
    assert session.begin_turn() == 1
    session.end_turn(1)


@pytest.mark.asyncio
async def test_preflight_failure_discards_runtime_and_clears_active_turn() -> None:
    session = SessionManager(history_enabled=False)
    status = _StatusHook()
    status.error = RuntimeError("preflight failed")
    context = SimpleNamespace(enforce_window_threshold=lambda *_args, **_kwargs: None)
    async def provider_for(*_args, **_kwargs):  # noqa: ANN202
        return object()

    model = SimpleNamespace(provider_for=provider_for)
    factory = TurnRuntimeFactory(
        lifecycle=_lifecycle(session),
        context_service=context,
        model_runtime=model,
        status_preflight=status,
    )

    with pytest.raises(RuntimeError, match="preflight failed"):
        await factory.create(_plan())

    assert session.history == []
    assert session.begin_turn() == 1
    session.end_turn(1)


@pytest.mark.asyncio
async def test_ooc_runtime_skips_status_preflight() -> None:
    session = SessionManager(history_enabled=False)
    status = _StatusHook()

    async def provider_for(*_args, **_kwargs):  # noqa: ANN202
        return object()

    factory = TurnRuntimeFactory(
        lifecycle=_lifecycle(session),
        context_service=SimpleNamespace(
            enforce_window_threshold=lambda *_args, **_kwargs: None
        ),
        model_runtime=SimpleNamespace(provider_for=provider_for),
        status_preflight=status,
    )

    runtime = await factory.create(_plan(TurnMode.OOC))
    try:
        assert status.calls == 0
        assert runtime.scratch.message_scratch.mode == "ooc"
    finally:
        runtime.discard()
        runtime.close()
