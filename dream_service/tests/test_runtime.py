from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from dream_service.contracts import DreamProposalView
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


class _Repository:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.ready: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.sequence = 0
        self.proposals: dict[str, DreamProposalView] = {}

    def interrupt_generating(self) -> int:
        self.interrupt_calls += 1
        return 1 if self.interrupt_calls == 1 else 0

    def build_source_snapshot(self, session_id: str):  # noqa: ANN202
        return type("Snapshot", (), {"session_id": session_id})()

    def create_proposal(self, selection):  # noqa: ANN001, ANN202
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

    def get_proposal(self, session_id: str, proposal_id: str):  # noqa: ANN202
        proposal = self.proposals.get(proposal_id)
        return proposal if proposal is not None and proposal.session_id == session_id else None

    def set_proposal_ready(self, proposal_id: str, items):  # noqa: ANN001, ANN202
        self.ready.append(proposal_id)

    def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ):  # noqa: ANN202
        self.failed.append((proposal_id, error_code))


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
    assert repository.interrupt_calls == 2


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
