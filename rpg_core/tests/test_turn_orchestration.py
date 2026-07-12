from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.sub_agents import StatusSubAgentPreflightOutcome
from rpg_core.agent.transaction import AgentTurnTransaction
from rpg_core.agent.turn.models import (
    PreparedTurn,
    TurnExecutionPlan,
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnMode,
    TurnRequest,
)
from rpg_core.agent.turn.orchestrator import TurnOrchestrator
from rpg_core.agent.turn.resolver import TurnSnapshotResolver
from rpg_core.agent.turn.runtime import TurnRuntime
from rpg_core.context.rpg_context import Role
from rpg_core.session import SessionManager


class _Catalog:
    def __init__(self, session) -> None:  # noqa: ANN001
        self._session = session

    def get_session(self, _session_id: str):  # noqa: ANN201
        return self._session


class _Composer:
    def __init__(self) -> None:
        self.style_calls: list[tuple[str, int | None]] = []

    @staticmethod
    def get_mode(_workspace_id: str, mode: str):  # noqa: ANN201
        return SimpleNamespace(prompt=f"mode:{mode}")

    def resolve_session_style(self, session_id: str, style_id: int | None):  # noqa: ANN201
        self.style_calls.append((session_id, style_id))
        return SimpleNamespace(narrative_style_id=7, name="简洁", prompt="style:brief")


def test_turn_snapshot_resolver_freezes_mode_and_style_selection() -> None:
    composer = _Composer()
    gateway = SimpleNamespace(
        catalog=_Catalog(SimpleNamespace(workspace_id="ws")),
        session_composer=composer,
    )
    request = TurnRequest.create("行动", mode="gm", narrative_style_id=7)

    snapshot = TurnSnapshotResolver("s1", gateway=gateway).resolve(request)

    assert snapshot.request is request
    assert snapshot.mode_prompt == "mode:gm"
    assert snapshot.narrative_style_id == 7
    assert snapshot.narrative_style_prompt == "style:brief"
    assert snapshot.policy == TurnExecutionPolicy.for_mode(TurnMode.GM)
    assert composer.style_calls == [("s1", 7)]


def test_ooc_snapshot_validates_but_suppresses_explicit_style() -> None:
    composer = _Composer()
    gateway = SimpleNamespace(
        catalog=_Catalog(SimpleNamespace(workspace_id="ws")),
        session_composer=composer,
    )
    snapshot = TurnSnapshotResolver("s1", gateway=gateway).resolve(
        TurnRequest.create("解释规则", mode="ooc", narrative_style_id=7)
    )

    assert snapshot.narrative_style_id == 7
    assert snapshot.narrative_style_prompt == ""
    assert snapshot.policy.run_status_preflight is False
    assert composer.style_calls == [("s1", 7)]


def test_explicit_style_requires_catalog_session() -> None:
    gateway = SimpleNamespace(catalog=_Catalog(None), session_composer=_Composer())

    with pytest.raises(FileNotFoundError, match="resolving narrative style"):
        TurnSnapshotResolver("missing", gateway=gateway).resolve(
            TurnRequest.create("行动", narrative_style_id=3)
        )


class _PlanResolver:
    @staticmethod
    def resolve(request: TurnRequest) -> TurnExecutionPlan:
        return TurnExecutionPlan(
            execution=TurnExecutionSnapshot(
                request=request,
                mode_prompt="",
                narrative_style_id=None,
                narrative_style_name="",
                narrative_style_prompt="",
                policy=TurnExecutionPolicy.for_mode(request.mode),
            ),
            main_llm=SimpleNamespace(effective_provider_key="fake"),
            rp_modules=SimpleNamespace(modules=()),
        )


class _RuntimeFactory:
    def __init__(self, session: SessionManager) -> None:
        self._session = session

    async def create(self, plan: TurnExecutionPlan) -> TurnRuntime:
        stats = TurnStats(started_at=time.monotonic())
        transaction = AgentTurnTransaction(
            session=self._session,
            status_mgr=None,
            scene_tracker=None,
        )
        runtime = TurnRuntime(
            plan=plan,
            transaction=transaction,
            scratch=transaction.begin(stats, mode=plan.request.mode),
            stats=stats,
            provider=object(),
        )
        runtime.preflight_outcome = StatusSubAgentPreflightOutcome.NONE
        return runtime


