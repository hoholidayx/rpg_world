"""Narrow data backends owned by the Play API runtime."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.plot_scheduler.management import (
    PlotScheduleManagementService,
)
from rpg_core.rp_modules.plot_scheduler.story_projection import (
    PlotStoryProjectionService,
)
from rpg_core.scene.status import SceneStatusService
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_core.summary.reader import SummaryDocument, SummaryReader
from rpg_data import models
from rpg_data.model.runtime_maintenance import RuntimeMaintenanceItem
from rpg_data.model import status as status_models
from rpg_data.services import (
    CatalogService,
    CharacterManagementService,
    LorebookManagementService,
    MessageDataService,
    NarrativeOutcomeDataService,
    PlotSchedulingDataService,
    RuntimeMaintenanceDataService,
    SessionDataService,
    StoryMemoryDataService,
)
from rpg_memory.story.application import StoryMemoryApplicationService


class PlayCatalogBackend:
    """Workspace, Story, Session catalog, Composer, and RP Module access."""

    def __init__(
        self,
        *,
        catalog: CatalogService,
        sessions: SessionDataService,
        session_composer: SessionComposerApplicationService,
        rp_modules: RPModuleApplicationService,
    ) -> None:
        self._catalog = catalog
        self._session_catalog = SessionCatalogService(sessions)
        self._session_roles = SessionRoleService(sessions)
        self.session_composer = session_composer
        self.rp_modules = rp_modules

    def _ready_session(self, session_id: str) -> models.Session | None:
        session = self._catalog.get_session(session_id)
        if session is None or session.lifecycle != models.SESSION_LIFECYCLE_READY:
            return None
        return session

    async def list_workspaces(self) -> list[dict[str, object]]:
        return [
            _workspace_summary(workspace)
            for workspace in self._catalog.list_workspaces()
        ]

    async def list_stories(self, workspace: str) -> list[dict[str, object]] | None:
        stories = self._catalog.list_stories(workspace)
        if stories is None:
            return None
        return [_story_summary(story) for story in stories]

    async def create_story(
        self,
        workspace: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        openings: Sequence[models.StoryOpeningInput] = (),
    ) -> dict[str, object] | None:
        story = self._session_catalog.create_story(
            workspace,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            openings=openings,
        )
        if story is None:
            return None
        return _story_summary(story)

    async def update_story(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        openings: Sequence[models.StoryOpeningInput] | None = None,
    ) -> dict[str, object] | None:
        story = self._session_catalog.update_story(
            workspace,
            story_id,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            openings=openings,
        )
        if story is None:
            return None
        return _story_summary(story)

    async def list_session_opening_options(
        self,
        session_id: str,
        player_character_id: int,
    ) -> dict[str, object] | None:
        session = self._ready_session(session_id)
        if session is None:
            return None
        options = self._session_roles.list_opening_options(
            session_id,
            player_character_id,
        )
        return {
            "can_select_opening": self._session_roles.can_select_opening(
                session_id
            ),
            "items": [
                {
                    "id": option.opening.id,
                    "title": option.opening.title,
                    "rendered_message": option.rendered_message,
                    "sort_order": option.opening.sort_order,
                }
                for option in options
            ],
        }

    async def list_sessions(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        sessions = self._catalog.list_sessions(workspace, story_id)
        if sessions is None:
            return None
        return [
            _session_summary(session, self._session_roles)
            for session in sessions
        ]

    async def get_session(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        session = self._ready_session(session_id)
        if session is None:
            return None
        return _session_summary(session, self._session_roles)


class PlaySessionReadBackend:
    """Committed Session history, annotations, Scene, Summary, and Memory."""

    def __init__(
        self,
        *,
        catalog: CatalogService,
        messages: MessageDataService,
        story_memory: StoryMemoryDataService,
        narrative_outcomes: NarrativeOutcomeDataService,
        plot_scheduling: PlotSchedulingDataService,
        scene: SceneStatusService,
    ) -> None:
        self._catalog = catalog
        self._messages = messages
        self._story_memory = StoryMemoryApplicationService(story_memory)
        self._narrative_outcomes = narrative_outcomes
        self._plot_scheduling = plot_scheduling
        self._scene = scene

    def _ready_session(self, session_id: str) -> models.Session | None:
        session = self._catalog.get_session(session_id)
        if session is None or session.lifecycle != models.SESSION_LIFECYCLE_READY:
            return None
        return session

    async def list_session_summaries(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        reader = SummaryReader(
            self._catalog.resolve_session_runtime_dir(session_id)
        )
        index = reader.read_index()
        turn_ranges = self._messages.list_summary_turn_ranges(session_id)
        return {
            "overall": (
                _summary_document_payload(index.overall, turn_ranges)
                if index.overall is not None
                else None
            ),
            "batches": [
                _summary_document_payload(document, turn_ranges)
                for document in reversed(index.batches)
            ],
        }

    async def get_session_summary(
        self,
        session_id: str,
        summary_key: str | int,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        reader = SummaryReader(
            self._catalog.resolve_session_runtime_dir(session_id)
        )
        document = reader.get(summary_key)
        if document is None:
            return None
        return _summary_document_payload(
            document,
            self._messages.list_summary_turn_ranges(session_id),
            include_markdown=True,
        )

    async def list_session_story_memories(
        self,
        session_id: str,
        *,
        page: int,
        page_size: int,
        memory_kind: str | None,
        dream_processed: bool | None,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        result = self._story_memory.list_page(
            session_id,
            page=page,
            page_size=page_size,
            memory_kind=memory_kind,
            dream_processed=dream_processed,
        )
        stats = result.stats
        return {
            "items": [
                {
                    "id": item.id,
                    "text": item.text,
                    "memoryKind": item.memory_kind,
                    "epistemicStatus": item.epistemic_status,
                    "salience": item.salience,
                    "sourceTurnStart": item.source_turn_start,
                    "sourceTurnEnd": item.source_turn_end,
                    "dreamProcessed": item.dream_processed,
                    "evidence": [
                        {
                            "messageId": evidence.message_id,
                            "turnId": evidence.turn_id,
                        }
                        for evidence in item.evidence
                    ],
                    "version": item.version,
                    "createdAt": item.created_at,
                    "updatedAt": item.updated_at,
                }
                for item in result.items
            ],
            "page": result.page,
            "pageSize": result.page_size,
            "total": result.total,
            "stats": {
                "totalFacts": stats.total_facts,
                "dreamProcessedFacts": stats.dream_processed_facts,
                "pendingDreamFacts": stats.pending_dream_facts,
                "unprocessedSourceTurns": self._messages.count_distinct_turns(
                    session_id,
                    excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
                    story_memory_processed=False,
                ),
                "latestUpdatedAt": stats.latest_updated_at or None,
            },
        }

    def list_turn_window(
        self,
        session_id: str,
        *,
        limit: int,
        before_turn_id: int | None,
        after_turn_id: int | None,
    ) -> list[object]:
        return list(
            self._messages.list_turn_window(
                session_id,
                limit=limit,
                before_turn_id=before_turn_id,
                after_turn_id=after_turn_id,
            )
        )

    def list_turn(self, session_id: str, turn_id: int) -> list[object]:
        return list(self._messages.list_turn(session_id, turn_id))

    def latest_turn_id(self, session_id: str) -> int | None:
        return self._messages.latest_turn_id(session_id)

    def has_turn_before(self, session_id: str, turn_id: int) -> bool:
        return self._messages.has_turn_before(session_id, turn_id)

    def has_turn_after(self, session_id: str, turn_id: int) -> bool:
        return self._messages.has_turn_after(session_id, turn_id)

    def list_outcomes_for_turns(
        self,
        session_id: str,
        turn_ids: Sequence[int],
    ) -> list[object]:
        return list(
            self._narrative_outcomes.list_for_turns(session_id, turn_ids)
        )

    def list_plot_decisions_for_turns(
        self,
        session_id: str,
        turn_ids: Sequence[int],
    ) -> list[models.SessionPlotScheduleDecision]:
        return self._plot_scheduling.list_session_decisions_for_turns(
            session_id,
            turn_ids,
        )

    def get_scene_attrs(self, session_id: str) -> dict[str, str] | None:
        return self._scene.get_attrs(session_id)


class PlayRuntimeMaintenanceBackend:
    """Play-facing adapter for the typed runtime maintenance boundary."""

    def __init__(self, service: RuntimeMaintenanceDataService) -> None:
        self._service = service

    async def scan_unindexed_runtime(self, workspace: str) -> dict[str, list[dict[str, str]]] | None:
        scan = self._service.scan_unindexed_runtime(workspace)
        if scan is None:
            return None
        return {
            "items": [_runtime_item_payload(item) for item in scan.items]
        }

    async def delete_unindexed_runtime_item(self, item: dict[str, str]) -> bool | None:
        return await self.delete_unindexed_runtime_items([item])

    async def delete_unindexed_runtime_items(self, items: list[dict[str, str]]) -> bool | None:
        try:
            targets = tuple(_runtime_item_from_payload(item) for item in items)
        except (KeyError, TypeError, ValueError):
            return False
        result = self._service.delete_unindexed_runtime_items(targets)
        return None if result is None else result.matched


class PlayStoryAssetBackend:
    """Story assets, Status administration, and Plot projections."""

    def __init__(
        self,
        *,
        catalog: CatalogService,
        character_management: CharacterManagementService,
        lorebook_management: LorebookManagementService,
        status_administration: StatusTableAdministrationService,
        plot_management: PlotScheduleManagementService,
        plot_story_projection: PlotStoryProjectionService,
        scene: SceneStatusService,
    ) -> None:
        self._catalog = catalog
        self._character_management = character_management
        self._lorebook_management = lorebook_management
        self._status_administration = status_administration
        self.plot_management = plot_management
        self.plot_story_projection = plot_story_projection
        self._scene = scene

    def _ready_session(self, session_id: str) -> models.Session | None:
        session = self._catalog.get_session(session_id)
        if session is None or session.lifecycle != models.SESSION_LIFECYCLE_READY:
            return None
        return session

    def get_scene_attrs(self, session_id: str) -> dict[str, str] | None:
        return self._scene.get_attrs(session_id)

    async def list_characters(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        characters = self._character_management.list_characters(
            workspace,
            story_id,
        )
        if characters is None:
            return None
        return [
            _character_summary(
                character,
                self._character_management.list_details(
                    workspace,
                    story_id,
                    int(character.id),
                ) or [],
            )
            for character in characters
        ]

    async def create_character(
        self,
        workspace: str,
        story_id: int,
        *,
        name: str,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._character_management.create_character(
            workspace,
            story_id,
            name=name,
            description=description,
            sort_order=sort_order,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._character_management.list_details(
                workspace,
                story_id,
                int(character.id),
            ) or [],
        )

    async def get_character(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
    ) -> dict[str, object] | None:
        characters = self._character_management.list_characters(
            workspace,
            story_id,
        )
        if characters is None:
            return None
        for character in characters:
            if int(character.id) == int(character_id):
                return _character_summary(
                    character,
                    self._character_management.list_details(
                        workspace,
                        story_id,
                        int(character.id),
                    ) or [],
                )
        return None

    async def update_character(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._character_management.update_character(
            workspace,
            story_id,
            character_id,
            name=name,
            description=description,
            sort_order=sort_order,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._character_management.list_details(
                workspace,
                story_id,
                int(character.id),
            ) or [],
        )

    async def delete_character(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
    ) -> bool:
        return self._character_management.delete_character(
            workspace,
            story_id,
            character_id,
        )

    async def create_character_detail(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
        *,
        name: str,
        content: str = "",
        tags: list[str] | None = None,
        sort_order: int = 0,
    ) -> dict[str, object] | None:
        detail = self._character_management.create_detail(
            workspace,
            story_id,
            character_id,
            name=name,
            content=content,
            tags=tags or [],
            sort_order=sort_order,
        )
        if detail is None:
            return None
        return _character_detail_summary(detail)

    async def update_character_detail(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        detail = self._character_management.update_detail(
            workspace,
            story_id,
            character_id,
            detail_id,
            name=name,
            content=content,
            tags=tags,
            sort_order=sort_order,
        )
        if detail is None:
            return None
        return _character_detail_summary(detail)

    async def delete_character_detail(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
        detail_id: int,
    ) -> bool:
        return self._character_management.delete_detail(
            workspace,
            story_id,
            character_id,
            detail_id,
        )

    async def list_lorebook_entries(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        entries = self._lorebook_management.list_entries(workspace, story_id)
        if entries is None:
            return None
        return [_lorebook_entry_summary(entry) for entry in entries]

    async def create_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        *,
        name: str,
        content: str = "",
        description: str = "",
        tags: list[str] | None = None,
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._lorebook_management.create_entry(
            workspace,
            story_id,
            name=name,
            content=content,
            description=description,
            tags=tags or [],
            sort_order=sort_order,
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def get_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        entry_id: int,
    ) -> dict[str, object] | None:
        entries = self._lorebook_management.list_entries(workspace, story_id)
        if entries is None:
            return None
        for entry in entries:
            if int(entry.id) == int(entry_id):
                return _lorebook_entry_summary(entry)
        return None

    async def update_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        sort_order: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._lorebook_management.update_entry(
            workspace,
            story_id,
            entry_id,
            name=name,
            content=content,
            description=description,
            tags=tags,
            sort_order=sort_order,
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def delete_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        entry_id: int,
    ) -> bool:
        return self._lorebook_management.delete_entry(
            workspace,
            story_id,
            entry_id,
        )

    async def list_story_status_tables(
        self,
        workspace: str,
        story_id: int,
        status_kind: str | None = None,
    ) -> list[dict[str, object]] | None:
        stories = self._catalog.list_stories(workspace)
        if stories is None or not any(int(story.id) == int(story_id) for story in stories):
            return None
        return [
            _story_status_table_summary(table)
            for table in self._status_administration.list_story_tables(
                workspace,
                story_id,
                status_kind=status_kind,
            )
        ]

    async def create_story_status_table(
        self,
        workspace: str,
        story_id: int,
        *,
        name: str,
        status_kind: str,
        document: status_models.StatusTableDocument,
        story_character_id: int | None = None,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        try:
            table = self._status_administration.create_story_table(
                workspace,
                story_id,
                name,
                status_kind=status_kind,
                document=document,
                story_character_id=story_character_id,
                description=description,
                sort_order=sort_order,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
        except FileNotFoundError:
            return None
        return _story_status_table_summary(table)

    async def update_story_status_table(
        self,
        workspace: str,
        story_id: int,
        story_status_table_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        document: status_models.StatusTableDocument | None = None,
        story_character_id: int | None = None,
        update_story_character: bool = False,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        try:
            table = self._status_administration.update_story_table(
                workspace,
                story_id,
                story_status_table_id,
                name=name,
                status_kind=status_kind,
                document=document,
                story_character_id=story_character_id,
                update_story_character=update_story_character,
                description=description,
                sort_order=sort_order,
            )
        except FileNotFoundError:
            return None
        return _story_status_table_summary(table)

    async def delete_story_status_table(
        self,
        workspace: str,
        story_id: int,
        story_status_table_id: int,
    ) -> bool | None:
        try:
            self._status_administration.delete_story_table(
                workspace,
                story_id,
                story_status_table_id,
            )
        except FileNotFoundError:
            return None
        return True

    async def list_session_status_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
    ) -> list[dict[str, object]] | None:
        if self._ready_session(session_id) is None:
            return None
        return [
            _session_status_table_summary(table)
            for table in self._status_administration.list_session_tables(
                session_id,
                status_kind=status_kind,
            )
        ]

    async def create_session_status_table(
        self,
        session_id: str,
        *,
        name: str,
        status_kind: str,
        document: status_models.StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        table = self._status_administration.create_session_table(
            session_id,
            name,
            status_kind=status_kind,
            document=document,
            description=description,
            sort_order=sort_order,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        return _session_status_table_summary(table)

    async def update_session_status_table(
        self,
        session_id: str,
        table_id: int,
        *,
        name: str | None = None,
        document: status_models.StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        try:
            table = self._status_administration.update_session_table(
                session_id,
                table_id,
                name=name,
                document=document,
                description=description,
                sort_order=sort_order,
            )
        except FileNotFoundError:
            return None
        return _session_status_table_summary(table)

    async def delete_session_status_table(self, session_id: str, table_id: int) -> bool | None:
        if self._ready_session(session_id) is None:
            return None
        try:
            self._status_administration.delete_session_table(session_id, table_id)
        except FileNotFoundError:
            return None
        return True


def _workspace_summary(workspace: models.Workspace) -> dict[str, object]:
    description = str(workspace.description or "")
    return {
        "id": str(workspace.id),
        "name": str(workspace.name),
        "description": description or None,
    }


def _summary_document_payload(
    document: SummaryDocument,
    turn_ranges: dict[int, tuple[int, int]],
    *,
    include_markdown: bool = False,
) -> dict[str, object]:
    turn_start: int | None = None
    turn_end: int | None = None
    if document.batch_id is not None:
        turn_range = turn_ranges.get(document.batch_id)
        if turn_range is not None:
            turn_start, turn_end = turn_range
        elif (
            document.source_turn_start is not None
            and document.source_turn_end is not None
        ):
            turn_start = document.source_turn_start
            turn_end = document.source_turn_end
    elif document.kind == "overall":
        eligible_ranges = [
            turn_range
            for batch_id, turn_range in turn_ranges.items()
            if document.last_batch_id is None or batch_id <= document.last_batch_id
        ]
        if eligible_ranges:
            turn_start = min(item[0] for item in eligible_ranges)
            turn_end = max(item[1] for item in eligible_ranges)

    payload: dict[str, object] = {
        "kind": document.kind,
        "batch_id": document.batch_id,
        "last_batch_id": document.last_batch_id,
        "title": document.title,
        "excerpt": document.excerpt,
        "time": document.time or None,
        "location": document.location or None,
        "characters": list(document.characters),
        "turn_start": turn_start,
        "turn_end": turn_end,
        "updated_at": document.updated_at,
    }
    if include_markdown:
        payload["markdown"] = document.markdown
    return payload


def _story_summary(story: models.Story) -> dict[str, object]:
    return {
        "id": int(story.id),
        "workspace": str(story.workspace_id),
        "title": str(story.title),
        "summary": str(story.summary or "") or None,
        "story_prompt": str(story.story_prompt or ""),
        "openings": [
            {
                "id": opening.id,
                "title": opening.title,
                "message": opening.message,
                "sort_order": opening.sort_order,
            }
            for opening in story.openings
        ],
        "created_at": str(story.created_at),
        "updated_at": str(story.updated_at),
    }


def _session_summary(
    session: models.Session,
    role_service: SessionRoleService | None = None,
) -> dict[str, object]:
    player_state = _player_character_state(session, role_service)
    return {
        "id": str(session.id),
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "title": str(session.title or session.id),
        "description": str(session.description or "") or None,
        "player_character": player_state["player"],
        "player_character_status": player_state["status"],
        "story_opening_id": session.story_opening_id,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }


def _player_character_state(
    session: models.Session,
    role_service: SessionRoleService | None,
) -> dict[str, object]:
    if role_service is None:
        return {
            "status": PlayerCharacterBindingStatus.INVALID.value,
            "player": None,
        }
    state = role_service.get_state(str(session.id))
    return {
        "status": state.status.value,
        "player": _player_character_summary(state.player) if state.player is not None else None,
    }


def _player_character_summary(snapshot: models.SessionPlayerCharacterSnapshot) -> dict[str, object]:
    return {
        "character_id": int(snapshot.character_id),
        "story_id": int(snapshot.story_id),
        "name": str(snapshot.name),
        "avatar_url": str(snapshot.avatar_url or ""),
        "role_label": str(snapshot.role_label or ""),
        "updated_at": str(snapshot.updated_at or ""),
    }


def _character_summary(
    character: models.StoryCharacter,
    details: list[models.CharacterDetail],
) -> dict[str, object]:
    return {
        "id": int(character.id),
        "workspace_id": str(character.workspace_id),
        "story_id": int(character.story_id),
        "name": str(character.name),
        "description": str(character.description or ""),
        "sort_order": int(character.sort_order),
        "metadata": _parse_metadata(character.metadata_json),
        "details": [_character_detail_summary(detail) for detail in details],
        "version": int(character.version),
        "created_at": str(character.created_at),
        "updated_at": str(character.updated_at),
    }


def _character_detail_summary(detail: models.CharacterDetail) -> dict[str, object]:
    return {
        "id": int(detail.id),
        "story_character_id": int(detail.story_character_id),
        "name": str(detail.name),
        "content": str(detail.content or ""),
        "tags": list(_parse_tags(detail.tags_json)),
        "sort_order": int(detail.sort_order),
        "version": int(detail.version),
        "created_at": str(detail.created_at),
        "updated_at": str(detail.updated_at),
    }


def _lorebook_entry_summary(
    entry: models.StoryLorebookEntry,
) -> dict[str, object]:
    return {
        "id": int(entry.id),
        "workspace_id": str(entry.workspace_id),
        "story_id": int(entry.story_id),
        "name": str(entry.name),
        "content": str(entry.content or ""),
        "description": str(entry.description or ""),
        "tags": list(_parse_tags(entry.tags_json)),
        "sort_order": int(entry.sort_order),
        "metadata": _parse_metadata(entry.metadata_json),
        "version": int(entry.version),
        "created_at": str(entry.created_at),
        "updated_at": str(entry.updated_at),
    }


def _status_document_summary(
    document: status_models.StatusTableDocument,
) -> dict[str, object]:
    return {
        "key_column": document.key_column,
        "value_column": document.value_column,
        "rows": [
            {
                "key": row.key,
                "value": row.value,
                "runtime_key_locked": row.runtime_key_locked,
                "update_rule": row.update_rule,
                "metadata": dict(row.metadata),
            }
            for row in document.rows
        ],
        "metadata": dict(document.metadata),
    }


def _story_status_table_summary(
    table: status_models.StoryStatusTable,
) -> dict[str, object]:
    result = {
        "id": int(table.id),
        "workspace_id": str(table.workspace_id),
        "story_id": int(table.story_id),
        "story_character_id": table.story_character_id,
        "name": str(table.name),
        "status_kind": str(table.status_kind),
        "description": str(table.description or ""),
        "sort_order": int(table.sort_order),
        "metadata": _parse_metadata(table.metadata_json),
        "version": int(table.version),
        "created_at": str(table.created_at),
        "updated_at": str(table.updated_at),
    }
    result.update(_status_document_summary(table.document))
    return result


def _session_status_table_summary(
    table: status_models.SessionStatusTable,
) -> dict[str, object]:
    result = {
        "id": int(table.id),
        "session_id": str(table.session_id),
        "workspace_id": str(table.workspace_id),
        "story_id": int(table.story_id),
        "source_story_status_table_id": table.source_story_status_table_id,
        "origin": str(table.origin),
        "name": str(table.name),
        "status_kind": str(table.status_kind),
        "description": str(table.description or ""),
        "sort_order": int(table.sort_order),
        "metadata": _parse_metadata(table.metadata_json),
        "version": int(table.version),
        "created_at": str(table.created_at),
        "updated_at": str(table.updated_at),
    }
    result.update(_status_document_summary(table.document))
    return result


def _parse_tags(raw: str | None) -> tuple[str, ...]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, str))


def _parse_metadata(raw: str | None) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _runtime_item_payload(
    item: RuntimeMaintenanceItem,
) -> dict[str, str]:
    return {
        "category": item.category,
        "kind": item.kind,
        "workspace_id": item.workspace_id,
        "story_id": item.story_id,
        "session_id": item.session_id,
        "relative_path": item.relative_path,
        "path": item.path,
    }


def _runtime_item_from_payload(
    item: dict[str, str],
) -> RuntimeMaintenanceItem:
    return RuntimeMaintenanceItem(
        category=str(item["category"]),
        kind=str(item["kind"]),
        workspace_id=str(item["workspace_id"]),
        story_id=str(item.get("story_id", "")),
        session_id=str(item.get("session_id", "")),
        relative_path=str(item["relative_path"]),
        path=str(item["path"]),
    )


__all__ = [
    "PlayCatalogBackend",
    "PlayRuntimeMaintenanceBackend",
    "PlaySessionReadBackend",
    "PlayStoryAssetBackend",
]
