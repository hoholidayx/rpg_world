"""Session message service for mutable main history."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from functools import reduce
from operator import add, or_

from peewee import Case, Database, fn

from commons.errors import InvalidTurnMetadataError
from rpg_data.model import session as models
from rpg_data.repositories._utils import to_session_message
from rpg_data.repositories.records import SessionMessageRecord
from rpg_data.services._message_store import BaseSessionMessageStore, MessageInput

__all__ = ["MessageDataService"]


class MessageDataService:
    """Expose CRUD for the current mutable session message history."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._store = BaseSessionMessageStore(database, SessionMessageRecord)

    def search_history_turns(
        self,
        session_id: str,
        terms: Collection[str],
        *,
        limit: int,
    ) -> list[models.SessionHistorySearchHit]:
        """Search committed user/assistant messages and return unique matching turns."""

        normalized_terms = _normalize_history_search_terms(terms)
        result_limit = int(limit)
        if result_limit <= 0:
            raise ValueError("limit must be positive")

        turn_term_flags = tuple(
            fn.MAX(
                Case(
                    None,
                    (
                        (
                            fn.INSTR(
                                fn.LOWER(SessionMessageRecord.content),
                                _ascii_fold(term),
                            )
                            > 0,
                            1,
                        ),
                    ),
                    0,
                )
            )
            for term in normalized_terms
        )
        matched_term_count = reduce(add, turn_term_flags)
        matched_term_length = reduce(
            add,
            (
                flag * len(term)
                for flag, term in zip(
                    turn_term_flags,
                    normalized_terms,
                    strict=True,
                )
            ),
        )
        candidate_query = (
            SessionMessageRecord
            .select(
                SessionMessageRecord.turn_id,
                *(
                    flag.alias(f"term_match_{index}")
                    for index, flag in enumerate(turn_term_flags)
                ),
            )
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id > 0)
                & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
            )
            .group_by(SessionMessageRecord.turn_id)
            .having(matched_term_count > 0)
            .order_by(
                matched_term_count.desc(),
                matched_term_length.desc(),
                SessionMessageRecord.turn_id.desc(),
            )
            .limit(result_limit)
            .dicts()
        )
        message_term_filters = tuple(
            fn.INSTR(
                fn.LOWER(SessionMessageRecord.content),
                _ascii_fold(term),
            )
            > 0
            for term in normalized_terms
        )

        with self._database.atomic():
            candidate_rows = tuple(candidate_query)
            candidates = tuple(
                (
                    int(row["turn_id"]),
                    tuple(
                        term
                        for index, term in enumerate(normalized_terms)
                        if int(row[f"term_match_{index}"])
                    ),
                )
                for row in candidate_rows
            )
            if not candidates:
                return []

            candidate_turn_ids = tuple(turn_id for turn_id, _ in candidates)
            message_query = (
                SessionMessageRecord
                .select(
                    SessionMessageRecord.id,
                    SessionMessageRecord.turn_id,
                    SessionMessageRecord.seq_in_turn,
                    SessionMessageRecord.role,
                    SessionMessageRecord.mode,
                    SessionMessageRecord.content,
                )
                .where(
                    (SessionMessageRecord.session == str(session_id))
                    & (SessionMessageRecord.turn_id.in_(candidate_turn_ids))
                    & (SessionMessageRecord.turn_id > 0)
                    & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
                    & reduce(or_, message_term_filters)
                )
                .order_by(
                    SessionMessageRecord.turn_id,
                    SessionMessageRecord.seq_in_turn,
                    SessionMessageRecord.id,
                )
            )

            matches_by_turn: dict[
                int,
                list[tuple[SessionMessageRecord, tuple[str, ...]]],
            ] = {}
            for row in message_query:
                folded_content = _ascii_fold(str(row.content or ""))
                matched_terms = tuple(
                    term
                    for term in normalized_terms
                    if _ascii_fold(term) in folded_content
                )
                if not matched_terms:
                    continue
                matches_by_turn.setdefault(int(row.turn_id), []).append(
                    (row, matched_terms)
                )

        hits: list[models.SessionHistorySearchHit] = []
        for turn_id, turn_matched_terms in candidates:
            message_matches = matches_by_turn.get(turn_id, ())
            if not message_matches:
                continue
            representative, _ = min(
                message_matches,
                key=lambda item: (
                    -len(item[1]),
                    -sum(len(term) for term in item[1]),
                    int(item[0].seq_in_turn),
                    int(item[0].id),
                ),
            )
            hits.append(
                models.SessionHistorySearchHit(
                    turn_id=turn_id,
                    message_id=int(representative.id),
                    seq_in_turn=int(representative.seq_in_turn),
                    role=str(representative.role),
                    mode=str(representative.mode or models.TURN_MODE_NEUTRAL),
                    content=str(representative.content or ""),
                    matched_terms=turn_matched_terms,
                )
            )
        return hits

    def read_history_turn_window(
        self,
        session_id: str,
        *,
        anchor_turn_id: int,
        before_turns: int,
        after_turns: int,
    ) -> models.SessionHistoryTurnWindow | None:
        """Read an ordered window of actual committed turns from one Session."""

        anchor = int(anchor_turn_id)
        before = int(before_turns)
        after = int(after_turns)
        if anchor <= 0:
            raise ValueError("anchor_turn_id must be positive")
        if not 0 <= before <= 2:
            raise ValueError("before_turns must be between 0 and 2")
        if not 0 <= after <= 2:
            raise ValueError("after_turns must be between 0 and 2")

        with self._database.atomic():
            anchor_row = (
                SessionMessageRecord
                .select(SessionMessageRecord.id)
                .where(
                    (SessionMessageRecord.session == str(session_id))
                    & (SessionMessageRecord.turn_id == anchor)
                    & (SessionMessageRecord.turn_id > 0)
                    & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
                )
                .limit(1)
                .first()
            )
            if anchor_row is None:
                return None

            before_candidates = tuple(
                int(row[0])
                for row in (
                    SessionMessageRecord
                    .select(SessionMessageRecord.turn_id)
                    .where(
                        (SessionMessageRecord.session == str(session_id))
                        & (SessionMessageRecord.turn_id > 0)
                        & (SessionMessageRecord.turn_id < anchor)
                        & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
                    )
                    .distinct()
                    .order_by(SessionMessageRecord.turn_id.desc())
                    .limit(before + 1)
                    .tuples()
                )
            )
            after_candidates = tuple(
                int(row[0])
                for row in (
                    SessionMessageRecord
                    .select(SessionMessageRecord.turn_id)
                    .where(
                        (SessionMessageRecord.session == str(session_id))
                        & (SessionMessageRecord.turn_id > anchor)
                        & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
                    )
                    .distinct()
                    .order_by(SessionMessageRecord.turn_id)
                    .limit(after + 1)
                    .tuples()
                )
            )

            selected_before = tuple(reversed(before_candidates[:before]))
            selected_after = after_candidates[:after]
            turn_ids = (*selected_before, anchor, *selected_after)
            message_rows = (
                SessionMessageRecord
                .select()
                .where(
                    (SessionMessageRecord.session == str(session_id))
                    & (SessionMessageRecord.turn_id.in_(turn_ids))
                    & (SessionMessageRecord.role.in_(_HISTORY_MESSAGE_ROLES))
                )
                .order_by(
                    SessionMessageRecord.turn_id,
                    SessionMessageRecord.seq_in_turn,
                    SessionMessageRecord.id,
                )
            )
            messages = tuple(to_session_message(row) for row in message_rows)

        return models.SessionHistoryTurnWindow(
            anchor_turn_id=anchor,
            turn_ids=turn_ids,
            messages=messages,
            has_before=len(before_candidates) > before,
            has_after=len(after_candidates) > after,
        )

    def append(
        self,
        session_id: str,
        role: str,
        content: str = "",
        *,
        mode: str = models.TURN_MODE_NEUTRAL,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str = "",
        tool_calls_json: str = "",
        metadata_json: str = "{}",
    ) -> models.SessionMessage:
        return self._store.append(
            session_id,
            role,
            content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        )

    def append_mapping(
        self,
        session_id: str,
        values: models.SessionMessage | Mapping[str, object],
    ) -> models.SessionMessage:
        return self._store.append_mapping(session_id, values)

    def list(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[models.SessionMessage]:
        return self._store.list(session_id, limit=limit, offset=offset)

    def list_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> list[models.SessionMessage]:
        return self._store.list_filtered(
            session_id,
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def count_distinct_turns(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> int:
        return self._store.count_distinct_turns(
            session_id,
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def list_turn_window(
        self,
        session_id: str,
        *,
        limit: int,
        before_turn_id: int | None = None,
        after_turn_id: int | None = None,
    ) -> list[models.SessionMessage]:
        return self._store.list_turn_window(
            session_id,
            limit=limit,
            before_turn_id=before_turn_id,
            after_turn_id=after_turn_id,
        )

    def list_turn(self, session_id: str, turn_id: int) -> list[models.SessionMessage]:
        return self._store.list_turn(session_id, turn_id)

    def has_turn_before(self, session_id: str, turn_id: int) -> bool:
        return self._store.has_turn_before(session_id, turn_id)

    def has_turn_after(self, session_id: str, turn_id: int) -> bool:
        return self._store.has_turn_after(session_id, turn_id)

    def get(self, message_id: int) -> models.SessionMessage | None:
        return self._store.get(message_id)

    def get_for_session(self, session_id: str, message_id: int) -> models.SessionMessage | None:
        return self._store.get_for_session(session_id, message_id)

    def update(
        self,
        message_id: int,
        *,
        role: str | None = None,
        content: str | None = None,
        mode: str | None = None,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        if turn_id is not None or seq_in_turn is not None:
            raise InvalidTurnMetadataError("turn_id and seq_in_turn are immutable; use a dedicated repair flow")
        return self._store.update(
            message_id,
            role=role,
            content=content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        )

    def delete(self, message_id: int) -> bool:
        return self._store.delete(message_id)

    def delete_for_session(self, session_id: str, message_id: int) -> bool:
        return self._store.delete_for_session(session_id, message_id)

    def clear(self, session_id: str) -> int:
        return self._store.clear(session_id)

    def count(self, session_id: str) -> int:
        return self._store.count(session_id)

    def latest_turn_id(self, session_id: str) -> int:
        return self._store.latest_turn_id(session_id)

    def list_summary_turn_ranges(self, session_id: str) -> dict[int, tuple[int, int]]:
        """Return min/max turn IDs for each processed summary batch."""

        return self._store.list_summary_turn_ranges(session_id)

    def replace(
        self,
        session_id: str,
        messages: Iterable[MessageInput],
    ) -> list[models.SessionMessage]:
        return self._store.replace(session_id, messages)

    def truncate_before_id(self, session_id: str, boundary_id: int) -> int:
        return self._store.truncate_before_id(session_id, boundary_id)

    def truncate_before_index(self, session_id: str, keep_from_index: int) -> int:
        return self._store.truncate_before_index(session_id, keep_from_index)

    def truncate_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._store.truncate_from_turn(session_id, turn_id)

    def mark_summary_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
        *,
        batch_id: int | None,
    ) -> int:
        return self._store.mark_summary_processed(
            session_id,
            message_ids,
            batch_id=batch_id,
        )

    def mark_summary_batches_processed(
        self,
        session_id: str,
        batches: Iterable[tuple[Iterable[int], int]],
    ) -> int:
        return self._store.mark_summary_batches_processed(session_id, batches)

    def mark_story_memory_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._store.mark_story_memory_processed(session_id, message_ids)

    def reset_processing_for_messages(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._store.reset_processing_for_messages(session_id, message_ids)


_ASCII_UPPER_TO_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)
_HISTORY_MESSAGE_ROLES = (
    models.MESSAGE_ROLE_USER,
    models.MESSAGE_ROLE_ASSISTANT,
)


def _ascii_fold(value: str) -> str:
    return value.translate(_ASCII_UPPER_TO_LOWER)


def _normalize_history_search_terms(terms: Collection[str]) -> tuple[str, ...]:
    if isinstance(terms, str):
        raise ValueError("terms must be a collection of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_term in terms:
        if not isinstance(raw_term, str):
            raise ValueError("history search terms must be strings")
        term = raw_term.strip()
        if not term:
            continue
        if len(term) > 64:
            raise ValueError("history search terms must be at most 64 characters")
        key = _ascii_fold(term)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(term)

    if not normalized:
        raise ValueError("at least one non-empty history search term is required")
    if len(normalized) > 8:
        raise ValueError("at most 8 history search terms are allowed")
    return tuple(normalized)
