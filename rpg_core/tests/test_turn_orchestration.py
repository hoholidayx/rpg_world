from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
from rpg_core.agent.sub_agents import StatusSubAgentPreflightOutcome
from rpg_core.agent.turn.models import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnMode,
    TurnRequest,
)
from rpg_core.agent.turn.orchestrator import TurnOrchestrator
from rpg_core.agent.turn.resolver import TurnSnapshotResolver
from rpg_core.agent.turn.runtime import TurnRuntime
from rpg_core.context.rpg_context import Message, Role
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
    gateway = SimpleNamespace(
        catalog=_Catalog(None),
        session_composer=_Composer(),
    )

    with pytest.raises(FileNotFoundError, match="resolving narrative style"):
        TurnSnapshotResolver("missing", gateway=gateway).resolve(
            TurnRequest.create("行动", narrative_style_id=3)
        )


class _TurnHost:
    def __init__(self) -> None:
        self._session_id = "s_turn"
        self._session = SessionManager(history_enabled=False)
        self._status_mgr = None
        self._scene_tracker = None
        self._rp_module_registry = None
        self._memory_manager = None
        self._last_tool_records = None
        self.post_commit_calls = 0
        self.diagnostic_calls = 0

    @staticmethod
    def _resolve_turn_execution_snapshot(request: TurnRequest) -> TurnExecutionSnapshot:
        return TurnExecutionSnapshot(
            request=request,
            mode_prompt="",
            narrative_style_id=None,
            narrative_style_name="",
            narrative_style_prompt="",
            policy=TurnExecutionPolicy.for_mode(request.mode),
        )

    @staticmethod
    def _resolve_main_llm_selection():  # noqa: ANN205
        return SimpleNamespace(effective_provider_key="fake")

    @staticmethod
    def _resolve_rp_module_snapshot():  # noqa: ANN205
        return SimpleNamespace(modules=())

    @staticmethod
    def _enforce_main_context_window_threshold(_selection, **_kwargs) -> None:  # noqa: ANN001
        return None

    @staticmethod
    def _refresh_main_provider(*, selection):  # noqa: ANN001, ANN205
        del selection
        return object()

    @staticmethod
    def _compose_stored_user_input(_scene_ctx: str | None, user_input: str) -> str:
        return user_input

    @staticmethod
    def _build_transformed_context(*, current_user_message: Message, **_kwargs) -> list[Message]:
        return [current_user_message]

    @staticmethod
    def _tool_registry_for_turn(*_args, **_kwargs):  # noqa: ANN205
        return None

    @staticmethod
    def _main_tool_schemas(_registry, **_kwargs):  # noqa: ANN001, ANN205
        return None

    @staticmethod
    async def _run_status_preflight(**_kwargs):  # noqa: ANN205
        return None

    @staticmethod
    def _preflight_outcome_state(*_args):  # noqa: ANN205
        return StatusSubAgentPreflightOutcome.NONE

    def _log_turn_preflight_diagnostics(self, **_kwargs) -> None:
        self.diagnostic_calls += 1

    @staticmethod
    def _tool_names_from_records(_records) -> list[str]:  # noqa: ANN001
        return []

    async def _run_post_commit_side_effects(self) -> None:
        self.post_commit_calls += 1


@pytest.mark.asyncio
async def test_sync_orchestrator_commits_protocol_neutral_result() -> None:
    host = _TurnHost()

    async def sync_runner(**kwargs):  # noqa: ANN003, ANN202
        assert kwargs["messages"][-1].content == "前进"
        return "完成", []

    async def unused_stream(**_kwargs):  # noqa: ANN202
        if False:
            yield None

    result = await TurnOrchestrator(
        host,
        sync_runner=sync_runner,
        stream_runner=unused_stream,
    ).execute_sync(TurnRequest.create("前进", mode="gm"))

    assert result.text == "完成"
    assert result.committed_turn_id == 1
    assert [(item.role, item.content, item.mode) for item in host._session.history] == [
        (Role.USER, "前进", "gm"),
        (Role.ASSISTANT, "完成", "gm"),
    ]
    assert host.post_commit_calls == 1
    assert host.diagnostic_calls == 1


@pytest.mark.asyncio
async def test_stream_orchestrator_buffers_done_until_commit() -> None:
    host = _TurnHost()
    emitted: list[AgentStreamEvent | str] = []

    async def unused_sync(**_kwargs):  # noqa: ANN202
        return "", []

    async def stream_runner(**_kwargs):  # noqa: ANN202
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="增量")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content="完整")

    async def emit_event(event: AgentStreamEvent) -> None:
        emitted.append(event)

    async def emit_error(error: BaseException) -> None:
        raise AssertionError(f"unexpected stream error: {error}")

    async def emit_end() -> None:
        emitted.append("end")

    result = await TurnOrchestrator(
        host,
        sync_runner=unused_sync,
        stream_runner=stream_runner,
    ).execute_stream(
        TurnRequest.create("观察"),
        emit_event=emit_event,
        emit_error=emit_error,
        emit_end=emit_end,
    )

    assert result is not None
    assert [item.kind for item in emitted if isinstance(item, AgentStreamEvent)] == [
        StreamEventKind.TEXT,
        StreamEventKind.DONE,
    ]
    done = emitted[-2]
    assert isinstance(done, AgentStreamEvent)
    assert done.committed_turn_id == 1
    assert emitted[-1] == "end"
    assert [item.content for item in host._session.history] == ["观察", "完整"]


@pytest.mark.asyncio
async def test_sync_orchestrator_discards_scratch_on_runner_failure() -> None:
    host = _TurnHost()

    async def failing_sync(**_kwargs):  # noqa: ANN202
        raise RuntimeError("provider failed")

    async def unused_stream(**_kwargs):  # noqa: ANN202
        if False:
            yield None

    with pytest.raises(RuntimeError, match="provider failed"):
        await TurnOrchestrator(
            host,
            sync_runner=failing_sync,
            stream_runner=unused_stream,
        ).execute_sync(TurnRequest.create("失败行动"))

    assert host._session.history == []
    assert host._session.begin_turn() == 1
    host._session.end_turn(1)
    assert host.post_commit_calls == 0


def test_turn_runtime_closes_transaction_when_module_close_fails() -> None:
    class FailingModuleRuntime:
        @staticmethod
        def close() -> None:
            raise RuntimeError("module close failed")

    transaction = SimpleNamespace(close_calls=0)

    def close_transaction() -> None:
        transaction.close_calls += 1

    transaction.close = close_transaction
    runtime = TurnRuntime(
        plan=SimpleNamespace(),  # type: ignore[arg-type]
        transaction=transaction,  # type: ignore[arg-type]
        scratch=SimpleNamespace(),  # type: ignore[arg-type]
        stats=SimpleNamespace(),  # type: ignore[arg-type]
        provider=object(),  # type: ignore[arg-type]
        rp_module_runtime=FailingModuleRuntime(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="module close failed"):
        runtime.close()

    assert transaction.close_calls == 1
