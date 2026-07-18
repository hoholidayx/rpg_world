from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import pytest

from dream_service.contracts import DreamProposalView
from dream_service.notifications import DreamTerminalNotification
from dream_service.runtime import DreamTaskManager
from rp_memory.dream.errors import DreamAlreadyRunningError
from rp_memory.dream.types import (
    DreamDepth,
    DreamGenerationResult,
    DreamScope,
)


@dataclass(frozen=True)
class _Selection:
    snapshot: object
    depth: DreamDepth
    scope: DreamScope


class _NotificationSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.notifications: list[DreamTerminalNotification] = []

    async def publish(self, notification: DreamTerminalNotification) -> None:
        if self.fail:
            raise RuntimeError("notification unavailable")
        self.notifications.append(notification)


class _Repository:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.interrupt_sessions: list[str | None] = []
        self.interrupt_proposals: list[str | None] = []
        self.ready: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.sequence = 0
        self.proposals: dict[str, DreamProposalView] = {}

    async def interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[DreamProposalView, ...]:
        self.interrupt_calls += 1
        self.interrupt_sessions.append(session_id)
        self.interrupt_proposals.append(proposal_id)
        return ()

    async def build_source_snapshot(self, session_id: str):  # noqa: ANN202
        return type("Snapshot", (), {"session_id": session_id})()

    async def create_proposal(self, selection):  # noqa: ANN001, ANN202
        self.sequence += 1
        proposal = DreamProposalView(
            proposal_id=f"p{self.sequence}",
            session_id=selection.snapshot.session_id,
            depth=selection.depth.value,
            scope=selection.scope.value,
            status="generating",
            ledger_revision=0,
            items=(),
            error_code="",
            error_message="",
            created_at="",
            updated_at="",
            finished_at="",
        )
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    async def get_proposal(self, session_id: str, proposal_id: str):  # noqa: ANN202
        proposal = self.proposals.get(proposal_id)
        return proposal if proposal is not None and proposal.session_id == session_id else None

    async def set_proposal_ready(self, proposal_id: str, items):  # noqa: ANN001, ANN202
        self.ready.append(proposal_id)
        self.proposals[proposal_id] = replace(
            self.proposals[proposal_id],
            status="ready",
        )
        return self.proposals[proposal_id]

    async def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ):  # noqa: ANN202
        self.failed.append((proposal_id, error_code))
        self.proposals[proposal_id] = replace(
            self.proposals[proposal_id],
            status="failed",
            error_code=error_code,
            error_message=error_message,
        )
        return self.proposals[proposal_id]


class _BlockingEngine:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = 0

    def prepare(self, snapshot, *, depth, scope):  # noqa: ANN001, ANN202
        return _Selection(snapshot, depth, scope)

    async def generate(self, _selection) -> DreamGenerationResult:  # noqa: ANN001
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return DreamGenerationResult((), 0, 0)


async def test_task_manager_interrupts_startup_and_serializes_one_session() -> None:
    repository = _Repository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(repository=repository, engine=engine)  # type: ignore[arg-type]
    await manager.start()
    assert repository.interrupt_calls == 1

    created = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )
    await engine.started.wait()
    with pytest.raises(DreamAlreadyRunningError):
        await manager.create_proposal(
            "s1",
            depth=DreamDepth.DEEP,
            scope=DreamScope.FULL,
        )
    assert created.status == "generating"

    engine.release.set()
    for _ in range(10):
        if repository.ready:
            break
        await asyncio.sleep(0)
    assert repository.ready == [created.proposal_id]
    await manager.stop()
    assert repository.interrupt_calls == 3
    assert repository.interrupt_sessions == [None, "s1", None]
    assert repository.interrupt_proposals == [None, None, None]


class _FailingEngine(_BlockingEngine):
    async def generate(self, _selection) -> DreamGenerationResult:  # noqa: ANN001
        raise RuntimeError("provider failed")


async def test_task_manager_persists_generation_failure() -> None:
    repository = _Repository()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=_FailingEngine(),
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    for _ in range(10):
        if repository.failed:
            break
        await asyncio.sleep(0)
    assert repository.failed == [(proposal.proposal_id, "DREAM_GENERATION_FAILED")]
    await manager.stop()


