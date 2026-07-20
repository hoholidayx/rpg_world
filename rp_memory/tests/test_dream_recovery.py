from __future__ import annotations

import pytest

from rp_memory.dream.recovery import DreamRecoveryAction, decide_orphan_recovery
from rp_memory.dream.types import (
    DreamDepth,
    DreamProposalStatus,
    DreamScope,
)


def test_generating_proposal_is_the_only_recoverable_orphan() -> None:
    decision = decide_orphan_recovery(
        status=DreamProposalStatus.GENERATING.value,
        depth=DreamDepth.DEEP.value,
        scope=DreamScope.FULL.value,
    )

    assert decision.action is DreamRecoveryAction.INTERRUPT_ORPHAN
    assert decision.depth is DreamDepth.DEEP
    assert decision.scope is DreamScope.FULL


@pytest.mark.parametrize(
    "status",
    tuple(
        item.value
        for item in DreamProposalStatus
        if item is not DreamProposalStatus.GENERATING
    ),
)
def test_terminal_or_ready_proposal_is_returned_without_replacement(
    status: str,
) -> None:
    decision = decide_orphan_recovery(
        status=status,
        depth=DreamDepth.SHALLOW.value,
        scope=DreamScope.INCREMENTAL.value,
    )

    assert decision.action is DreamRecoveryAction.RETURN_EXISTING


def test_recovery_rejects_unknown_persisted_state() -> None:
    with pytest.raises(ValueError):
        decide_orphan_recovery(
            status="unknown",
            depth=DreamDepth.SHALLOW.value,
            scope=DreamScope.INCREMENTAL.value,
        )
