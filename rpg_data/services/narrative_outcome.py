"""Typed persistence boundary for Narrative Outcome turn records."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database, IntegrityError

from rpg_data.errors import DataIntegrityError
from rpg_data.model.narrative_outcome import (
    NarrativeOutcomeCreate,
    NarrativeOutcomeRecord,
)
from rpg_data.repositories.narrative_outcome_repo import NarrativeOutcomeRepository
from rpg_data.repositories.session_repo import SessionRepository

__all__ = ["NarrativeOutcomeDataService"]


class NarrativeOutcomeDataService:
    """Persist caller-validated Outcome rows and expose ledger queries."""

    def __init__(self, database: Database) -> None:
        self._sessions = SessionRepository(database)
        self._records = NarrativeOutcomeRepository(database)

    def append(self, values: NarrativeOutcomeCreate) -> NarrativeOutcomeRecord:
        if self._sessions.get(str(values.session_id)) is None:
            raise FileNotFoundError(f"session not found: {values.session_id}")
        try:
            return self._records.create(values)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Narrative Outcome write violated persisted constraints"
            ) from exc

    def get_for_turn(self, session_id: str, turn_id: int) -> NarrativeOutcomeRecord | None:
        return self._records.get_for_turn(session_id, turn_id)

    def list_for_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> list[NarrativeOutcomeRecord]:
        return self._records.list_for_turns(session_id, turn_ids)

    def delete_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_from_turn(session_id, turn_id)

    def delete_for_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_for_turn(session_id, turn_id)

    def retain_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        return self._records.retain_turns(session_id, turn_ids)

    def clear(self, session_id: str) -> int:
        return self._records.clear(session_id)