async def test_task_manager_publishes_ready_and_isolates_sink_failure() -> None:
    repository = _Repository()
    engine = _BlockingEngine()
    notifications = _NotificationSink(fail=True)
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        notification_sink=notifications,
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()
    engine.release.set()
    for _ in range(20):
        if repository.proposals[proposal.proposal_id].status == "ready":
            break
        await asyncio.sleep(0)

    assert repository.proposals[proposal.proposal_id].status == "ready"
    await manager.stop()


async def test_task_manager_publishes_ready_and_failed_terminals() -> None:
    ready_repository = _Repository()
    ready_engine = _BlockingEngine()
    ready_notifications = _NotificationSink()
    ready_manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=ready_repository,
        engine=ready_engine,
        notification_sink=ready_notifications,
    )
    await ready_manager.start()
    ready = await ready_manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    await ready_engine.started.wait()
    ready_engine.release.set()
    for _ in range(20):
        if ready_notifications.notifications:
            break
        await asyncio.sleep(0)
    assert [
        (item.proposal_id, item.status)
        for item in ready_notifications.notifications
    ] == [(ready.proposal_id, "ready")]
    await ready_manager.stop()

    failed_repository = _Repository()
    failed_notifications = _NotificationSink()
    failed_manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=failed_repository,
        engine=_FailingEngine(),
        notification_sink=failed_notifications,
    )
    await failed_manager.start()
    failed = await failed_manager.create_proposal(
        "s2",
        depth=DreamDepth.DEEP,
        scope=DreamScope.INCREMENTAL,
    )
    for _ in range(20):
        if failed_notifications.notifications:
            break
        await asyncio.sleep(0)
    assert [
        (item.proposal_id, item.status)
        for item in failed_notifications.notifications
    ] == [(failed.proposal_id, "failed")]
    await failed_manager.stop()


async def test_task_manager_replaces_orphaned_task_after_clear_or_delete() -> None:
    repository = _Repository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(repository=repository, engine=engine)  # type: ignore[arg-type]
    await manager.start()
    first = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()

    # Simulate the public reset/delete data path removing SQL proposal state
    # while the process-local model call is still awaiting completion.
    repository.proposals.pop(first.proposal_id)
    second = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )
    assert second.proposal_id != first.proposal_id
    assert engine.cancelled == 1

    engine.release.set()
    for _ in range(10):
        if second.proposal_id in repository.ready:
            break
        await asyncio.sleep(0)
    assert repository.ready == [second.proposal_id]
    await manager.stop()


async def test_task_manager_cancels_orphan_without_waiting_for_next_create() -> None:
    repository = _Repository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        orphan_check_interval_seconds=0.01,
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()

    repository.proposals.pop(proposal.proposal_id)
    for _ in range(100):
        if engine.cancelled:
            break
        await asyncio.sleep(0.001)

    assert engine.cancelled == 1
    assert repository.ready == []
    await manager.stop()


class _TransientPersistenceRepository(_Repository):
    def __init__(
        self,
        *,
        ready_failures: int = 0,
        failed_failures: int = 0,
    ) -> None:
        super().__init__()
        self.ready_failures = ready_failures
        self.failed_failures = failed_failures
        self.ready_attempts = 0
        self.failed_attempts = 0

    async def set_proposal_ready(self, proposal_id: str, items):  # noqa: ANN001, ANN202
        self.ready_attempts += 1
        if self.ready_attempts <= self.ready_failures:
            raise RuntimeError("temporary ready write failure")
        return await super().set_proposal_ready(proposal_id, items)

    async def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ):  # noqa: ANN202
        self.failed_attempts += 1
        if self.failed_attempts <= self.failed_failures:
            raise RuntimeError("temporary failed write failure")
        return await super().set_proposal_failed(
            proposal_id,
            error_code=error_code,
            error_message=error_message,
        )


async def test_task_manager_retries_ready_state_persistence() -> None:
    repository = _TransientPersistenceRepository(ready_failures=2)
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        state_persist_retry_delay_seconds=0,
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()
    engine.release.set()
    for _ in range(30):
        if repository.ready:
            break
        await asyncio.sleep(0)

    assert repository.ready_attempts == 3
    assert repository.ready == [proposal.proposal_id]
    assert repository.proposals[proposal.proposal_id].status == "ready"
    await manager.stop()