class _Preparation:
    @staticmethod
    def build(runtime: TurnRuntime) -> PreparedTurn:
        message = runtime.transaction.stage_user_message(runtime.plan.request.text)
        return PreparedTurn(messages=[message], tool_registry=None, schemas=None)


class _PostCommitHooks:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self) -> None:
        self.calls += 1


class _Diagnostics:
    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def tool_names(_records) -> list[str]:  # noqa: ANN001
        return []

    def log_preflight(self, **_kwargs) -> None:
        self.calls += 1


def _orchestrator(*, session, sync_runner, stream_runner):  # noqa: ANN001, ANN201
    post_commit = _PostCommitHooks()
    diagnostics = _Diagnostics()
    orchestrator = TurnOrchestrator(
        session_id=lambda: "s_turn",
        plan_resolver=_PlanResolver(),
        runtime_factory=_RuntimeFactory(session),
        preparation=_Preparation(),
        post_commit_hooks=post_commit,
        diagnostics=diagnostics,
        sync_runner=sync_runner,
        stream_runner=stream_runner,
    )
    return orchestrator, post_commit, diagnostics


@pytest.mark.asyncio
async def test_sync_orchestrator_commits_protocol_neutral_result() -> None:
    session = SessionManager(history_enabled=False)

    async def sync_runner(**kwargs):  # noqa: ANN003, ANN202
        assert kwargs["messages"][-1].content == "前进"
        return "完成", []

    async def unused_stream(**_kwargs):  # noqa: ANN202
        if False:
            yield None

    orchestrator, post_commit, diagnostics = _orchestrator(
        session=session,
        sync_runner=sync_runner,
        stream_runner=unused_stream,
    )
    result = await orchestrator.execute_sync(TurnRequest.create("前进", mode="gm"))

    assert result.text == "完成"
    assert result.committed_turn_id == 1
    assert [(item.role, item.content, item.mode) for item in session.history] == [
        (Role.USER, "前进", "gm"),
        (Role.ASSISTANT, "完成", "gm"),
    ]
    assert post_commit.calls == 1
    assert diagnostics.calls == 1


@pytest.mark.asyncio
async def test_stream_orchestrator_buffers_done_until_commit() -> None:
    session = SessionManager(history_enabled=False)
    emitted: list[AgentStreamEvent | str] = []

    async def unused_sync(**_kwargs):  # noqa: ANN202
        return "", []

    async def stream_runner(**_kwargs):  # noqa: ANN202
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="增量")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="完整")

    orchestrator, post_commit, _ = _orchestrator(
        session=session,
        sync_runner=unused_sync,
        stream_runner=stream_runner,
    )
    result = await orchestrator.execute_stream(
        TurnRequest.create("观察"),
        emit_event=lambda event: _append(emitted, event),
        emit_error=_unexpected_error,
        emit_end=lambda: _append(emitted, "end"),
    )

    assert result is not None
    assert [event.kind for event in emitted if isinstance(event, AgentStreamEvent)] == [
        StreamEventKind.TEXT,
        StreamEventKind.DONE,
    ]
    assert emitted[-1] == "end"
    assert session.history[-1].content == "完整"
    assert post_commit.calls == 1


@pytest.mark.asyncio
async def test_sync_orchestrator_discards_scratch_on_runner_failure() -> None:
    session = SessionManager(history_enabled=False)

    async def failing_sync(**_kwargs):  # noqa: ANN202
        raise RuntimeError("provider failed")

    async def unused_stream(**_kwargs):  # noqa: ANN202
        if False:
            yield None

    orchestrator, post_commit, _ = _orchestrator(
        session=session,
        sync_runner=failing_sync,
        stream_runner=unused_stream,
    )
    with pytest.raises(RuntimeError, match="provider failed"):
        await orchestrator.execute_sync(TurnRequest.create("失败行动"))

    assert session.history == []
    assert post_commit.calls == 0


async def _append(items: list, item) -> None:  # noqa: ANN001
    items.append(item)


async def _unexpected_error(error: BaseException) -> None:
    raise AssertionError(f"unexpected stream error: {error}")
