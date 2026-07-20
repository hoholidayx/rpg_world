from __future__ import annotations

from dataclasses import replace

from rpg_core.status.context_service import StatusContextService
from rpg_data.model.status import (
    SessionStatusMetadata,
    SessionStatusTable,
    StatusCharacterIdentity,
    StatusContextCandidate,
    StatusStoryMountIdentity,
    StatusTableDocument,
    StoryStatusMountSnapshot,
    parse_session_status_metadata,
    serialize_session_status_metadata,
)


def _table(metadata: SessionStatusMetadata) -> SessionStatusTable:
    return SessionStatusTable(
        id=7,
        session_id="session",
        workspace_id="workspace",
        story_id=1,
        source_table_id=11,
        origin="template_copy",
        name="角色状态",
        document=StatusTableDocument.from_rows(),
        metadata_json=serialize_session_status_metadata(metadata),
    )


class _Data:
    def __init__(self, candidate: StatusContextCandidate) -> None:
        self.candidate = candidate
        self.updates: list[SessionStatusMetadata] = []

    def list_context_candidates(self, session_id: str):
        assert session_id == "session"
        return [self.candidate]

    def update_table_metadata_for_session(
        self,
        session_id: str,
        table_id: int,
        metadata: SessionStatusMetadata,
    ) -> SessionStatusTable:
        assert (session_id, table_id) == ("session", 7)
        self.updates.append(metadata)
        return replace(
            self.candidate.table,
            metadata_json=serialize_session_status_metadata(metadata),
        )


def test_context_service_repairs_missing_character_name() -> None:
    metadata = SessionStatusMetadata().with_story_mount(
        StoryStatusMountSnapshot(
            mount_id=21,
            character_mount_id=31,
            character_id=41,
        )
    )
    identity = StatusCharacterIdentity(31, 41, "Alice")
    data = _Data(
        StatusContextCandidate(
            table=_table(metadata),
            referenced_character=identity,
        )
    )

    result = StatusContextService(data).list_tables("session")

    repaired = parse_session_status_metadata(result[0].metadata_json).story_mount
    assert repaired is not None
    assert repaired.character_name == "Alice"
    assert repaired.character_mount_id == 31
    assert len(data.updates) == 1


def test_context_service_excludes_identity_mismatch() -> None:
    metadata = SessionStatusMetadata().with_story_mount(
        StoryStatusMountSnapshot(
            mount_id=21,
            character_mount_id=31,
            character_id=41,
        )
    )
    data = _Data(
        StatusContextCandidate(
            table=_table(metadata),
            referenced_character=StatusCharacterIdentity(31, 99, "Bob"),
            current_story_mount=StatusStoryMountIdentity(
                mount_id=21,
                mount_origin="system_mount",
                character=StatusCharacterIdentity(31, 99, "Bob"),
            ),
        )
    )

    assert StatusContextService(data).list_tables("session") == []
    assert data.updates == []
