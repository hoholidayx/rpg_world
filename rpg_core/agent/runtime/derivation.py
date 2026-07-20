"""Session-local operations used by the Agent Service derivation worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from rpg_core.agent.sub_agents.status.bootstrap import StatusBootstrapCoordinator
from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot
from rpg_core.session.derivation import (
    SessionDerivationSeedResult,
    SessionDerivationStage,
)
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionPlayerCharacterState,
)
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_core.agent.runtime.context import AgentContextService
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_data.model.session import SessionDerivationJob


class DerivationRuntimeApplication(Protocol):
    def get_job(self, job_id: str) -> "SessionDerivationJob | None": ...

    def set_stage(
        self,
        job_id: str,
        stage: SessionDerivationStage,
    ) -> "SessionDerivationJob": ...

    def materialize_target(self, job_id: str) -> SessionDerivationSeedResult: ...

    def set_context_usage(
        self,
        job_id: str,
        *,
        used_tokens: int,
        context_limit: int,
        threshold_exceeded: bool,
    ) -> "SessionDerivationJob": ...


class SessionRoleReader(Protocol):
    def get_state(self, session_id: str) -> SessionPlayerCharacterState: ...


class SessionDerivationPreparationError(RuntimeError):
    """Typed failure propagated to the persistent derivation job."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SessionDerivationPreparationResult:
    used_tokens: int | None = None
    context_limit: int | None = None
    context_threshold_exceeded: bool = False


class AgentDerivationService:
    """Own derivation materialization and target-runtime preparation."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        context_service: "AgentContextService",
        derivation_service: DerivationRuntimeApplication,
        role_service: SessionRoleReader,
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service
        self._derivation_service = derivation_service
        self._role_service = role_service

    def materialize(self, job_id: str) -> "SessionDerivationSeedResult":
        """Create a target at this source mailbox's serialized boundary."""

        service = self._get_derivation_service()
        job = service.get_job(job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        if job.source_session_id != self._lifecycle.session_id:
            raise SessionDerivationPreparationError(
                "DERIVATION_SOURCE_MISMATCH",
                "Derivation job does not belong to the source Agent mailbox",
            )
        service.set_stage(job_id, SessionDerivationStage.COPYING)
        return service.materialize_target(job_id)

    async def prepare_target(
        self,
        job_id: str,
    ) -> SessionDerivationPreparationResult:
        """Rebuild derived state/memory/summary before publishing the target."""

        service = self._get_derivation_service()
        job = service.get_job(job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        if job.target_session_id != self._lifecycle.session_id:
            raise SessionDerivationPreparationError(
                "DERIVATION_TARGET_MISMATCH",
                "Derivation job does not belong to the target Agent runtime",
            )

        status_sub_agent = self._lifecycle.status_sub_agent
        status_manager = self._lifecycle.resources.status_manager
        if status_sub_agent is None or status_manager is None:
            raise SessionDerivationPreparationError(
                "DERIVATION_STATUS_UNAVAILABLE",
                "Status bootstrap collaborators are unavailable",
            )
        service.set_stage(job_id, SessionDerivationStage.REBUILDING_STATUS)
        bootstrap = await StatusBootstrapCoordinator(status_sub_agent).run(
            history=self._lifecycle.session_manager.history,
            boundary_turn_id=job.branch_turn_id,
            status_manager=status_manager,
            scene_tracker=self._lifecycle.resources.scene_tracker,
            player_character=self._player_character_snapshot(),
        )
        if bootstrap.failed:
            raise SessionDerivationPreparationError(
                "DERIVATION_STATUS_BOOTSTRAP_FAILED",
                "Unable to rebuild status tables from the branch history window",
            )

        memory_sub_agent = self._lifecycle.memory_sub_agent
        if memory_sub_agent is None:
            raise SessionDerivationPreparationError(
                "DERIVATION_STORY_MEMORY_UNAVAILABLE",
                "Story Memory extraction is unavailable",
            )
        service.set_stage(job_id, SessionDerivationStage.EXTRACTING_STORY_MEMORY)
        extraction = await memory_sub_agent.extract_pending_story_memory(
            self._lifecycle.session_manager,
            strict=True,
        )
        if extraction.failed:
            raise SessionDerivationPreparationError(
                extraction.error_code or "DERIVATION_STORY_MEMORY_FAILED",
                extraction.error_message or "Story Memory extraction failed",
            )

        compressor = self._lifecycle.compressor
        if compressor is None:
            raise SessionDerivationPreparationError(
                "DERIVATION_SUMMARY_UNAVAILABLE",
                "Summary compressor is unavailable",
            )
        service.set_stage(job_id, SessionDerivationStage.SUMMARIZING)
        compression = await compressor.maybe_compress(
            self._lifecycle.session_manager,
            strict=True,
        )
        if compression.failed:
            raise SessionDerivationPreparationError(
                compression.error_code or "DERIVATION_SUMMARY_FAILED",
                compression.error_message or "Summary generation failed",
            )

        service.set_stage(job_id, SessionDerivationStage.EVALUATING_CONTEXT)
        usage = self._context_usage(await self._context_service.inspect_payload())
        if usage.used_tokens is not None and usage.context_limit is not None:
            service.set_context_usage(
                job_id,
                used_tokens=usage.used_tokens,
                context_limit=usage.context_limit,
                threshold_exceeded=usage.context_threshold_exceeded,
            )
        service.set_stage(job_id, SessionDerivationStage.FINALIZING)
        return usage

    def _player_character_snapshot(self) -> TurnPlayerCharacterSnapshot | None:
        state = self._get_role_service().get_state(self._lifecycle.session_id)
        if (
            state.status is not PlayerCharacterBindingStatus.BOUND
            or state.player is None
        ):
            return None
        player = state.player
        return TurnPlayerCharacterSnapshot(
            character_id=int(player.character_id),
            mount_id=int(player.mount_id),
            story_id=int(player.story_id),
            name=str(player.name),
        )

    def _get_derivation_service(self) -> DerivationRuntimeApplication:
        return self._derivation_service

    def _get_role_service(self) -> SessionRoleReader:
        return self._role_service

    @staticmethod
    def _context_usage(payload: dict[str, object]) -> SessionDerivationPreparationResult:
        raw = payload.get("usageEstimate")
        if not isinstance(raw, dict):
            return SessionDerivationPreparationResult()
        used = raw.get("usedTokens")
        limit = raw.get("contextLimit")
        if (
            isinstance(used, bool)
            or not isinstance(used, int)
            or used < 0
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
        ):
            return SessionDerivationPreparationResult()
        return SessionDerivationPreparationResult(
            used_tokens=used,
            context_limit=limit,
            context_threshold_exceeded=(
                used / limit >= settings.context_window_reject_threshold_ratio
            ),
        )
