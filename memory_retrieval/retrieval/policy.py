"""Injectable candidate policy boundary for business-neutral retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class CandidatePolicy(Protocol):
    """Application-owned eligibility and semantic score policy."""

    def is_eligible(self, metadata: Mapping[str, object]) -> bool: ...

    def granularity(self, metadata: Mapping[str, object]) -> tuple[str, float]: ...


class AcceptAllCandidatePolicy:
    """Neutral default used when the caller has no domain policy."""

    def is_eligible(self, metadata: Mapping[str, object]) -> bool:
        del metadata
        return True

    def granularity(self, metadata: Mapping[str, object]) -> tuple[str, float]:
        del metadata
        return "unknown", 0.0
