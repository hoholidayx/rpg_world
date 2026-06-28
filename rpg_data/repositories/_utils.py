"""Shared helpers for Peewee repositories."""

from __future__ import annotations

from typing import Any, TypeVar

from peewee import SQL, DoesNotExist, Model

from rpg_data import models
from rpg_data.repositories import records

ModelT = TypeVar("ModelT", bound=Model)


def get_or_none(model: type[ModelT], row_id: Any) -> ModelT | None:
    try:
        return model.get_by_id(row_id)
    except DoesNotExist:
        return None


def update_timestamp(model: type[ModelT], row_id: Any) -> ModelT | None:
    updated = (
        model.update(updated_at=SQL("CURRENT_TIMESTAMP"))
        .where(model._meta.primary_key == row_id)
        .execute()
    )
    if not updated:
        return None
    return get_or_none(model, row_id)


def to_workspace(row: records.WorkspaceRecord) -> models.Workspace:
    return models.Workspace(
        id=str(row.id),
        name=str(row.name),
        root_path=str(row.root_path),
        description=str(row.description or ""),
        enabled=bool(row.enabled),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story(row: records.StoryRecord) -> models.Story:
    return models.Story(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        title=str(row.title),
        summary=str(row.summary or ""),
        description=str(row.description or ""),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session(row: records.SessionRecord) -> models.Session:
    profile = getattr(row, "session_profile", None)
    if profile is None:
        try:
            profile = row.profile.get()
        except Exception:
            profile = None
    return models.Session(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        state_json=str(row.state_json or "{}"),
        story_memory_last_turn_id=int(row.story_memory_last_turn_id),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
        title=str(profile.title or "") if profile is not None else "",
        description=str(profile.description or "") if profile is not None else "",
        profile_metadata_json=str(profile.metadata_json or "{}") if profile is not None else "{}",
        profile_created_at=str(profile.created_at) if profile is not None else "",
        profile_updated_at=str(profile.updated_at) if profile is not None else "",
    )


def to_session_profile(row: records.SessionProfileRecord) -> models.SessionProfile:
    return models.SessionProfile(
        session_id=str(row.session_id),
        title=str(row.title or ""),
        description=str(row.description or ""),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_message(
    row: records.SessionMessageRecord | records.SessionBackupMessageRecord,
) -> models.SessionMessage:
    return models.SessionMessage(
        id=int(row.id),
        session_id=str(row.session_id),
        role=str(row.role),
        content=str(row.content or ""),
        turn_id=int(row.turn_id),
        seq_in_turn=int(row.seq_in_turn),
        tool_call_id=str(row.tool_call_id or ""),
        tool_calls_json=str(row.tool_calls_json or ""),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_story_memory(row: records.SessionStoryMemoryRecord) -> models.SessionStoryMemory:
    return models.SessionStoryMemory(
        id=int(row.id),
        session_id=str(row.session_id),
        turn_id=int(row.turn_id),
        text=str(row.text or ""),
        dream_processed=bool(row.dream_processed),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_character(row: records.CharacterRecord) -> models.Character:
    return models.Character(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        name=str(row.name),
        personality=str(row.personality or ""),
        content=str(row.content or ""),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_character_detail(row: records.CharacterDetailRecord) -> models.CharacterDetail:
    return models.CharacterDetail(
        id=int(row.id),
        character_id=int(row.character_id),
        name=str(row.name),
        content=str(row.content or ""),
        tags_json=str(row.tags_json or "[]"),
        sort_order=int(row.sort_order),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_lorebook_entry(row: records.LorebookEntryRecord) -> models.LorebookEntry:
    return models.LorebookEntry(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        name=str(row.name),
        content=str(row.content or ""),
        description=str(row.description or ""),
        tags_json=str(row.tags_json or "[]"),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_character(row: records.StoryCharacterRecord) -> models.StoryCharacter:
    return models.StoryCharacter(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        character_id=int(row.character_id),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_lorebook_entry(row: records.StoryLorebookEntryRecord) -> models.StoryLorebookEntry:
    return models.StoryLorebookEntry(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        lorebook_entry_id=int(row.lorebook_entry_id),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )
