from __future__ import annotations

from types import SimpleNamespace

import pytest

from commons.errors import MessageModeUnavailableError
from rpg_core.agent.turn.models import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnRequest,
)
from rpg_core.agent.turn.planning import TurnPlanResolver
from rpg_core.rp_modules.models import RPModuleSelectionSnapshot


class _Context:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.snapshot = RPModuleSelectionSnapshot(
            session_id="s1",
            story_id=1,
            global_enabled=False,
            modules=(),
        )

    def resolve_rp_module_snapshot(self) -> RPModuleSelectionSnapshot:
        self.calls.append("rp_modules")
        return self.snapshot

    def resolve_turn_execution(
        self,
        request: TurnRequest,
        *,
        require_player_character: bool,
    ) -> TurnExecutionSnapshot:
        assert require_player_character is True
        self.calls.append("execution")
        return TurnExecutionSnapshot(
            request=request,
            narrative_style_id=None,
            narrative_style_name="",
            narrative_style_prompt="",
            policy=TurnExecutionPolicy.for_mode(request.mode),
        )

    async def load_persistent_memory_snapshot(self) -> tuple:
        self.calls.append("persistent_memory")
        return ()

    async def load_story_memory_snapshot(self) -> tuple:
        self.calls.append("story_memory")
        return ()

    def build_adjudication_context_snapshot(self, **_kwargs):  # noqa: ANN003, ANN201
        self.calls.append("adjudication")
        return SimpleNamespace(messages=())


class _Model:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def resolve(self, _session_id: str):  # noqa: ANN201
        self._calls.append("model")
        return SimpleNamespace(effective_provider_key="main")


class _Plot:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def resolve(self, _session_id: str, _snapshot):  # noqa: ANN001, ANN201
        self._calls.append("plot")
        return SimpleNamespace(enabled=False)


def _resolver(context: _Context) -> TurnPlanResolver:
    return TurnPlanResolver(
        lifecycle=SimpleNamespace(session_id="s1"),
        context_service=context,
        model_runtime=_Model(context.calls),
        plot_schedule_resolver=_Plot(context.calls),
    )


@pytest.mark.asyncio
async def test_guided_mode_is_rejected_before_execution_model_or_scratch_work() -> None:
    context = _Context()

    with pytest.raises(MessageModeUnavailableError):
        await _resolver(context).resolve(TurnRequest.create("托管", mode="gm"))

    assert context.calls == ["rp_modules"]


@pytest.mark.asyncio
async def test_neutral_plan_resolves_when_message_mode_module_is_unavailable() -> None:
    context = _Context()

    plan = await _resolver(context).resolve(TurnRequest.create("继续"))

    assert plan.request.mode.value == "neutral"
    assert context.calls == [
        "rp_modules",
        "execution",
        "model",
        "persistent_memory",
        "story_memory",
        "plot",
        "adjudication",
    ]
