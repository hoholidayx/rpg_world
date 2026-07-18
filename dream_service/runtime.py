"""Process-local asynchronous Dream generation lifecycle."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from dream_service.contracts import AsyncDreamRepository, DreamProposalView
from dream_service.notifications import (
    DreamTerminalNotification,
    DreamTerminalNotificationSink,
    NullDreamTerminalNotificationSink,
)
from rp_memory.dream.engine import DreamEngine
from rp_memory.dream.errors import DreamAlreadyRunningError, DreamError
from rp_memory.dream.types import DreamDepth, DreamScope

logger = logging.getLogger("dream_service.runtime")


@dataclass(frozen=True)
class _ActiveGeneration:
    proposal_id: str
    task: asyncio.Task[None]


@dataclass(frozen=True)
class _ProposalLookup:
    succeeded: bool
    proposal: DreamProposalView | None


class DreamTaskManager:
    def __init__(
        self,
        *,
        repository: AsyncDreamRepository,
        engine: DreamEngine,
        notification_sink: DreamTerminalNotificationSink | None = None,
        orphan_check_interval_seconds: float = 0.5,
        state_persist_attempts: int = 3,
        state_persist_retry_delay_seconds: float = 0.05,
    ) -> None:
        self.repository = repository
        self.engine = engine
        self._notifications = (
            notification_sink or NullDreamTerminalNotificationSink()
        )
        self._orphan_check_interval_seconds = max(
            0.01,
            float(orphan_check_interval_seconds),
        )
        self._state_persist_attempts = max(1, int(state_persist_attempts))
        self._state_persist_retry_delay_seconds = max(
            0.0,
            float(state_persist_retry_delay_seconds),
        )
        self._tasks_by_session: dict[str, _ActiveGeneration] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        interrupted = await self._interrupt_generating()
        if interrupted:
            logger.warning(
                "interrupted stale Dream proposals count=%s",
                len(interrupted),
            )

    async def stop(self) -> None:
        tasks = tuple(active.task for active in self._tasks_by_session.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks_by_session.clear()
        interrupted = await self._interrupt_generating()
        if interrupted:
            logger.warning(
                "interrupted Dream proposals during shutdown count=%s",
                len(interrupted),
            )

    async def create_proposal(
        self,
        session_id: str,
        *,
        depth: DreamDepth,
        scope: DreamScope,
        recover_proposal_id: str | None = None,
    ) -> DreamProposalView:
        async with self._lock:
            recovery = None
            if recover_proposal_id is not None:
                recovery_id = str(recover_proposal_id).strip()
                if not recovery_id:
                    raise ValueError("recover_proposal_id must not be empty")
                recovery = await self.repository.get_proposal(
                    session_id,
                    recovery_id,
                )
                if recovery is None:
                    raise FileNotFoundError(
                        f"Dream proposal not found: {recovery_id}"
                    )
                if recovery.status != "generating":
                    return recovery

            existing = self._tasks_by_session.get(session_id)
            if existing is not None and not existing.task.done():
                stored = await self.repository.get_proposal(
                    session_id,
                    existing.proposal_id,
                )
                if stored is not None and stored.status == "generating":
                    raise DreamAlreadyRunningError(
                        f"Session already has a generating Dream proposal: {session_id}"
                    )
                # `/clear`, Session deletion, or an external state transition
                # may remove/finish SQL state before this process-local LLM
                # task observes it.  Drain that orphan before accepting work.
                existing.task.cancel()
                await asyncio.gather(existing.task, return_exceptions=True)
                if self._tasks_by_session.get(session_id) is existing:
                    self._tasks_by_session.pop(session_id, None)
            elif existing is not None:
                self._tasks_by_session.pop(session_id, None)

            if recovery is not None:
                interrupted = await self._interrupt_generating(
                    session_id,
                    proposal_id=recovery.proposal_id,
                )
                recovered = await self.repository.get_proposal(
                    session_id,
                    recovery.proposal_id,
                )
                if recovered is None:
                    raise FileNotFoundError(
                        f"Dream proposal not found: {recovery.proposal_id}"
                    )
                if recovered.status == "generating":
                    raise DreamAlreadyRunningError(
                        "Dream proposal is still generating and could not be "
                        f"recovered: {recovery.proposal_id}"
                    )
                if recovered.status != "interrupted":
                    return recovered
                depth = DreamDepth(recovered.depth)
                scope = DreamScope(recovered.scope)
                logger.warning(
                    "recovering orphaned Dream proposal session_id=%s "
                    "proposal_id=%s interrupted=%s",
                    session_id,
                    recovered.proposal_id,
                    len(interrupted),
                )
            else:
                interrupted = await self._interrupt_generating(session_id)
                if interrupted:
                    logger.warning(
                        "interrupted orphaned Dream proposal before create "
                        "session_id=%s count=%s",
                        session_id,
                        len(interrupted),
                    )
            snapshot = await self.repository.build_source_snapshot(session_id)
            selection = self.engine.prepare(snapshot, depth=depth, scope=scope)
            proposal = await self.repository.create_proposal(selection)
            task = asyncio.create_task(
                self._generate(proposal, selection),
                name=f"dream-{session_id}-{proposal.proposal_id}",
            )
            active = _ActiveGeneration(proposal.proposal_id, task)
            self._tasks_by_session[session_id] = active
            task.add_done_callback(
                lambda completed, sid=session_id, pid=proposal.proposal_id: self._forget(
                    sid,
                    pid,
                    completed,
                )
            )
            return proposal

    async def _generate(self, proposal, selection) -> None:  # noqa: ANN001
        generation = asyncio.create_task(
            self.engine.generate(selection),
            name=f"dream-engine-{proposal.session_id}-{proposal.proposal_id}",
        )
        orphan_guard = asyncio.create_task(
            self._wait_until_proposal_inactive(
                proposal.session_id,
                proposal.proposal_id,
            ),
            name=f"dream-guard-{proposal.session_id}-{proposal.proposal_id}",
        )
        try:
            completed, _pending = await asyncio.wait(
                {generation, orphan_guard},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if orphan_guard in completed:
                generation.cancel()
                await asyncio.gather(generation, return_exceptions=True)
                logger.info(
                    "cancelled orphaned Dream generation proposal_id=%s session_id=%s",
                    proposal.proposal_id,
                    proposal.session_id,
                )
                return
            orphan_guard.cancel()
            await asyncio.gather(orphan_guard, return_exceptions=True)
            result = generation.result()
            await self._persist_ready(proposal, result.items)
        except asyncio.CancelledError:
            generation.cancel()
            orphan_guard.cancel()
            await asyncio.gather(
                generation,
                orphan_guard,
                return_exceptions=True,
            )
            raise
        except Exception as exc:
            logger.exception(
                "Dream generation failed proposal_id=%s session_id=%s",
                proposal.proposal_id,
                proposal.session_id,
            )
            try:
                await self._persist_failed(
                    proposal,
                    error_code=(
                        "DREAM_MODEL_CONTRACT_ERROR"
                        if isinstance(exc, DreamError)
                        else "DREAM_GENERATION_FAILED"
                    ),
                    error_message=str(exc),
                )
            except Exception:
                logger.exception(
                    "failed to persist Dream generation error proposal_id=%s",
                    proposal.proposal_id,
                )
                await self._interrupt_after_terminal_persist_failure(proposal)
        finally:
            generation.cancel()
            orphan_guard.cancel()
            await asyncio.gather(
                generation,
                orphan_guard,
                return_exceptions=True,
            )

    async def _wait_until_proposal_inactive(
        self,
        session_id: str,
        proposal_id: str,
    ) -> None:
        while True:
            await asyncio.sleep(self._orphan_check_interval_seconds)
            try:
                stored = await self.repository.get_proposal(session_id, proposal_id)
            except Exception:
                logger.warning(
                    "failed to inspect Dream proposal while guarding generation "
                    "proposal_id=%s session_id=%s",
                    proposal_id,
                    session_id,
                    exc_info=True,
                )
                continue
            if stored is None or stored.status != "generating":
                return

    async def _persist_ready(self, proposal, items) -> None:  # noqa: ANN001
        last_error: Exception | None = None
        for attempt in range(1, self._state_persist_attempts + 1):
            try:
                stored = await self.repository.set_proposal_ready(
                    proposal.proposal_id,
                    items,
                )
                await self._publish_terminal(stored)
                return
            except Exception as exc:
                last_error = exc
                lookup = await self._get_proposal_after_persist_error(proposal)
                stored = lookup.proposal
                if lookup.succeeded and (
                    stored is None or stored.status != "generating"
                ):
                    if stored is not None and stored.status == "ready":
                        await self._publish_terminal(stored)
                        return
                    raise
                if attempt < self._state_persist_attempts:
                    await asyncio.sleep(self._state_persist_retry_delay_seconds)
        assert last_error is not None
        raise last_error

    async def _persist_failed(
        self,
        proposal,
        *,
        error_code: str,
        error_message: str,
    ) -> None:  # noqa: ANN001
        last_error: Exception | None = None
        for attempt in range(1, self._state_persist_attempts + 1):
            try:
                stored = await self.repository.set_proposal_failed(
                    proposal.proposal_id,
                    error_code=error_code,
                    error_message=error_message,
                )
                await self._publish_terminal(stored)
                return
            except Exception as exc:
                last_error = exc
                lookup = await self._get_proposal_after_persist_error(proposal)
                stored = lookup.proposal
                if lookup.succeeded and (
                    stored is None or stored.status != "generating"
                ):
                    if stored is not None and stored.status == "failed":
                        await self._publish_terminal(stored)
                    return
                if attempt < self._state_persist_attempts:
                    await asyncio.sleep(self._state_persist_retry_delay_seconds)
        assert last_error is not None
        raise last_error

    async def _get_proposal_after_persist_error(
        self,
        proposal,
    ) -> _ProposalLookup:  # noqa: ANN001
        try:
            return _ProposalLookup(
                succeeded=True,
                proposal=await self.repository.get_proposal(
                    proposal.session_id,
                    proposal.proposal_id,
                ),
            )
        except Exception:
            logger.warning(
                "failed to inspect Dream proposal after persistence error "
                "proposal_id=%s session_id=%s",
                proposal.proposal_id,
                proposal.session_id,
                exc_info=True,
            )
            return _ProposalLookup(succeeded=False, proposal=None)

    async def _interrupt_after_terminal_persist_failure(
        self,
        proposal,
    ) -> None:  # noqa: ANN001
        """Best-effort release of a SQL ``generating`` row after terminal writes fail."""
        try:
            interrupted = await self._interrupt_generating(
                proposal.session_id,
                proposal_id=proposal.proposal_id,
            )
        except Exception:
            logger.exception(
                "failed to interrupt Dream proposal after terminal persistence "
                "failure proposal_id=%s session_id=%s",
                proposal.proposal_id,
                proposal.session_id,
            )
            return
        if interrupted:
            logger.warning(
                "interrupted Dream proposal after terminal persistence failure "
                "proposal_id=%s session_id=%s count=%s",
                proposal.proposal_id,
                proposal.session_id,
                len(interrupted),
            )

    async def _interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[DreamProposalView, ...]:
        proposals = await self.repository.interrupt_generating(
            session_id,
            proposal_id=proposal_id,
        )
        for proposal in proposals:
            await self._publish_terminal(proposal)
        return proposals

    async def _publish_terminal(self, proposal: DreamProposalView) -> None:
        try:
            await self._notifications.publish(
                DreamTerminalNotification(
                    proposal_id=proposal.proposal_id,
                    session_id=proposal.session_id,
                    depth=proposal.depth,
                    scope=proposal.scope,
                    status=proposal.status,
                    error_code=proposal.error_code,
                    error_message=proposal.error_message,
                    finished_at=proposal.finished_at,
                    updated_at=proposal.updated_at,
                )
            )
        except Exception:
            logger.warning(
                "Dream terminal notification failed proposal_id=%s session_id=%s",
                proposal.proposal_id,
                proposal.session_id,
                exc_info=True,
            )

    def _forget(
        self,
        session_id: str,
        proposal_id: str,
        completed: asyncio.Task[None],
    ) -> None:
        active = self._tasks_by_session.get(session_id)
        if (
            active is not None
            and active.proposal_id == proposal_id
            and active.task is completed
        ):
            self._tasks_by_session.pop(session_id, None)
