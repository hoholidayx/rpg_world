"""Typed orphan-recovery decisions for process-local Dream tasks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rp_memory.dream.types import DreamDepth, DreamProposalStatus, DreamScope


class DreamRecoveryAction(StrEnum):
    RETURN_EXISTING = "return_existing"
    INTERRUPT_ORPHAN = "interrupt_orphan"


@dataclass(frozen=True)
class DreamRecoveryDecision:
    action: DreamRecoveryAction
    depth: DreamDepth
    scope: DreamScope


def decide_orphan_recovery(
    *,
    status: str,
    depth: str,
    scope: str,
) -> DreamRecoveryDecision:
    proposal_status = DreamProposalStatus(status)
    return DreamRecoveryDecision(
        action=(
            DreamRecoveryAction.INTERRUPT_ORPHAN
            if proposal_status is DreamProposalStatus.GENERATING
            else DreamRecoveryAction.RETURN_EXISTING
        ),
        depth=DreamDepth(depth),
        scope=DreamScope(scope),
    )
