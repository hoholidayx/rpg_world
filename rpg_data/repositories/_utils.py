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
    return models.Session(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        session_key=str(row.session_key),
        title=str(row.title or ""),
        state_json=str(row.state_json or "{}"),
        last_story_turn_index=int(row.last_story_turn_index),
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
        enabled=bool(row.enabled),
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
        enabled=bool(row.enabled),
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
        enabled=bool(row.enabled),
        sort_order=int(row.sort_order),
        metadata_json=str(row.metadata_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )
