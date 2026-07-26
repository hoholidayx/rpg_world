"""Application service for lightweight-channel Session references."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from typing import Iterator, TypeVar

from rpg_data.model import memory as memory_models
from rpg_data.model.session import SESSION_LIFECYCLE_READY
from rpg_data.model.session_reference import (
    SessionReferenceScope as DataSessionReferenceScope,
    SessionReferenceStatusOrder,
)
from rpg_memory.persistent.reference import PersistentMemoryReferenceItem

from channels.session_reference.errors import (
    SessionReferenceNotFoundError,
    SessionReferenceResourceDisabledError,
    SessionReferenceUnavailableError,
)
from channels.session_reference.models import (
    CharacterCard,
    CharacterDetail,
    CharacterDetailSummary,
    CharacterSummary,
    DEFAULT_SESSION_REFERENCE_POLICY,
    EvidenceReference,
    PersistentMemoryDetail,
    PersistentMemorySummary,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferencePolicy,
    SessionReferenceResource,
    SessionReferenceScope,
    StatusRow,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    StoryMemorySummary,
    SummaryDetail,
    SummarySummary,
)
from channels.session_reference.ports import (
    PersistentMemoryReferenceProvider,
    SessionReferenceDataPort,
    StoryMemoryReferenceProvider,
    SummaryReferenceProvider,
)
from rpg_core.summary.reference import ResolvedSummaryDocument


T = TypeVar("T")
U = TypeVar("U")

_MEMORY_KIND_LABELS = {
    "character": "角色",
    "event": "事件",
    "relationship": "关系",
    "commitment": "承诺",
    "clue": "线索",
    "world_fact": "世界事实",
    "state_change": "持续影响",
}


class SessionReferenceApplicationService:
    """Compose scoped data facts into immutable player-facing projections."""

    def __init__(
        self,
        data: SessionReferenceDataPort,
        *,
        summaries: SummaryReferenceProvider,
        story_memories: StoryMemoryReferenceProvider,
        persistent_memories: PersistentMemoryReferenceProvider,
        policy: SessionReferencePolicy = DEFAULT_SESSION_REFERENCE_POLICY,
    ) -> None:
        self._data = data
        self._summaries = summaries
        self._story_memories = story_memories
        self._persistent_memories = persistent_memories
        self._policy = policy

    @property
    def policy(self) -> SessionReferencePolicy:
        return self._policy

    def get_scope(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceScope:
        locator = _normalized_locator(locator)
        with self._snapshot(locator) as scope:
            return SessionReferenceScope(
                locator=scope.locator,
                title=scope.title,
                lifecycle=scope.lifecycle,
                player_character_id=scope.player_character_id,
                version=scope.session_version,
                updated_at=scope.updated_at,
            )

    def list_characters(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterSummary]:
        locator = _normalized_locator(locator)
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.CHARACTERS,
        ) as scope:
            result = self._data.list_characters(
                locator,
                page=page,
                page_size=page_size,
            )
            return _data_page(
                result,
                lambda item: _character_summary(
                    item,
                    player_character_id=scope.player_character_id,
                ),
            )

    def get_character(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
    ) -> CharacterCard:
        locator = _normalized_locator(locator)
        normalized_id = _positive_id(character_id, "character_id")
        with self._snapshot(
            locator,
            SessionReferenceResource.CHARACTERS,
        ) as scope:
            character = self._data.get_character(locator, normalized_id)
            if character is None:
                raise SessionReferenceNotFoundError(
                    f"Character is no longer available: {normalized_id}"
                )

            return CharacterCard(
                id=character.character_id,
                name=character.name,
                description=character.description,
                is_player=(
                    scope.player_character_id == character.character_id
                ),
                details_count=character.details_count,
                version=character.version,
                updated_at=character.updated_at,
            )

    def list_character_details(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterDetailSummary]:
        locator = _normalized_locator(locator)
        normalized_id = _positive_id(character_id, "character_id")
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.CHARACTERS,
        ):
            if self._data.get_character(locator, normalized_id) is None:
                raise SessionReferenceNotFoundError(
                    f"Character is no longer available: {normalized_id}"
                )
            result = self._data.list_character_details(
                locator,
                normalized_id,
                page=page,
                page_size=page_size,
            )
            return _data_page(result, _character_detail_summary)

    def get_character_detail(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        detail_id: int,
    ) -> CharacterDetail:
        locator = _normalized_locator(locator)
        normalized_character_id = _positive_id(character_id, "character_id")
        normalized_detail_id = _positive_id(detail_id, "detail_id")
        with self._snapshot(
            locator,
            SessionReferenceResource.CHARACTERS,
        ):
            detail = self._data.get_character_detail(
                locator,
                normalized_character_id,
                normalized_detail_id,
            )
            if detail is None:
                raise SessionReferenceNotFoundError(
                    "Character detail is no longer available: "
                    f"{normalized_detail_id}"
                )
            return CharacterDetail(
                id=detail.detail_id,
                character_id=detail.character_id,
                title=detail.name,
                content=detail.content,
                version=detail.version,
                updated_at=detail.updated_at,
            )

    def list_status_tables(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
        character_id: int | None = None,
    ) -> ReferencePage[StatusTableSummary]:
        locator = _normalized_locator(locator)
        normalized_character_id = (
            _positive_id(character_id, "character_id")
            if character_id is not None
            else None
        )
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.STATUS_TABLES,
        ):
            if (
                normalized_character_id is not None
                and self._data.get_character(
                    locator,
                    normalized_character_id,
                )
                is None
            ):
                raise SessionReferenceNotFoundError(
                    "Character is no longer available: "
                    f"{normalized_character_id}"
                )
            order = self._status_order(locator)
            result = self._data.list_status_tables(
                locator,
                page=page,
                page_size=page_size,
                character_id=normalized_character_id,
                order=order,
            )
            return _data_page(result, _status_summary)

    def get_status_table(
        self,
        locator: SessionReferenceLocator,
        table_id: int,
    ) -> StatusTableDetail:
        locator = _normalized_locator(locator)
        normalized_id = _positive_id(table_id, "table_id")
        with self._snapshot(
            locator,
            SessionReferenceResource.STATUS_TABLES,
        ):
            table = self._data.get_status_table(locator, normalized_id)
            if table is None:
                raise SessionReferenceNotFoundError(
                    f"Status table is no longer available: {normalized_id}"
                )
            return StatusTableDetail(
                id=table.table_id,
                name=table.name,
                description=table.description,
                kind=str(table.status_kind),
                character_id=table.associated_character_id,
                character_name=table.associated_character_name,
                rows=tuple(
                    StatusRow(key=row.key, value=row.value)
                    for row in table.document.rows
                ),
                version=table.version,
                updated_at=table.updated_at,
            )

    def list_summaries(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[SummarySummary]:
        locator = _normalized_locator(locator)
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.SUMMARIES,
        ):
            documents = self._summaries.list_summaries(locator)
            return _sequence_page(
                documents,
                page=page,
                page_size=page_size,
                project=lambda document: _summary_summary(
                    document,
                    excerpt_limit=self._policy.excerpt_limit,
                ),
            )

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> SummaryDetail:
        locator = _normalized_locator(locator)
        normalized_id = str(summary_id or "").strip()
        if not normalized_id:
            raise SessionReferenceNotFoundError("Summary id must not be empty")
        with self._snapshot(
            locator,
            SessionReferenceResource.SUMMARIES,
        ):
            document = self._summaries.get_summary(locator, normalized_id)
            if document is None:
                raise SessionReferenceNotFoundError(
                    f"Summary is no longer available: {normalized_id}"
                )
            return _summary_detail(
                document,
                excerpt_limit=self._policy.excerpt_limit,
            )

    def list_story_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[StoryMemorySummary]:
        locator = _normalized_locator(locator)
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.STORY_MEMORIES,
        ):
            result = self._story_memories.list_reference_page(
                locator,
                page=page,
                page_size=page_size,
            )
            return _reference_page(
                items=tuple(
                    self._story_memory_summary(item)
                    for item in result.items
                ),
                page=result.page,
                page_size=result.page_size,
                total=result.total,
            )

    def get_story_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: int,
    ) -> StoryMemoryDetail:
        locator = _normalized_locator(locator)
        normalized_id = _positive_id(memory_id, "memory_id")
        with self._snapshot(
            locator,
            SessionReferenceResource.STORY_MEMORIES,
        ):
            memory = self._story_memories.get_reference(
                locator,
                normalized_id,
            )
            if memory is None:
                raise SessionReferenceNotFoundError(
                    f"Story Memory is no longer available: {normalized_id}"
                )
            return self._story_memory_detail(memory)

    def list_persistent_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[PersistentMemorySummary]:
        locator = _normalized_locator(locator)
        page, page_size = self._validate_page(page, page_size)
        with self._snapshot(
            locator,
            SessionReferenceResource.PERSISTENT_MEMORIES,
        ):
            memories = self._persistent_memories.list_memories(locator)
            return _sequence_page(
                memories,
                page=page,
                page_size=page_size,
                project=self._persistent_memory_summary,
            )

    def get_persistent_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> PersistentMemoryDetail:
        locator = _normalized_locator(locator)
        normalized_id = str(memory_id or "").strip()
        if not normalized_id:
            raise SessionReferenceNotFoundError(
                "Persistent Memory id must not be empty"
            )
        with self._snapshot(
            locator,
            SessionReferenceResource.PERSISTENT_MEMORIES,
        ):
            memory = self._persistent_memories.get_memory(
                locator,
                normalized_id,
            )
            if memory is None:
                raise SessionReferenceNotFoundError(
                    "Persistent Memory is no longer available: "
                    f"{normalized_id}"
                )
            return self._persistent_memory_detail(memory)

    @contextmanager
    def _snapshot(
        self,
        locator: SessionReferenceLocator,
        resource: SessionReferenceResource | None = None,
    ) -> Iterator[DataSessionReferenceScope]:
        try:
            with self._data.transaction():
                scope = self._data.require_scope(locator)
                if scope.lifecycle != SESSION_LIFECYCLE_READY:
                    raise SessionReferenceUnavailableError(
                        f"Session is not ready: {locator.session_id}"
                    )
                if (
                    resource is not None
                    and resource not in self._policy.enabled_resources
                ):
                    raise SessionReferenceResourceDisabledError(
                        "Session reference resource is disabled: "
                        f"{resource.value}"
                    )
                yield scope
        except FileNotFoundError as exc:
            raise SessionReferenceUnavailableError(
                "Session is missing or does not match the requested scope"
            ) from exc

    def _validate_page(self, page: int, page_size: int) -> tuple[int, int]:
        if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
            raise ValueError("page must be a positive integer")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size <= 0
            or page_size > self._policy.max_page_size
        ):
            raise ValueError(
                f"page_size must be between 1 and {self._policy.max_page_size}"
            )
        return page, page_size

    def _status_order(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceStatusOrder:
        return SessionReferenceStatusOrder(
            status_kind_order=("scene", "normal"),
            ordered_character_ids=self._data.list_character_order_ids(locator),
            associated_first=True,
        )

    def _story_memory_summary(
        self,
        memory: memory_models.SessionStoryMemory,
    ) -> StoryMemorySummary:
        return StoryMemorySummary(
            id=memory.id,
            title=_story_memory_title(memory),
            excerpt=_excerpt(memory.text, self._policy.excerpt_limit),
            memory_kind=memory.memory_kind,
            epistemic_status=memory.epistemic_status,
            salience=memory.salience,
            turn_start=memory.source_turn_start,
            turn_end=memory.source_turn_end,
            evidence=_evidence(memory.evidence),
            version=memory.version,
            updated_at=memory.updated_at,
        )

    def _story_memory_detail(
        self,
        memory: memory_models.SessionStoryMemory,
    ) -> StoryMemoryDetail:
        summary = self._story_memory_summary(memory)
        return StoryMemoryDetail(
            **summary.__dict__,
            text=memory.text,
        )

    def _persistent_memory_summary(
        self,
        memory: PersistentMemoryReferenceItem,
    ) -> PersistentMemorySummary:
        return PersistentMemorySummary(
            id=memory.memory_id,
            title=(
                f"{_memory_kind_label(memory.memory_kind)}"
                f" · rev {memory.revision_number}"
            ),
            excerpt=_excerpt(memory.text, self._policy.excerpt_limit),
            memory_kind=memory.memory_kind,
            epistemic_status=memory.epistemic_status,
            salience=memory.salience,
            evidence=tuple(
                EvidenceReference(
                    turn_id=item.turn_id,
                    message_id=item.message_id,
                )
                for item in memory.evidence
            ),
            revision_number=memory.revision_number,
            updated_at=memory.updated_at,
        )

    def _persistent_memory_detail(
        self,
        memory: PersistentMemoryReferenceItem,
    ) -> PersistentMemoryDetail:
        summary = self._persistent_memory_summary(memory)
        return PersistentMemoryDetail(
            **summary.__dict__,
            text=memory.text,
        )


def _character_summary(
    character,  # noqa: ANN001
    *,
    player_character_id: int | None,
) -> CharacterSummary:
    return CharacterSummary(
        id=character.character_id,
        name=character.name,
        description=character.description,
        is_player=player_character_id == character.character_id,
        details_count=character.details_count,
        version=character.version,
        updated_at=character.updated_at,
    )


def _character_detail_summary(detail) -> CharacterDetailSummary:  # noqa: ANN001
    return CharacterDetailSummary(
        id=detail.detail_id,
        title=detail.name,
        version=detail.version,
        updated_at=detail.updated_at,
    )


def _status_summary(table) -> StatusTableSummary:  # noqa: ANN001
    return StatusTableSummary(
        id=table.table_id,
        name=table.name,
        description=table.description,
        kind=str(table.status_kind),
        character_id=table.associated_character_id,
        character_name=table.associated_character_name,
        version=table.version,
        updated_at=table.updated_at,
    )


def _summary_summary(
    document: ResolvedSummaryDocument,
    *,
    excerpt_limit: int,
) -> SummarySummary:
    return SummarySummary(
        id=document.summary_id,
        title=document.title,
        excerpt=_excerpt(document.excerpt, excerpt_limit),
        kind=document.kind,
        turn_start=document.turn_start,
        turn_end=document.turn_end,
        time=document.time,
        location=document.location,
        characters=document.characters,
        updated_at=document.updated_at,
    )


def _summary_detail(
    document: ResolvedSummaryDocument,
    *,
    excerpt_limit: int,
) -> SummaryDetail:
    summary = _summary_summary(document, excerpt_limit=excerpt_limit)
    return SummaryDetail(**summary.__dict__, text=document.text)


def _data_page(  # noqa: ANN001
    result,
    project: Callable[[object], U],
) -> ReferencePage[U]:
    return _reference_page(
        items=tuple(project(item) for item in result.items),
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


def _sequence_page(
    items: Sequence[T],
    *,
    page: int,
    page_size: int,
    project: Callable[[T], U],
) -> ReferencePage[U]:
    total = len(items)
    start = (page - 1) * page_size
    selected = items[start : start + page_size]
    return _reference_page(
        items=tuple(project(item) for item in selected),
        page=page,
        page_size=page_size,
        total=total,
    )


def _total_pages(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0


def _reference_page(
    *,
    items: tuple[T, ...],
    page: int,
    page_size: int,
    total: int,
) -> ReferencePage[T]:
    total_pages = _total_pages(total, page_size)
    if page > 1 and page > total_pages:
        raise SessionReferenceNotFoundError(
            "Reference list changed while navigating pages"
        )
    return ReferencePage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _normalized_locator(
    locator: SessionReferenceLocator,
) -> SessionReferenceLocator:
    if not isinstance(locator, SessionReferenceLocator):
        raise TypeError("locator must be a SessionReferenceLocator")
    session_id = str(locator.session_id or "").strip()
    workspace_id = str(locator.workspace_id or "").strip()
    if not session_id:
        raise ValueError("locator.session_id must not be empty")
    if not workspace_id:
        raise ValueError("locator.workspace_id must not be empty")
    story_id = _positive_id(locator.story_id, "locator.story_id")
    return SessionReferenceLocator(
        session_id=session_id,
        workspace_id=workspace_id,
        story_id=story_id,
    )


def _positive_id(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _excerpt(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _memory_kind_label(kind: str) -> str:
    return _MEMORY_KIND_LABELS.get(kind, kind or "记忆")


def _story_memory_title(memory: memory_models.SessionStoryMemory) -> str:
    start = memory.source_turn_start
    end = memory.source_turn_end
    turn_label = f"Turn {start}" if start == end else f"Turn {start}–{end}"
    return f"{_memory_kind_label(memory.memory_kind)} · {turn_label}"


def _evidence(
    items: Sequence[memory_models.MemoryEvidence],
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(turn_id=item.turn_id, message_id=item.message_id)
        for item in items
    )


__all__ = ["SessionReferenceApplicationService"]
