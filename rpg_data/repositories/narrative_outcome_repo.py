"""Repository for persisted narrative outcome records."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database

from rpg_data import models
from rpg_data.repositories._utils import (
    serialize_narrative_outcome_weights,
    to_narrative_outcome,
)
from rpg_data.repositories.records import SessionNarrativeOutcomeRecord, bind_database


class NarrativeOutcomeRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
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
        row = SessionNarrativeOutcomeRecord.create(
            session=session_id,
            turn_id=int(turn_id),
            outcome_code=outcome_code,
            reason=reason,
            actor=actor,
            sample_value=int(sample_value),
            effective_weights_json=serialize_narrative_outcome_weights(effective_weights),
            effective_source=effective_source,
        )
        return to_narrative_outcome(SessionNarrativeOutcomeRecord.get_by_id(row.id))

    def get_for_turn(self, session_id: str, turn_id: int) -> models.NarrativeOutcomeRecord | None:
        row = (
            SessionNarrativeOutcomeRecord
            .select()
            .where(
                (SessionNarrativeOutcomeRecord.session == session_id)
                & (SessionNarrativeOutcomeRecord.turn_id == int(turn_id))
            )
            .first()
        )
        return to_narrative_outcome(row) if row is not None else None

    def list_for_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> list[models.NarrativeOutcomeRecord]:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        if not ids:
            return []
        rows = (
            SessionNarrativeOutcomeRecord
            .select()
            .where(
                (SessionNarrativeOutcomeRecord.session == session_id)
                & (SessionNarrativeOutcomeRecord.turn_id.in_(ids))
            )
            .order_by(SessionNarrativeOutcomeRecord.turn_id)
        )
        return [to_narrative_outcome(row) for row in rows]

    def delete_from_turn(self, session_id: str, turn_id: int) -> int:
        return int(
            SessionNarrativeOutcomeRecord
            .delete()
            .where(
                (SessionNarrativeOutcomeRecord.session == session_id)
                & (SessionNarrativeOutcomeRecord.turn_id >= int(turn_id))
            )
            .execute()
        )

    def delete_for_turn(self, session_id: str, turn_id: int) -> int:
        return int(
            SessionNarrativeOutcomeRecord
            .delete()
            .where(
                (SessionNarrativeOutcomeRecord.session == session_id)
                & (SessionNarrativeOutcomeRecord.turn_id == int(turn_id))
            )
            .execute()
        )

    def retain_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        if not ids:
            return self.clear(session_id)
        return int(
            SessionNarrativeOutcomeRecord
            .delete()
            .where(
                (SessionNarrativeOutcomeRecord.session == session_id)
                & ~(SessionNarrativeOutcomeRecord.turn_id.in_(ids))
            )
            .execute()
        )

    def clear(self, session_id: str) -> int:
        return int(
            SessionNarrativeOutcomeRecord
            .delete()
            .where(SessionNarrativeOutcomeRecord.session == session_id)
            .execute()
        )
