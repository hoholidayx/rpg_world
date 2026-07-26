"""Narrow structural contracts for the common Session reference service."""

from __future__ import annotations

from typing import ContextManager, Protocol

from rpg_core.summary.reference import ResolvedSummaryDocument
from rpg_data.model import memory as memory_models
from rpg_data.model.session_reference import (
    ReferenceDataPage,
    SessionReferenceCharacter,
    SessionReferenceCharacterDetail,
    SessionReferenceCharacterDetailItem,
    SessionReferenceScope as DataSessionReferenceScope,
    SessionReferenceStatusTableDetail,
    SessionReferenceStatusTableItem,
    SessionReferenceStatusOrder,
    SessionReferenceSummarySource,
)
from rpg_memory.persistent.reference import PersistentMemoryReferenceItem

from rpg_core.session.reference.models import (
    CharacterCard,
    CharacterDetail,
    CharacterDetailSummary,
    CharacterSummary,
    PersistentMemoryDetail,
    PersistentMemorySummary,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferenceScope,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    StoryMemorySummary,
    SummaryDetail,
    SummarySummary,
)


class SessionReferenceDataPort(Protocol):
    """Business-neutral, Session-scoped read models supplied by ``rpg_data``."""

    def transaction(self) -> ContextManager[None]: ...

    def require_scope(
        self,
        locator: SessionReferenceLocator,
    ) -> DataSessionReferenceScope: ...

    def list_characters(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int,
        page_size: int,
    ) -> ReferenceDataPage[SessionReferenceCharacter]: ...

    def get_character(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
    ) -> SessionReferenceCharacter | None: ...

    def list_character_order_ids(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[int, ...]: ...

    def list_character_details(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        *,
        page: int,
        page_size: int,
    ) -> ReferenceDataPage[SessionReferenceCharacterDetailItem]: ...

    def get_character_detail(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        detail_id: int,
    ) -> SessionReferenceCharacterDetail | None: ...

    def list_status_tables(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int,
        page_size: int,
        character_id: int | None = None,
        order: SessionReferenceStatusOrder | None = None,
    ) -> ReferenceDataPage[SessionReferenceStatusTableItem]: ...

    def get_status_table(
        self,
        locator: SessionReferenceLocator,
        table_id: int,
    ) -> SessionReferenceStatusTableDetail | None: ...

    def get_summary_source(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceSummarySource: ...


class SummaryReferenceProvider(Protocol):
    def list_summaries(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[ResolvedSummaryDocument, ...]: ...

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> ResolvedSummaryDocument | None: ...


class StoryMemoryReferenceProvider(Protocol):
    def list_reference_page(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int,
        page_size: int,
        memory_kind: str | None = None,
        dream_processed: bool | None = None,
    ) -> memory_models.SessionStoryMemoryPage: ...

    def get_reference(
        self,
        locator: SessionReferenceLocator,
        memory_id: int,
    ) -> memory_models.SessionStoryMemory | None: ...


class PersistentMemoryReferenceProvider(Protocol):
    def list_memories(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[PersistentMemoryReferenceItem, ...]: ...

    def get_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> PersistentMemoryReferenceItem | None: ...


class SessionReferenceReader(Protocol):
    """Async public boundary consumed by Telegram or future process adapters."""

    async def aclose(self) -> None:
        """Wait for in-flight reads and release reader-owned resources."""

        ...

    async def get_scope(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceScope: ...

    async def list_characters(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterSummary]: ...

    async def get_character(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
    ) -> CharacterCard: ...

    async def list_character_details(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterDetailSummary]: ...

    async def get_character_detail(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        detail_id: int,
    ) -> CharacterDetail: ...

    async def list_status_tables(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
        character_id: int | None = None,
    ) -> ReferencePage[StatusTableSummary]: ...

    async def get_status_table(
        self,
        locator: SessionReferenceLocator,
        table_id: int,
    ) -> StatusTableDetail: ...

    async def list_summaries(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[SummarySummary]: ...

    async def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> SummaryDetail: ...

    async def list_story_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[StoryMemorySummary]: ...

    async def get_story_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: int,
    ) -> StoryMemoryDetail: ...

    async def list_persistent_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[PersistentMemorySummary]: ...

    async def get_persistent_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> PersistentMemoryDetail: ...


__all__ = [
    "PersistentMemoryReferenceProvider",
    "SessionReferenceDataPort",
    "SessionReferenceReader",
    "StoryMemoryReferenceProvider",
    "SummaryReferenceProvider",
]
