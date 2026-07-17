"""Session-local operations used by the Agent Service derivation worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_core.agent.sub_agents.status_bootstrap import StatusBootstrapCoordinator
from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_data.models import SessionDerivationSeedResult
    from rpg_core.agent.context_service import AgentContextService
    from rpg_core.agent.lifecycle import AgentRuntimeLifecycle


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
    ) -> None:
        self._lifecycle = lifecycle
        self._context_service = context_service

    def materialize(self, job_id: str) -> "SessionDerivationSeedResult":
        """Create a target at this source mailbox's serialized boundary."""

        from rpg_data.services import get_data_service_gateway

        service = get_data_service_gateway().session_derivations
        job = service.get_job(job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        if job.source_session_id != self._lifecycle.session_id:
            raise SessionDerivationPreparationError(
                "DERIVATION_SOURCE_MISMATCH",
                "Derivation job does not belong to the source Agent mailbox",
            )
        service.set_stage(job_id, "copying")
        return service.seed_target_session(job_id)

    async def prepare_target(
        self,
        job_id: str,
    ) -> SessionDerivationPreparationResult:
        """Rebuild derived state/memory/summary before publishing the target."""

        from rpg_data.services import get_data_service_gateway

        gateway = get_data_service_gateway()
        service = gateway.session_derivations
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
        service.set_stage(job_id, "rebuilding_status")
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
        service.set_stage(job_id, "extracting_story_memory")
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
        service.set_stage(job_id, "summarizing")
        compression = await compressor.maybe_compress(
            self._lifecycle.session_manager,
            strict=True,
        )
        if compression.failed:
            raise SessionDerivationPreparationError(
                compression.error_code or "DERIVATION_SUMMARY_FAILED",
                compression.error_message or "Summary generation failed",
            )

        service.set_stage(job_id, "evaluating_context")
        usage = self._context_usage(await self._context_service.inspect_payload())
        if usage.used_tokens is not None and usage.context_limit is not None:
            service.set_context_usage(
                job_id,
                used_tokens=usage.used_tokens,
                context_limit=usage.context_limit,
                threshold_exceeded=usage.context_threshold_exceeded,
            )
        service.set_stage(job_id, "finalizing")
        return usage

    def _player_character_snapshot(self) -> TurnPlayerCharacterSnapshot | None:
        from rpg_data import models as data_models
        from rpg_data.services import get_data_service_gateway

        state = get_data_service_gateway().session_roles.get_state(
            self._lifecycle.session_id
        )
        if (
            state.status != data_models.PLAYER_CHARACTER_STATUS_BOUND
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
