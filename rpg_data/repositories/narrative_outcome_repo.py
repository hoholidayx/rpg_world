"""Repository for persisted narrative outcome records."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database

from rpg_data.model.narrative_outcome import (
    NarrativeOutcomeCreate,
    NarrativeOutcomeRecord,
)
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
        values: NarrativeOutcomeCreate,
    ) -> NarrativeOutcomeRecord:
        row = SessionNarrativeOutcomeRecord.create(
            session=str(values.session_id),
            turn_id=int(values.turn_id),
            outcome_code=str(values.outcome_code),
            reason=str(values.reason),
            actor=str(values.actor),
            sample_value=int(values.sample_value),
            effective_weights_json=serialize_narrative_outcome_weights(
                values.effective_weights
            ),
            effective_source=str(values.effective_source),
        )
        return to_narrative_outcome(SessionNarrativeOutcomeRecord.get_by_id(row.id))

    def get_for_turn(self, session_id: str, turn_id: int) -> NarrativeOutcomeRecord | None:
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
    ) -> list[NarrativeOutcomeRecord]:
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
