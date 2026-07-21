"""Data manager backend provider for Play API."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_core.summary.reader import SummaryDocument, SummaryReader
from rpg_data import models
from rpg_data.model import status as status_models
from rpg_data.bootstrap import (
    delete_unindexed_runtime_item,
    delete_unindexed_runtime_items,
    scan_unindexed_runtime_data,
)
from rpg_data.services import DataServiceGateway, get_data_service_gateway
from rpg_data.settings import get_database_path
from rp_memory.story_memory_service import StoryMemoryApplicationService


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else get_database_path()
        )
        self._gateway: DataServiceGateway = get_data_service_gateway(self._database_path)
        self._gateway.initialize()
        self._status_administration = StatusTableAdministrationService(
            self._gateway.status
        )

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        self._gateway.close()

    def _ready_session(self, session_id: str) -> models.Session | None:
        session = self._gateway.catalog.get_session(session_id)
        if session is None or session.lifecycle != models.SESSION_LIFECYCLE_READY:
            return None
        return session

    async def list_workspaces(self) -> list[dict[str, object]]:
        return [_workspace_summary(workspace) for workspace in self._gateway.catalog.list_workspaces()]

    async def list_stories(self, workspace: str) -> list[dict[str, object]] | None:
        stories = self._gateway.catalog.list_stories(workspace)
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
        story = SessionCatalogService(self._gateway.sessions).create_story(
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
        story = SessionCatalogService(self._gateway.sessions).update_story(
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
        role_service = SessionRoleService(self._gateway.sessions)
        options = role_service.list_opening_options(
            session_id,
            player_character_id,
        )
        return {
            "can_select_opening": role_service.can_select_opening(session_id),
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
        sessions = self._gateway.catalog.list_sessions(workspace, story_id)
        if sessions is None:
            return None
        return [_session_summary(session, self._gateway) for session in sessions]

    async def create_session(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str = "",
        description: str = "",
    ) -> dict[str, object] | None:
        session = SessionCatalogService(self._gateway.sessions).create_session(
            workspace,
            story_id,
            title=title,
            description=description,
        )
        if session is None:
            return None
        return _session_summary(session, self._gateway)

    async def get_session(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        session = self._ready_session(session_id)
        if session is None:
            return None
        return _session_summary(session, self._gateway)

    async def list_session_summaries(
        self,
        session_id: str,
    ) -> dict[str, object] | None:
        if self._ready_session(session_id) is None:
            return None
        reader = SummaryReader(
            self._gateway.catalog.resolve_session_runtime_dir(session_id)
        )
        index = reader.read_index()
        turn_ranges = self._gateway.messages.list_summary_turn_ranges(session_id)
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
            self._gateway.catalog.resolve_session_runtime_dir(session_id)
        )
        document = reader.get(summary_key)
        if document is None:
            return None
        return _summary_document_payload(
            document,
            self._gateway.messages.list_summary_turn_ranges(session_id),
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
        result = StoryMemoryApplicationService(
            self._gateway.story_memory
        ).list_page(
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
                "unprocessedSourceTurns": self._gateway.messages.count_distinct_turns(
                    session_id,
                    excluded_roles=(models.MESSAGE_ROLE_SYSTEM,),
                    story_memory_processed=False,
                ),
                "latestUpdatedAt": stats.latest_updated_at or None,
            },
        }

    async def scan_unindexed_runtime(self, workspace: str) -> dict[str, list[dict[str, str]]] | None:
        return scan_unindexed_runtime_data(self._gateway.database, workspace)

    async def delete_unindexed_runtime_item(self, item: dict[str, str]) -> bool | None:
        return delete_unindexed_runtime_item(self._gateway.database, item)

    async def delete_unindexed_runtime_items(self, items: list[dict[str, str]]) -> bool | None:
        return delete_unindexed_runtime_items(self._gateway.database, items)

    async def list_characters(self, workspace: str) -> list[dict[str, object]] | None:
        characters = self._gateway.character_management.list_characters(workspace)
        if characters is None:
            return None
        return [
            _character_summary(
                character,
                self._gateway.character_management.list_details(workspace, int(character.id)) or [],
            )
            for character in characters
        ]

    async def create_character(
        self,
        workspace: str,
        *,
        name: str,
        personality: str = "",
        content: str = "",
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.create_character(
            workspace,
            name=name,
            personality=personality,
            content=content,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.id)) or [],
        )

    async def get_character(
        self,
        workspace: str,
        character_id: int,
    ) -> dict[str, object] | None:
        characters = self._gateway.character_management.list_characters(workspace)
        if characters is None:
            return None
        for character in characters:
            if int(character.id) == int(character_id):
                return _character_summary(
                    character,
                    self._gateway.character_management.list_details(workspace, int(character.id)) or [],
                )
        return None

    async def update_character(
        self,
        workspace: str,
        character_id: int,
        *,
        name: str | None = None,
        personality: str | None = None,
        content: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.update_character(
            workspace,
            character_id,
            name=name,
            personality=personality,
            content=content,
            metadata=metadata,
        )
        if character is None:
            return None
        return _character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.id)) or [],
        )

    async def delete_character(
        self,
        workspace: str,
        character_id: int,
    ) -> bool:
        return self._gateway.character_management.delete_character(workspace, character_id)

    async def create_character_detail(
        self,
        workspace: str,
        character_id: int,
        *,
        name: str,
        content: str = "",
        tags: list[str] | None = None,
        sort_order: int = 0,
    ) -> dict[str, object] | None:
        detail = self._gateway.character_management.create_detail(
            workspace,
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
        character_id: int,
        detail_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        detail = self._gateway.character_management.update_detail(
            workspace,
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
        character_id: int,
        detail_id: int,
    ) -> bool:
        return self._gateway.character_management.delete_detail(workspace, character_id, detail_id)

    async def list_story_characters(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        characters = self._gateway.character_management.list_story_characters(workspace, story_id)
        if characters is None:
            return None
        return [
            _mounted_character_summary(
                item,
                self._gateway.character_management.list_details(workspace, int(item.character.id)) or [],
            )
            for item in characters
        ]

    async def mount_character(
        self,
        workspace: str,
        story_id: int,
        character_id: int,
    ) -> dict[str, object] | None:
        character = self._gateway.character_management.mount_character(workspace, story_id, character_id)
        if character is None:
            return None
        return _mounted_character_summary(
            character,
            self._gateway.character_management.list_details(workspace, int(character.character.id)) or [],
        )

    async def unmount_character(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        return self._gateway.character_management.unmount_character(workspace, story_id, mount_id)

    async def list_lorebook_entries(self, workspace: str) -> list[dict[str, object]] | None:
        entries = self._gateway.lorebook_management.list_entries(workspace)
        if entries is None:
            return None
        return [_lorebook_entry_summary(entry) for entry in entries]

    async def create_lorebook_entry(
        self,
        workspace: str,
        *,
        name: str,
        content: str = "",
        description: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.create_entry(
            workspace,
            name=name,
            content=content,
            description=description,
            tags=tags or [],
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def get_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
    ) -> dict[str, object] | None:
        entries = self._gateway.lorebook_management.list_entries(workspace)
        if entries is None:
            return None
        for entry in entries:
            if int(entry.id) == int(entry_id):
                return _lorebook_entry_summary(entry)
        return None

    async def update_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.update_entry(
            workspace,
            entry_id,
            name=name,
            content=content,
            description=description,
            tags=tags,
            metadata=metadata,
        )
        if entry is None:
            return None
        return _lorebook_entry_summary(entry)

    async def delete_lorebook_entry(
        self,
        workspace: str,
        entry_id: int,
    ) -> bool:
        return self._gateway.lorebook_management.delete_entry(workspace, entry_id)

    async def list_story_lorebook_entries(
        self,
        workspace: str,
        story_id: int,
    ) -> list[dict[str, object]] | None:
        entries = self._gateway.lorebook_management.list_story_entries(workspace, story_id)
        if entries is None:
            return None
        return [_mounted_lorebook_entry_summary(entry) for entry in entries]

    async def mount_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        entry_id: int,
    ) -> dict[str, object] | None:
        entry = self._gateway.lorebook_management.mount_entry(workspace, story_id, entry_id)
        if entry is None:
            return None
        return _mounted_lorebook_entry_summary(entry)

    async def get_lorebook_mount(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> dict[str, object] | None:
        entries = self._gateway.lorebook_management.list_story_entries(workspace, story_id)
        if entries is None:
            return None
        for entry in entries:
            if int(entry.mount.id) == int(mount_id):
                return _mounted_lorebook_entry_summary(entry)
        return None

    async def unmount_lorebook_entry(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        return self._gateway.lorebook_management.unmount_entry(workspace, story_id, mount_id)

    async def list_status_templates(
        self,
        workspace: str,
        status_kind: str | None = None,
    ) -> list[dict[str, object]] | None:
        if not _workspace_exists(self._gateway, workspace):
            return None
        return [
            _status_template_summary(template)
            for template in self._status_administration.list_templates(
                workspace,
                status_kind=status_kind,
            )
        ]

    async def create_status_template(
        self,
        workspace: str,
        *,
        name: str,
        status_kind: str,
        document: status_models.StatusTableDocument,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        if not _workspace_exists(self._gateway, workspace):
            return None
        template = self._status_administration.create_template(
            workspace,
            name,
            status_kind=status_kind,
            document=document,
            description=description,
            sort_order=sort_order,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        return _status_template_summary(template)

    async def update_status_template(
        self,
        workspace: str,
        template_id: int,
        *,
        name: str | None = None,
        status_kind: str | None = None,
        document: status_models.StatusTableDocument | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, object] | None:
        try:
            updated = self._status_administration.update_template(
                workspace,
                template_id,
                name=name,
                status_kind=status_kind,
                document=document,
                description=description,
                sort_order=sort_order,
            )
        except FileNotFoundError:
            return None
        return _status_template_summary(updated)

    async def delete_status_template(self, workspace: str, template_id: int) -> bool | None:
        try:
            self._status_administration.delete_template(workspace, template_id)
        except FileNotFoundError:
            return None
        return True

    async def list_story_status_mounts(self, workspace: str, story_id: int) -> list[dict[str, object]] | None:
        stories = self._gateway.catalog.list_stories(workspace)
        if stories is None or not any(int(story.id) == int(story_id) for story in stories):
            return None
        return [
            _status_mount_summary(mount)
            for mount in self._status_administration.list_story_mounts(
                workspace,
                story_id,
            )
        ]

    async def mount_status_template(
        self,
        workspace: str,
        story_id: int,
        template_id: int,
        *,
        character_mount_id: int | None = None,
        sort_order: int = 0,
    ) -> dict[str, object] | None:
        try:
            mount = self._status_administration.mount_template(
                workspace,
                story_id,
                template_id,
                character_mount_id=character_mount_id,
                sort_order=sort_order,
            )
        except FileNotFoundError:
            return None
        return _status_mount_summary(mount)

    async def create_story_status_template(
        self,
        workspace: str,
        story_id: int,
        *,
        name: str,
        status_kind: str,
        document: status_models.StatusTableDocument,
        character_mount_id: int | None = None,
        description: str = "",
        sort_order: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        try:
            mount = self._status_administration.create_story_template(
                workspace,
                story_id,
                name,
                status_kind=status_kind,
                document=document,
                character_mount_id=character_mount_id,
                description=description,
                sort_order=sort_order,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
        except FileNotFoundError:
            return None
        return _status_mount_summary(mount)

    async def update_story_status_mount(
        self,
        workspace: str,
        story_id: int,
        mount_id: int,
        *,
        character_mount_id: int | None,
    ) -> dict[str, object] | None:
        try:
            mount = self._status_administration.update_story_mount_character(
                workspace,
                story_id,
                mount_id,
                character_mount_id=character_mount_id,
            )
        except FileNotFoundError:
            return None
        return _status_mount_summary(mount)

    async def unmount_status_template(self, workspace: str, story_id: int, mount_id: int) -> bool | None:
        try:
            self._status_administration.unmount_template(
                workspace,
                story_id,
                mount_id,
            )
        except FileNotFoundError:
            return None
        return True

    async def delete_story_status_template(self, workspace: str, story_id: int, mount_id: int) -> bool | None:
        try:
            self._status_administration.delete_story_template(
                workspace,
                story_id,
                mount_id,
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


def _workspace_exists(gateway: DataServiceGateway, workspace: str) -> bool:
    return any(item.id == workspace for item in gateway.catalog.list_workspaces())


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


def _session_summary(session: models.Session, gateway: DataServiceGateway | None = None) -> dict[str, object]:
    player_state = _player_character_state(session, gateway)
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


def _player_character_state(session: models.Session, gateway: DataServiceGateway | None) -> dict[str, object]:
    if gateway is None:
        return {
            "status": PlayerCharacterBindingStatus.INVALID.value,
            "player": None,
        }
    state = SessionRoleService(gateway.sessions).get_state(str(session.id))
    return {
        "status": state.status.value,
        "player": _player_character_summary(state.player) if state.player is not None else None,
    }


def _player_character_summary(snapshot: models.SessionPlayerCharacterSnapshot) -> dict[str, object]:
    return {
        "character_id": int(snapshot.character_id),
        "mount_id": int(snapshot.mount_id),
        "story_id": int(snapshot.story_id),
        "name": str(snapshot.name),
        "avatar_url": str(snapshot.avatar_url or ""),
        "role_label": str(snapshot.role_label or ""),
        "updated_at": str(snapshot.updated_at or ""),
    }


def _character_summary(
    character: models.Character,
    details: list[models.CharacterDetail],
) -> dict[str, object]:
    return {
        "id": int(character.id),
        "workspace_id": str(character.workspace_id),
        "name": str(character.name),
        "personality": str(character.personality or ""),
        "content": str(character.content or ""),
        "metadata": _parse_metadata(character.metadata_json),
        "details": [_character_detail_summary(detail) for detail in details],
        "version": int(character.version),
        "created_at": str(character.created_at),
        "updated_at": str(character.updated_at),
    }


def _character_detail_summary(detail: models.CharacterDetail) -> dict[str, object]:
    return {
        "id": int(detail.id),
        "character_id": int(detail.character_id),
        "name": str(detail.name),
        "content": str(detail.content or ""),
        "tags": list(_parse_tags(detail.tags_json)),
        "sort_order": int(detail.sort_order),
        "version": int(detail.version),
        "created_at": str(detail.created_at),
        "updated_at": str(detail.updated_at),
    }


def _mounted_character_summary(
    detail: models.StoryCharacterDetail,
    details: list[models.CharacterDetail],
) -> dict[str, object]:
    result = _character_summary(detail.character, details)
    result.update(
        {
            "mount_id": int(detail.mount.id),
            "story_id": int(detail.mount.story_id),
        }
    )
    return result


def _lorebook_entry_summary(entry: models.LorebookEntry) -> dict[str, object]:
    return {
        "id": int(entry.id),
        "workspace_id": str(entry.workspace_id),
        "name": str(entry.name),
        "content": str(entry.content or ""),
        "description": str(entry.description or ""),
        "tags": list(_parse_tags(entry.tags_json)),
        "metadata": _parse_metadata(entry.metadata_json),
        "version": int(entry.version),
        "created_at": str(entry.created_at),
        "updated_at": str(entry.updated_at),
    }


def _mounted_lorebook_entry_summary(detail: models.StoryLorebookEntryDetail) -> dict[str, object]:
    result = _lorebook_entry_summary(detail.entry)
    result.update(
        {
            "mount_id": int(detail.mount.id),
            "story_id": int(detail.mount.story_id),
        }
    )
    return result


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
                "metadata": dict(row.metadata),
                "update_frequency": row.update_frequency,
                "update_rule": row.update_rule,
                "deferred_interval_turns": row.deferred_interval_turns,
            }
            for row in document.rows
        ],
        "metadata": dict(document.metadata),
    }


def _status_template_summary(
    template: status_models.StatusTableTemplate,
) -> dict[str, object]:
    result = {
        "id": int(template.id),
        "workspace_id": str(template.workspace_id),
        "name": str(template.name),
        "status_kind": str(template.status_kind),
        "description": str(template.description or ""),
        "sort_order": int(template.sort_order),
        "metadata": _parse_metadata(template.metadata_json),
        "version": int(template.version),
        "created_at": str(template.created_at),
        "updated_at": str(template.updated_at),
    }
    result.update(_status_document_summary(template.document))
    return result


def _status_mount_summary(
    mount: status_models.StoryStatusTable,
) -> dict[str, object]:
    return {
        "id": int(mount.id),
        "workspace_id": str(mount.workspace_id),
        "story_id": int(mount.story_id),
        "status_table_id": int(mount.status_table_id),
        "character_mount_id": mount.story_character_mount_id,
        "mount_origin": str(mount.mount_origin),
        "table_name": str(mount.table_name),
        "status_kind": str(mount.status_kind),
        "description": str(mount.description or ""),
        "sort_order": int(mount.sort_order),
        "metadata": _parse_metadata(mount.metadata_json),
        "version": int(mount.version),
        "created_at": str(mount.created_at),
        "updated_at": str(mount.updated_at),
    }


def _session_status_table_summary(
    table: status_models.SessionStatusTable,
) -> dict[str, object]:
    result = {
        "id": int(table.id),
        "session_id": str(table.session_id),
        "workspace_id": str(table.workspace_id),
        "story_id": int(table.story_id),
        "source_table_id": table.source_table_id,
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
