from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

import rpg_core.agent.runtime.derivation as derivation_module
from rpg_core.agent.runtime.derivation import (
    AgentDerivationService,
    SessionDerivationPreparationError,
)
from rpg_core.session.derivation import SessionDerivationStage
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionPlayerCharacterState,
)
from rpg_core.settings import settings


class _DerivationDataService:
    def __init__(self, job: object, order: list[str]) -> None:
        self.job = job
        self.order = order
        self.materialize_calls: list[str] = []
        self.context_usage: dict[str, object] | None = None

    def get_job(self, job_id: str):  # noqa: ANN201
        assert job_id == "job-1"
        return self.job

    def set_stage(self, job_id: str, stage: SessionDerivationStage) -> None:
        assert job_id == "job-1"
        self.order.append(f"stage:{stage.value}")

    def materialize_target(self, job_id: str):  # noqa: ANN201
        self.materialize_calls.append(job_id)
        return SimpleNamespace(session=SimpleNamespace(id="target-session"))

    def set_context_usage(self, job_id: str, **usage: object) -> None:
        assert job_id == "job-1"
        self.order.append("context-usage")
        self.context_usage = usage


class _ContextService:
    def __init__(self, order: list[str], payload: dict[str, object]) -> None:
        self.order = order
        self.payload = payload

    async def inspect_payload(self) -> dict[str, object]:
        self.order.append("context")
        return self.payload


class _StatusBootstrap:
    failed = False

    def __init__(self, _status_sub_agent: object, order: list[str]) -> None:
        self.order = order

    async def run(self, **_kwargs: object):  # noqa: ANN201
        self.order.append("status")
        return SimpleNamespace(failed=self.failed)


class _MemorySubAgent:
    def __init__(self, order: list[str], *, failed: bool = False) -> None:
        self.order = order
        self.failed = failed

    async def extract_pending_story_memory(
        self,
        _session_manager: object,
        *,
        strict: bool,
    ):  # noqa: ANN201
        assert strict is True
        self.order.append("story")
        return SimpleNamespace(
            failed=self.failed,
            error_code=None,
            error_message=None,
        )


class _Compressor:
    def __init__(self, order: list[str], *, failed: bool = False) -> None:
        self.order = order
        self.failed = failed

    async def maybe_compress(
        self,
        _session_manager: object,
        *,
        strict: bool,
    ):  # noqa: ANN201
        assert strict is True
        self.order.append("summary")
        return SimpleNamespace(
            failed=self.failed,
            error_code=None,
            error_message=None,
        )


def _build_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_session_id: str = "source-session",
    target_session_id: str = "target-session",
    status_failed: bool = False,
    story_failed: bool = False,
    summary_failed: bool = False,
    payload: dict[str, object] | None = None,
) -> tuple[AgentDerivationService, _DerivationDataService, list[str]]:
    order: list[str] = []
    job = SimpleNamespace(
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        branch_turn_id=7,
    )
    data_service = _DerivationDataService(job, order)
    role_service = SimpleNamespace(
        get_state=lambda _session_id: SessionPlayerCharacterState(
            status=PlayerCharacterBindingStatus.INVALID,
        )
    )

    class Bootstrap(_StatusBootstrap):
        failed = status_failed

        def __init__(self, status_sub_agent: object) -> None:
            super().__init__(status_sub_agent, order)

    monkeypatch.setattr(derivation_module, "StatusBootstrapCoordinator", Bootstrap)
    lifecycle = SimpleNamespace(
        session_id="target-session",
        status_sub_agent=object(),
        memory_sub_agent=_MemorySubAgent(order, failed=story_failed),
        compressor=_Compressor(order, failed=summary_failed),
        session_manager=SimpleNamespace(history=[]),
        resources=SimpleNamespace(
            status_manager=object(),
            scene_tracker=None,
        ),
    )
    context = _ContextService(order, payload or {})
    return (
        AgentDerivationService(
            lifecycle=lifecycle,
            context_service=context,
            derivation_service=data_service,
            role_service=role_service,
        ),
        data_service,
        order,
    )