async def test_task_manager_retries_failed_state_persistence() -> None:
    repository = _TransientPersistenceRepository(failed_failures=2)
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=_FailingEngine(),
        state_persist_retry_delay_seconds=0,
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    for _ in range(30):
        if repository.failed:
            break
        await asyncio.sleep(0)

    assert repository.failed_attempts == 3
    assert repository.failed == [(proposal.proposal_id, "DREAM_GENERATION_FAILED")]
    assert repository.proposals[proposal.proposal_id].status == "failed"
    await manager.stop()


class _OrphanCoordinatingRepository(_Repository):
    async def interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[DreamProposalView, ...]:
        self.interrupt_calls += 1
        self.interrupt_sessions.append(session_id)
        self.interrupt_proposals.append(proposal_id)
        interrupted: list[DreamProposalView] = []
        for stored_proposal_id, proposal in tuple(self.proposals.items()):
            if (
                proposal.status == "generating"
                and (session_id is None or proposal.session_id == session_id)
                and (
                    proposal_id is None
                    or stored_proposal_id == proposal_id
                )
            ):
                terminal = replace(
                    proposal,
                    status="interrupted",
                    error_code="DREAM_GENERATION_INTERRUPTED",
                )
                self.proposals[stored_proposal_id] = terminal
                interrupted.append(terminal)
        return tuple(interrupted)


async def test_create_interrupts_sql_orphan_without_local_task() -> None:
    repository = _OrphanCoordinatingRepository()
    repository.proposals["orphan"] = DreamProposalView(
        proposal_id="orphan",
        session_id="s1",
        depth="deep",
        scope="full",
        status="generating",
        ledger_revision=0,
        items=(),
        error_code="",
        error_message="",
        created_at="",
        updated_at="",
        finished_at="",
    )
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
    )

    created = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )

    assert repository.proposals["orphan"].status == "interrupted"
    assert created.proposal_id != "orphan"
    assert repository.interrupt_sessions == ["s1"]
    engine.release.set()
    await manager.stop()


async def test_startup_interruption_publishes_persisted_terminal_view() -> None:
    repository = _OrphanCoordinatingRepository()
    repository.proposals["orphan"] = DreamProposalView(
        proposal_id="orphan",
        session_id="s1",
        depth="deep",
        scope="full",
        status="generating",
        ledger_revision=0,
        items=(),
        error_code="",
        error_message="",
        created_at="",
        updated_at="",
        finished_at="",
    )
    notifications = _NotificationSink()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=_BlockingEngine(),
        notification_sink=notifications,
    )

    await manager.start()

    assert [item.status for item in notifications.notifications] == ["interrupted"]
    assert notifications.notifications[0].proposal_id == "orphan"
    await manager.stop()


async def test_shutdown_interruption_publishes_persisted_terminal_view() -> None:
    repository = _OrphanCoordinatingRepository()
    engine = _BlockingEngine()
    notifications = _NotificationSink()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        notification_sink=notifications,
    )
    await manager.start()
    proposal = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()

    await manager.stop()

    assert [
        (item.proposal_id, item.status)
        for item in notifications.notifications
    ] == [(proposal.proposal_id, "interrupted")]


class _UnwritableStateRepository(_OrphanCoordinatingRepository):
    def __init__(self) -> None:
        super().__init__()
        self.ready_attempts = 0
        self.failed_attempts = 0

    async def set_proposal_ready(self, proposal_id: str, items):  # noqa: ANN001, ANN202
        self.ready_attempts += 1
        raise RuntimeError("ready state unavailable")

    async def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ):  # noqa: ANN202
        self.failed_attempts += 1
        raise RuntimeError("failed state unavailable")


async def test_state_write_exhaustion_interrupts_orphan_without_next_create() -> None:
    repository = _UnwritableStateRepository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        state_persist_attempts=2,
        state_persist_retry_delay_seconds=0,
    )
    await manager.start()
    first = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()
    engine.release.set()
    for _ in range(50):
        if repository.proposals[first.proposal_id].status == "interrupted":
            break
        await asyncio.sleep(0)
    assert repository.ready_attempts == 2
    assert repository.failed_attempts == 2
    assert repository.proposals[first.proposal_id].status == "interrupted"
    assert repository.interrupt_sessions[-1] == "s1"
    assert repository.interrupt_proposals[-1] == first.proposal_id

    second = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )
    assert second.proposal_id != first.proposal_id
    engine.release.set()
    await manager.stop()


