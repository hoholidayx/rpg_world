"""Read-only, Session-scoped reference data queries."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from peewee import JOIN, Case, Database, fn

from rpg_data.plot_models import PLOT_SOURCE_OUTLINE, PLOT_SOURCE_POOL
from rpg_data.model import session_reference as models
from rpg_data.model import status as status_models
from rpg_data.repositories.records import (
    SessionMessageRecord,
    SessionNarrativeOutcomeRecord,
    SessionPlotScheduleDecisionRecord,
    SessionProfileRecord,
    SessionRecord,
    SessionStatusTableRecord,
    StoryCharacterDetailRecord,
    StoryCharacterRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.settings import (
    resolve_workspace_relative_path,
    resolve_workspace_root,
)
from rpg_data.transaction import DataTransactionMode

__all__ = ["SessionReferenceDataService"]

_MAX_PAGE_SIZE = 100


class SessionReferenceDataService:
    """Provide efficient data facts for Session reference consumers.

    This service intentionally does not decide visibility, grouping, menu
    ordering, truncation, or channel presentation.
    """

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Open a read snapshot; nested calls use Peewee savepoints."""

        with self._database.atomic(DataTransactionMode.DEFERRED.value):
            yield

    def require_scope(
        self,
        locator: models.SessionReferenceLocator,
    ) -> models.SessionReferenceScope:
        """Return one exact Session scope or raise ``FileNotFoundError``."""

        row = (
            SessionRecord.select(
                SessionRecord.lifecycle.alias("_lifecycle"),
                SessionRecord.version.alias("_session_version"),
                SessionRecord.updated_at.alias("_updated_at"),
                SessionProfileRecord.title.alias("_title"),
                SessionProfileRecord.player_character_id.alias(
                    "_player_character_id"
                ),
            )
            .join(SessionProfileRecord, JOIN.LEFT_OUTER)
            .where(_session_scope_clause(locator))
            .dicts()
            .first()
        )
        if row is None:
            raise FileNotFoundError(
                "Session reference scope not found: "
                f"{locator.workspace_id}/{locator.story_id}/{locator.session_id}"
            )
        return models.SessionReferenceScope(
            locator=locator,
            lifecycle=str(row["_lifecycle"]),
            title=str(row["_title"] or ""),
            player_character_id=_optional_int(row["_player_character_id"]),
            session_version=int(row["_session_version"]),
            updated_at=str(row["_updated_at"] or ""),
        )

    def list_characters(
        self,
        locator: models.SessionReferenceLocator,
        *,
        page: int,
        page_size: int,
    ) -> models.ReferenceDataPage[models.SessionReferenceCharacter]:
        page, page_size = _validated_page(page, page_size)
        with self.transaction():
            self.require_scope(locator)
            where_clause = _character_scope_clause(locator)
            total = (
                StoryCharacterRecord.select(StoryCharacterRecord.id)
                .join(
                    SessionRecord,
                    on=_character_session_join_clause(),
                )
                .where(where_clause)
                .count()
            )
            rows = tuple(
                _character_rows_query(locator)
                .order_by(
                    StoryCharacterRecord.sort_order,
                    StoryCharacterRecord.id,
                )
                .paginate(page, page_size)
                .dicts()
            )
            return models.ReferenceDataPage(
                items=tuple(_character_from_row(row) for row in rows),
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_character(
        self,
        locator: models.SessionReferenceLocator,
        character_id: int,
    ) -> models.SessionReferenceCharacter | None:
        with self.transaction():
            self.require_scope(locator)
            row = (
                _character_rows_query(locator)
                .where(StoryCharacterRecord.id == int(character_id))
                .dicts()
                .first()
            )
            return _character_from_row(row) if row is not None else None

    def list_character_order_ids(
        self,
        locator: models.SessionReferenceLocator,
    ) -> tuple[int, ...]:
        """Return every scoped character ID in persisted card order."""

        with self.transaction():
            self.require_scope(locator)
            rows = tuple(
                StoryCharacterRecord.select(
                    StoryCharacterRecord.id.alias("_id")
                )
                .join(
                    SessionRecord,
                    on=_character_session_join_clause(),
                )
                .where(_character_scope_clause(locator))
                .order_by(
                    StoryCharacterRecord.sort_order,
                    StoryCharacterRecord.id,
                )
                .dicts()
            )
            return tuple(int(row["_id"]) for row in rows)

    def list_character_details(
        self,
        locator: models.SessionReferenceLocator,
        character_id: int,
        *,
        page: int,
        page_size: int,
    ) -> models.ReferenceDataPage[models.SessionReferenceCharacterDetailItem]:
        page, page_size = _validated_page(page, page_size)
        with self.transaction():
            self.require_scope(locator)
            where_clause = _character_detail_scope_clause(
                locator,
                character_id,
            )
            total = (
                StoryCharacterDetailRecord.select(
                    StoryCharacterDetailRecord.id
                )
                .join(StoryCharacterRecord)
                .switch(StoryCharacterRecord)
                .join(
                    SessionRecord,
                    on=_character_session_join_clause(),
                )
                .where(where_clause)
                .count()
            )
            rows = tuple(
                _character_detail_item_rows_query(locator, character_id)
                .order_by(
                    StoryCharacterDetailRecord.sort_order,
                    StoryCharacterDetailRecord.id,
                )
                .paginate(page, page_size)
                .dicts()
            )
            return models.ReferenceDataPage(
                items=tuple(
                    _character_detail_item_from_row(row) for row in rows
                ),
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_character_detail(
        self,
        locator: models.SessionReferenceLocator,
        character_id: int,
        detail_id: int,
    ) -> models.SessionReferenceCharacterDetail | None:
        with self.transaction():
            self.require_scope(locator)
            row = (
                _character_detail_rows_query(locator, character_id)
                .where(StoryCharacterDetailRecord.id == int(detail_id))
                .dicts()
                .first()
            )
            return (
                _character_detail_from_row(row) if row is not None else None
            )

    def list_status_tables(
        self,
        locator: models.SessionReferenceLocator,
        *,
        page: int,
        page_size: int,
        character_id: int | None = None,
        order: models.SessionReferenceStatusOrder | None = None,
    ) -> models.ReferenceDataPage[models.SessionReferenceStatusTableItem]:
        page, page_size = _validated_page(page, page_size)
        with self.transaction():
            self.require_scope(locator)
            where_clause = _status_scope_clause(locator)
            if character_id is not None:
                where_clause &= _status_character_id_expression() == int(
                    character_id
                )
            total = (
                SessionStatusTableRecord.select(SessionStatusTableRecord.id)
                .join(
                    SessionRecord,
                    on=SessionStatusTableRecord.session == SessionRecord.id,
                )
                .where(where_clause)
                .count()
            )
            rows_query = _status_rows_query(
                locator,
                include_document=False,
            )
            if character_id is not None:
                rows_query = rows_query.where(
                    _status_character_id_expression() == int(character_id)
                )
            order_by = _status_order_by(order)
            rows = tuple(
                rows_query.order_by(*order_by)
                .paginate(page, page_size)
                .dicts()
            )
            return models.ReferenceDataPage(
                items=tuple(_status_item_from_row(row) for row in rows),
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_status_table(
        self,
        locator: models.SessionReferenceLocator,
        table_id: int,
    ) -> models.SessionReferenceStatusTableDetail | None:
        with self.transaction():
            self.require_scope(locator)
            row = (
                _status_rows_query(locator, include_document=True)
                .where(SessionStatusTableRecord.id == int(table_id))
                .dicts()
                .first()
            )
            return _status_detail_from_row(row) if row is not None else None

    def get_summary_source(
        self,
        locator: models.SessionReferenceLocator,
    ) -> models.SessionReferenceSummarySource:
        with self.transaction():
            self.require_scope(locator)
            workspace_row = (
                SessionRecord.select(
                    WorkspaceRecord.root_path.alias("_root_path")
                )
                .join(WorkspaceRecord)
                .where(_session_scope_clause(locator))
                .dicts()
                .first()
            )
            if workspace_row is None:
                raise FileNotFoundError(
                    "Session reference scope not found: "
                    f"{locator.workspace_id}/"
                    f"{locator.story_id}/{locator.session_id}"
                )
            workspace_root = resolve_workspace_root(
                str(workspace_row["_root_path"])
            )
            runtime_dir = resolve_workspace_relative_path(
                workspace_root,
                Path("stories") / str(locator.story_id) / locator.session_id,
            )
            range_rows = tuple(
                SessionMessageRecord.select(
                    SessionMessageRecord.summary_batch_id.alias("_batch_id"),
                    fn.MIN(SessionMessageRecord.turn_id).alias(
                        "_turn_start"
                    ),
                    fn.MAX(SessionMessageRecord.turn_id).alias("_turn_end"),
                )
                .join(
                    SessionRecord,
                    on=SessionMessageRecord.session == SessionRecord.id,
                )
                .where(
                    _session_scope_clause(locator)
                    & (SessionMessageRecord.session == locator.session_id)
                    & (SessionMessageRecord.summary_processed == 1)
                    & SessionMessageRecord.summary_batch_id.is_null(False)
                )
                .group_by(SessionMessageRecord.summary_batch_id)
                .order_by(SessionMessageRecord.summary_batch_id)
                .dicts()
            )
            return models.SessionReferenceSummarySource(
                runtime_dir=runtime_dir,
                batch_turn_ranges=tuple(
                    models.SummaryBatchTurnRange(
                        batch_id=int(row["_batch_id"]),
                        turn_start=int(row["_turn_start"]),
                        turn_end=int(row["_turn_end"]),
                    )
                    for row in range_rows
                ),
            )

    def get_turn_annotation_facts(
        self,
        locator: models.SessionReferenceLocator,
        turn_id: int,
    ) -> models.SessionReferenceTurnAnnotationFacts:
        """Read one scoped turn's Outcome and Plot ledger facts."""

        normalized_turn_id = _validated_turn_id(turn_id)
        with self.transaction():
            self.require_scope(locator)
            outcome_row = (
                SessionNarrativeOutcomeRecord.select(
                    SessionNarrativeOutcomeRecord.outcome_code.alias(
                        "_outcome_code"
                    ),
                    SessionNarrativeOutcomeRecord.reason.alias("_reason"),
                    SessionNarrativeOutcomeRecord.actor.alias("_actor"),
                )
                .join(
                    SessionRecord,
                    on=(
                        SessionNarrativeOutcomeRecord.session
                        == SessionRecord.id
                    ),
                )
                .where(
                    _session_scope_clause(locator)
                    & (
                        SessionNarrativeOutcomeRecord.session
                        == locator.session_id
                    )
                    & (
                        SessionNarrativeOutcomeRecord.turn_id
                        == normalized_turn_id
                    )
                )
                .dicts()
                .first()
            )
            outcome = (
                models.SessionReferenceNarrativeOutcomeFact(
                    outcome_code=str(outcome_row["_outcome_code"]),
                    reason=str(outcome_row["_reason"] or ""),
                    actor=str(outcome_row["_actor"] or ""),
                )
                if outcome_row is not None
                else None
            )

            source_rank = Case(
                SessionPlotScheduleDecisionRecord.source_kind,
                (
                    (PLOT_SOURCE_OUTLINE, 0),
                    (PLOT_SOURCE_POOL, 1),
                ),
                2,
            )
            plot_rows = tuple(
                SessionPlotScheduleDecisionRecord.select(
                    SessionPlotScheduleDecisionRecord.id.alias("_decision_id"),
                    SessionPlotScheduleDecisionRecord.source_kind.alias(
                        "_source_kind"
                    ),
                    SessionPlotScheduleDecisionRecord.decision_status.alias(
                        "_decision_status"
                    ),
                    SessionPlotScheduleDecisionRecord.event_snapshot_json.alias(
                        "_event_snapshot_json"
                    ),
                )
                .join(
                    SessionRecord,
                    on=(
                        SessionPlotScheduleDecisionRecord.session
                        == SessionRecord.id
                    ),
                )
                .where(
                    _session_scope_clause(locator)
                    & (
                        SessionPlotScheduleDecisionRecord.session
                        == locator.session_id
                    )
                    & (
                        SessionPlotScheduleDecisionRecord.turn_id
                        == normalized_turn_id
                    )
                )
                .order_by(
                    source_rank,
                    SessionPlotScheduleDecisionRecord.id,
                )
                .dicts()
            )
            return models.SessionReferenceTurnAnnotationFacts(
                turn_id=normalized_turn_id,
                outcome=outcome,
                plot_decisions=tuple(
                    _plot_decision_fact_from_row(row) for row in plot_rows
                ),
            )


def _session_scope_clause(locator: models.SessionReferenceLocator):
    return (
        (SessionRecord.id == str(locator.session_id))
        & (SessionRecord.workspace == str(locator.workspace_id))
        & (SessionRecord.story == int(locator.story_id))
    )


def _validated_turn_id(turn_id: object) -> int:
    if isinstance(turn_id, bool):
        raise ValueError("turn_id must be a positive integer")
    try:
        normalized = int(turn_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("turn_id must be a positive integer") from exc
    if normalized <= 0:
        raise ValueError("turn_id must be a positive integer")
    return normalized


def _plot_decision_fact_from_row(
    row: dict[str, object],
) -> models.SessionReferencePlotDecisionFact:
    event_title: str | None = None
    directive: str | None = None
    try:
        snapshot = json.loads(str(row["_event_snapshot_json"] or ""))
    except (TypeError, ValueError):
        snapshot = None
    if isinstance(snapshot, dict):
        raw_title = snapshot.get("eventTitle")
        raw_directive = snapshot.get("directive")
        event_title = raw_title if isinstance(raw_title, str) else None
        directive = raw_directive if isinstance(raw_directive, str) else None
    return models.SessionReferencePlotDecisionFact(
        decision_id=int(row["_decision_id"]),
        source_kind=str(row["_source_kind"]),
        decision_status=str(row["_decision_status"]),
        event_title=event_title,
        directive=directive,
    )


def _character_session_join_clause():
    return (
        (SessionRecord.workspace == StoryCharacterRecord.workspace)
        & (SessionRecord.story == StoryCharacterRecord.story)
    )


def _character_scope_clause(locator: models.SessionReferenceLocator):
    return (
        _session_scope_clause(locator)
        & (StoryCharacterRecord.workspace == str(locator.workspace_id))
        & (StoryCharacterRecord.story == int(locator.story_id))
    )


def _character_rows_query(locator: models.SessionReferenceLocator):
    return (
        StoryCharacterRecord.select(
            StoryCharacterRecord.id.alias("_id"),
            StoryCharacterRecord.name.alias("_name"),
            StoryCharacterRecord.description.alias("_description"),
            StoryCharacterRecord.sort_order.alias("_sort_order"),
            StoryCharacterRecord.metadata_json.alias("_metadata_json"),
            StoryCharacterRecord.version.alias("_version"),
            StoryCharacterRecord.updated_at.alias("_updated_at"),
            fn.COUNT(StoryCharacterDetailRecord.id).alias("_details_count"),
        )
        .join(StoryCharacterDetailRecord, JOIN.LEFT_OUTER)
        .switch(StoryCharacterRecord)
        .join(
            SessionRecord,
            on=_character_session_join_clause(),
        )
        .where(_character_scope_clause(locator))
        .group_by(
            StoryCharacterRecord.id,
            StoryCharacterRecord.name,
            StoryCharacterRecord.description,
            StoryCharacterRecord.sort_order,
            StoryCharacterRecord.metadata_json,
            StoryCharacterRecord.version,
            StoryCharacterRecord.updated_at,
        )
    )


def _character_from_row(
    row: dict[str, object],
) -> models.SessionReferenceCharacter:
    return models.SessionReferenceCharacter(
        id=int(row["_id"]),
        name=str(row["_name"]),
        description=str(row["_description"] or ""),
        sort_order=int(row["_sort_order"]),
        details_count=int(row["_details_count"]),
        metadata_json=str(row["_metadata_json"] or "{}"),
        version=int(row["_version"]),
        updated_at=str(row["_updated_at"] or ""),
    )


def _character_detail_scope_clause(
    locator: models.SessionReferenceLocator,
    character_id: int,
):
    return _character_scope_clause(locator) & (
        StoryCharacterRecord.id == int(character_id)
    )


def _character_detail_rows_query(
    locator: models.SessionReferenceLocator,
    character_id: int,
):
    return (
        StoryCharacterDetailRecord.select(
            StoryCharacterDetailRecord.id.alias("_id"),
            StoryCharacterDetailRecord.story_character.alias("_character_id"),
            StoryCharacterDetailRecord.name.alias("_name"),
            StoryCharacterDetailRecord.content.alias("_content"),
            StoryCharacterDetailRecord.tags_json.alias("_tags_json"),
            StoryCharacterDetailRecord.sort_order.alias("_sort_order"),
            StoryCharacterDetailRecord.version.alias("_version"),
            StoryCharacterDetailRecord.updated_at.alias("_updated_at"),
        )
        .join(StoryCharacterRecord)
        .switch(StoryCharacterRecord)
        .join(
            SessionRecord,
            on=_character_session_join_clause(),
        )
        .where(_character_detail_scope_clause(locator, character_id))
    )


def _character_detail_item_rows_query(
    locator: models.SessionReferenceLocator,
    character_id: int,
):
    return (
        StoryCharacterDetailRecord.select(
            StoryCharacterDetailRecord.id.alias("_id"),
            StoryCharacterDetailRecord.story_character.alias("_character_id"),
            StoryCharacterDetailRecord.name.alias("_name"),
            StoryCharacterDetailRecord.sort_order.alias("_sort_order"),
            StoryCharacterDetailRecord.version.alias("_version"),
            StoryCharacterDetailRecord.updated_at.alias("_updated_at"),
        )
        .join(StoryCharacterRecord)
        .switch(StoryCharacterRecord)
        .join(
            SessionRecord,
            on=_character_session_join_clause(),
        )
        .where(_character_detail_scope_clause(locator, character_id))
    )


def _character_detail_item_from_row(
    row: dict[str, object],
) -> models.SessionReferenceCharacterDetailItem:
    return models.SessionReferenceCharacterDetailItem(
        id=int(row["_id"]),
        character_id=int(row["_character_id"]),
        name=str(row["_name"]),
        sort_order=int(row["_sort_order"]),
        version=int(row["_version"]),
        updated_at=str(row["_updated_at"] or ""),
    )


def _character_detail_from_row(
    row: dict[str, object],
) -> models.SessionReferenceCharacterDetail:
    return models.SessionReferenceCharacterDetail(
        id=int(row["_id"]),
        character_id=int(row["_character_id"]),
        name=str(row["_name"]),
        content=str(row["_content"] or ""),
        tags_json=str(row["_tags_json"] or "[]"),
        sort_order=int(row["_sort_order"]),
        version=int(row["_version"]),
        updated_at=str(row["_updated_at"] or ""),
    )


def _status_scope_clause(locator: models.SessionReferenceLocator):
    return (
        _session_scope_clause(locator)
        & (SessionStatusTableRecord.session == str(locator.session_id))
        & (SessionStatusTableRecord.workspace == str(locator.workspace_id))
        & (SessionStatusTableRecord.story == int(locator.story_id))
    )


def _status_character_id_expression():
    metadata_is_valid = fn.json_valid(SessionStatusTableRecord.metadata_json) == 1
    return Case(
        None,
        (
            (
                metadata_is_valid,
                fn.json_extract(
                    SessionStatusTableRecord.metadata_json,
                    "$.storyStatusSource.characterId",
                ),
            ),
        ),
        None,
    )


def _status_rows_query(
    locator: models.SessionReferenceLocator,
    *,
    include_document: bool,
):
    columns = [
        SessionStatusTableRecord.id.alias("_id"),
        SessionStatusTableRecord.name.alias("_name"),
        SessionStatusTableRecord.status_kind.alias("_status_kind"),
        SessionStatusTableRecord.description.alias("_description"),
        SessionStatusTableRecord.sort_order.alias("_sort_order"),
        SessionStatusTableRecord.source_story_status_table.alias(
            "_source_story_status_table_id"
        ),
        SessionStatusTableRecord.origin.alias("_origin"),
        SessionStatusTableRecord.metadata_json.alias("_metadata_json"),
        SessionStatusTableRecord.version.alias("_version"),
        SessionStatusTableRecord.updated_at.alias("_updated_at"),
    ]
    if include_document:
        columns.append(SessionStatusTableRecord.document_json.alias("_document_json"))
    return (
        SessionStatusTableRecord.select(*columns)
        .join(
            SessionRecord,
            on=SessionStatusTableRecord.session == SessionRecord.id,
        )
        .where(_status_scope_clause(locator))
    )


def _status_order_by(
    order: models.SessionReferenceStatusOrder | None,
) -> tuple[object, ...]:
    if order is None:
        return (
            SessionStatusTableRecord.status_kind,
            SessionStatusTableRecord.sort_order,
            SessionStatusTableRecord.id,
        )
    expressions: list[object] = []
    if order.status_kind_order:
        expressions.append(
            Case(
                SessionStatusTableRecord.status_kind,
                tuple(
                    (status_kind, rank)
                    for rank, status_kind in enumerate(order.status_kind_order)
                ),
                len(order.status_kind_order),
            )
        )
    if order.associated_first:
        expressions.append(
            Case(
                None,
                (
                    (
                        _status_character_id_expression().is_null(False),
                        0,
                    ),
                ),
                1,
            )
        )
    if order.ordered_character_ids:
        expressions.append(
            Case(
                _status_character_id_expression(),
                tuple(
                    (character_id, rank)
                    for rank, character_id in enumerate(
                        order.ordered_character_ids
                    )
                ),
                len(order.ordered_character_ids),
            )
        )
    expressions.extend(
        (
            SessionStatusTableRecord.sort_order,
            SessionStatusTableRecord.id,
        )
    )
    return tuple(expressions)


def _status_item_from_row(
    row: dict[str, object],
) -> models.SessionReferenceStatusTableItem:
    metadata_json = str(row["_metadata_json"] or "{}")
    metadata = status_models.parse_session_status_metadata(metadata_json)
    source = metadata.story_source
    return models.SessionReferenceStatusTableItem(
        id=int(row["_id"]),
        name=str(row["_name"]),
        status_kind=str(row["_status_kind"]),
        description=str(row["_description"] or ""),
        sort_order=int(row["_sort_order"]),
        associated_character_id=(
            source.character_id if source is not None else None
        ),
        associated_character_name=(
            source.character_name if source is not None else None
        ),
        source_story_status_table_id=_optional_int(
            row["_source_story_status_table_id"]
        ),
        origin=str(row["_origin"]),
        metadata_json=metadata_json,
        version=int(row["_version"]),
        updated_at=str(row["_updated_at"] or ""),
    )


def _status_detail_from_row(
    row: dict[str, object],
) -> models.SessionReferenceStatusTableDetail:
    item = _status_item_from_row(row)
    return models.SessionReferenceStatusTableDetail(
        id=item.id,
        name=item.name,
        status_kind=item.status_kind,
        description=item.description,
        sort_order=item.sort_order,
        associated_character_id=item.associated_character_id,
        associated_character_name=item.associated_character_name,
        source_story_status_table_id=item.source_story_status_table_id,
        origin=item.origin,
        metadata_json=item.metadata_json,
        version=item.version,
        updated_at=item.updated_at,
        document=status_models.parse_status_document(str(row["_document_json"])),
    )


def _validated_page(page: int, page_size: int) -> tuple[int, int]:
    normalized_page = int(page)
    normalized_page_size = int(page_size)
    if normalized_page <= 0:
        raise ValueError("Reference page must be positive")
    if normalized_page_size <= 0 or normalized_page_size > _MAX_PAGE_SIZE:
        raise ValueError(
            f"Reference page_size must be between 1 and {_MAX_PAGE_SIZE}"
        )
    return normalized_page, normalized_page_size


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
