"""Shared typed vocabulary for Story and Persistent Memory facts."""

from __future__ import annotations

from enum import StrEnum


class MemoryKind(StrEnum):
    CHARACTER = "character"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    COMMITMENT = "commitment"
    CLUE = "clue"
    WORLD_FACT = "world_fact"
    STATE_CHANGE = "state_change"


class EpistemicStatus(StrEnum):
    CONFIRMED = "confirmed"
    REPORTED = "reported"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"


MEMORY_KINDS = frozenset(item.value for item in MemoryKind)
EPISTEMIC_STATUSES = frozenset(item.value for item in EpistemicStatus)