async def test_recovery_returns_terminal_proposal_without_duplicate_generation() -> None:
    repository = _OrphanCoordinatingRepository()
    repository.proposals["ready"] = DreamProposalView(
        proposal_id="ready",
        session_id="s1",
        depth="deep",
        scope="full",
        status="ready",
        ledger_revision=0,
        items=(),
        error_code="",
        error_message="",
        created_at="",
        updated_at="",
        finished_at="",
    )
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
    )

    recovered = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
        recover_proposal_id="ready",
    )

    assert recovered.proposal_id == "ready"
    assert repository.sequence == 0
    assert repository.interrupt_calls == 0
    assert engine.started.is_set() is False


async def test_recovery_conflicts_with_same_active_local_task() -> None:
    repository = _OrphanCoordinatingRepository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
    )
    await manager.start()
    active = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()

    with pytest.raises(DreamAlreadyRunningError):
        await manager.create_proposal(
            "s1",
            depth=DreamDepth.SHALLOW,
            scope=DreamScope.INCREMENTAL,
            recover_proposal_id=active.proposal_id,
        )

    assert active.proposal_id not in repository.interrupt_proposals
    assert repository.sequence == 1
    engine.release.set()
    await manager.stop()


async def test_concurrent_recovery_creates_at_most_one_replacement() -> None:
    repository = _OrphanCoordinatingRepository()
    repository.proposals["orphan"] = DreamProposalView(
        proposal_id="orphan",
        session_id="s1",
        depth="deep",
        scope="full",
        status="generating",
        ledger_revision=0,
        items=(),
        error_code="",
        error_message="",
        created_at="",
        updated_at="",
        finished_at="",
    )
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
    )

    recovered = await asyncio.gather(
        manager.create_proposal(
            "s1",
            depth=DreamDepth.SHALLOW,
            scope=DreamScope.INCREMENTAL,
            recover_proposal_id="orphan",
        ),
        manager.create_proposal(
            "s1",
            depth=DreamDepth.SHALLOW,
            scope=DreamScope.INCREMENTAL,
            recover_proposal_id="orphan",
        ),
    )

    replacements = [item for item in recovered if item.proposal_id != "orphan"]
    assert len(replacements) == 1
    assert replacements[0].depth == "deep"
    assert replacements[0].scope == "full"
    assert repository.sequence == 1
    assert repository.proposals["orphan"].status == "interrupted"
    engine.release.set()
    await manager.stop()


class _FallbackInterruptFailureRepository(_UnwritableStateRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failed_targeted_interrupts = 0

    async def interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[DreamProposalView, ...]:
        if proposal_id is not None and self.failed_targeted_interrupts == 0:
            self.failed_targeted_interrupts += 1
            raise RuntimeError("interrupt state unavailable")
        return await super().interrupt_generating(
            session_id,
            proposal_id=proposal_id,
        )


async def test_recovery_coordinates_orphan_when_terminal_fallback_also_fails() -> None:
    repository = _FallbackInterruptFailureRepository()
    engine = _BlockingEngine()
    manager = DreamTaskManager(  # type: ignore[arg-type]
        repository=repository,
        engine=engine,
        state_persist_attempts=1,
        state_persist_retry_delay_seconds=0,
    )
    await manager.start()
    first = await manager.create_proposal(
        "s1",
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    await engine.started.wait()
    engine.release.set()
    for _ in range(50):
        if repository.failed_targeted_interrupts:
            break
        await asyncio.sleep(0)
    for _ in range(3):
        await asyncio.sleep(0)

    assert repository.proposals[first.proposal_id].status == "generating"
    second = await manager.create_proposal(
        "s1",
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
        recover_proposal_id=first.proposal_id,
    )

    assert repository.proposals[first.proposal_id].status == "interrupted"
    assert second.proposal_id != first.proposal_id
    assert second.depth == "deep"
    assert second.scope == "full"
    await manager.stop()