def test_materialize_rejects_job_for_another_source_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, data_service, order = _build_service(
        monkeypatch,
        source_session_id="another-source",
    )
    service._lifecycle.session_id = "source-session"

    with pytest.raises(SessionDerivationPreparationError) as caught:
        service.materialize("job-1")

    assert caught.value.code == "DERIVATION_SOURCE_MISMATCH"
    assert data_service.materialize_calls == []
    assert order == []


def test_materialize_delegates_to_core_derivation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, data_service, order = _build_service(monkeypatch)
    service._lifecycle.session_id = "source-session"

    result = service.materialize("job-1")

    assert result.session.id == "target-session"
    assert data_service.materialize_calls == ["job-1"]
    assert order == ["stage:copying"]


@pytest.mark.asyncio
async def test_prepare_rejects_job_for_another_target_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _data_service, order = _build_service(
        monkeypatch,
        target_session_id="another-target",
    )

    with pytest.raises(SessionDerivationPreparationError) as caught:
        await service.prepare_target("job-1")

    assert caught.value.code == "DERIVATION_TARGET_MISMATCH"
    assert order == []


@pytest.mark.asyncio
async def test_prepare_runs_status_story_summary_and_context_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, data_service, order = _build_service(
        monkeypatch,
        payload={
            "usageEstimate": {
                "usedTokens": 40,
                "contextLimit": 100,
            }
        },
    )

    result = await service.prepare_target("job-1")

    assert result.used_tokens == 40
    assert result.context_limit == 100
    assert result.context_threshold_exceeded is False
    assert data_service.context_usage == {
        "used_tokens": 40,
        "context_limit": 100,
        "threshold_exceeded": False,
    }
    assert order == [
        "stage:rebuilding_status",
        "status",
        "stage:extracting_story_memory",
        "story",
        "stage:summarizing",
        "summary",
        "stage:evaluating_context",
        "context",
        "context-usage",
        "stage:finalizing",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failed_stage", "expected_code", "expected_order"),
    [
        (
            "status",
            "DERIVATION_STATUS_BOOTSTRAP_FAILED",
            ["stage:rebuilding_status", "status"],
        ),
        (
            "story",
            "DERIVATION_STORY_MEMORY_FAILED",
            [
                "stage:rebuilding_status",
                "status",
                "stage:extracting_story_memory",
                "story",
            ],
        ),
        (
            "summary",
            "DERIVATION_SUMMARY_FAILED",
            [
                "stage:rebuilding_status",
                "status",
                "stage:extracting_story_memory",
                "story",
                "stage:summarizing",
                "summary",
            ],
        ),
    ],
)
async def test_prepare_maps_stage_failures_and_stops_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
    expected_code: str,
    expected_order: list[str],
) -> None:
    service, _data_service, order = _build_service(
        monkeypatch,
        status_failed=failed_stage == "status",
        story_failed=failed_stage == "story",
        summary_failed=failed_stage == "summary",
    )

    with pytest.raises(SessionDerivationPreparationError) as caught:
        await service.prepare_target("job-1")

    assert caught.value.code == expected_code
    assert order == expected_order


@pytest.mark.asyncio
async def test_context_threshold_is_reported_as_warning_not_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_limit = 10_000
    used_tokens = math.ceil(
        context_limit * settings.context_window_reject_threshold_ratio
    )
    service, data_service, order = _build_service(
        monkeypatch,
        payload={
            "usageEstimate": {
                "usedTokens": used_tokens,
                "contextLimit": context_limit,
            }
        },
    )

    result = await service.prepare_target("job-1")

    assert result.context_threshold_exceeded is True
    assert data_service.context_usage == {
        "used_tokens": used_tokens,
        "context_limit": context_limit,
        "threshold_exceeded": True,
    }
    assert order[-1] == "stage:finalizing"
