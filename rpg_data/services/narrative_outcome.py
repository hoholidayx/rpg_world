"""Narrative outcome configuration and persisted turn records."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database

from rpg_data import models
from rpg_data.repositories.narrative_outcome_repo import NarrativeOutcomeRepository
from rpg_data.repositories.session_repo import SessionRepository

_VALID_SOURCES = {
    models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    models.NARRATIVE_OUTCOME_SOURCE_STORY,
    models.NARRATIVE_OUTCOME_SOURCE_SESSION,
}


class NarrativeOutcomeService:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._sessions = SessionRepository(database)
        self._records = NarrativeOutcomeRepository(database)

    def record(
        self,
        *,
        session_id: str,
        turn_id: int,
        outcome_code: str,
        reason: str,
        actor: str,
        sample_value: int,
        effective_weights: models.NarrativeOutcomeWeights,
        effective_source: str,
    ) -> models.NarrativeOutcomeRecord:
        if outcome_code not in models.NARRATIVE_OUTCOME_CODES:
            raise ValueError(f"invalid narrative outcome code: {outcome_code}")
        if int(turn_id) <= 0:
            raise ValueError("turn_id must be positive")
        if not 1 <= int(sample_value) <= 100:
            raise ValueError("sample_value must be within [1, 100]")
        if effective_source not in _VALID_SOURCES:
            raise ValueError(f"invalid narrative outcome source: {effective_source}")
        if self._sessions.get(session_id) is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        return self._records.create(
            session_id=session_id,
            turn_id=turn_id,
            outcome_code=outcome_code,
            reason=reason.strip(),
            actor=actor.strip(),
            sample_value=sample_value,
            effective_weights=effective_weights,
            effective_source=effective_source,
        )

    def get_for_turn(self, session_id: str, turn_id: int) -> models.NarrativeOutcomeRecord | None:
        return self._records.get_for_turn(session_id, turn_id)

    def list_for_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> list[models.NarrativeOutcomeRecord]:
        return self._records.list_for_turns(session_id, turn_ids)

    def delete_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_from_turn(session_id, turn_id)

    def delete_for_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_for_turn(session_id, turn_id)

    def retain_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        return self._records.retain_turns(session_id, turn_ids)

    def clear(self, session_id: str) -> int:
        return self._records.clear(session_id)
