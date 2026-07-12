"""Shared helpers for Peewee repositories."""

from __future__ import annotations

import json
from typing import Mapping, TypeVar

from peewee import SQL, DoesNotExist, Model

from rpg_data import models
from rpg_data.repositories import records

ModelT = TypeVar("ModelT", bound=Model)


def get_or_none(model: type[ModelT], row_id: object) -> ModelT | None:
    try:
        return model.get_by_id(row_id)
    except DoesNotExist:
        return None


def update_timestamp(model: type[ModelT], row_id: object) -> ModelT | None:
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
        story_prompt=str(row.story_prompt or ""),
        first_message=str(row.first_message or ""),
        main_llm_provider_key=(
            str(row.main_llm_provider_key)
            if row.main_llm_provider_key is not None
            else None
        ),
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
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
        title=str(profile.title or "") if profile is not None else "",
        description=str(profile.description or "") if profile is not None else "",
        main_llm_provider_key=(
            str(profile.main_llm_provider_key)
            if profile is not None and profile.main_llm_provider_key is not None
            else None
        ),
        player_character_id=(
            int(profile.player_character_id)
            if profile is not None and profile.player_character_id is not None
            else None
        ),
        player_character_snapshot_json=(
            str(profile.player_character_snapshot_json or "{}")
            if profile is not None
            else "{}"
        ),
        profile_metadata_json=str(profile.metadata_json or "{}") if profile is not None else "{}",
        profile_created_at=str(profile.created_at) if profile is not None else "",
        profile_updated_at=str(profile.updated_at) if profile is not None else "",
    )


def to_session_profile(row: records.SessionProfileRecord) -> models.SessionProfile:
    return models.SessionProfile(
        session_id=str(row.session_id),
        title=str(row.title or ""),
        description=str(row.description or ""),
        main_llm_provider_key=(
            str(row.main_llm_provider_key)
            if row.main_llm_provider_key is not None
            else None
        ),
        player_character_id=int(row.player_character_id) if row.player_character_id is not None else None,
        player_character_snapshot_json=str(row.player_character_snapshot_json or "{}"),
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
        summary_processed=bool(getattr(row, "summary_processed", False)),
        summary_batch_id=(
            int(getattr(row, "summary_batch_id"))
            if getattr(row, "summary_batch_id", None) is not None
            else None
        ),
        summary_processed_at=str(getattr(row, "summary_processed_at", "") or ""),
        story_memory_processed=bool(getattr(row, "story_memory_processed", False)),
        story_memory_processed_at=str(getattr(row, "story_memory_processed_at", "") or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_narrative_outcome(
    row: records.SessionNarrativeOutcomeRecord,
) -> models.NarrativeOutcomeRecord:
    weights = _parse_narrative_outcome_weights(row.effective_weights_json)
    if weights is None:
        raise ValueError("narrative outcome record is missing effective weights")
    return models.NarrativeOutcomeRecord(
        id=int(row.id),
        session_id=str(row.session_id),
        turn_id=int(row.turn_id),
        outcome_code=str(row.outcome_code),
        reason=str(row.reason or ""),
        actor=str(row.actor or ""),
        sample_value=int(row.sample_value),
        effective_weights=weights,
        effective_source=str(row.effective_source),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_rp_module_catalog(
    row: records.RPModuleCatalogRecord,
) -> models.RPModuleCatalogEntry:
    return models.RPModuleCatalogEntry(
        module_name=str(row.module_name),
        display_name=str(row.display_name),
        description=str(row.description or ""),
        sort_order=int(row.sort_order),
        config_version=int(row.config_version),
        default_story_enabled=bool(row.default_story_enabled),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_rp_module(row: records.StoryRPModuleRecord) -> models.StoryRPModule:
    return models.StoryRPModule(
        id=int(row.id),
        story_id=int(row.story_id),
        module_name=str(row.module_name_id),
        enabled=bool(row.enabled),
        config=parse_rp_module_config(row.config_json),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_rp_module_override(
    row: records.SessionRPModuleOverrideRecord,
) -> models.SessionRPModuleOverride:
    return models.SessionRPModuleOverride(
        id=int(row.id),
        session_id=str(row.session_id),
        module_name=str(row.module_name_id),
        enabled=bool(row.enabled) if row.enabled is not None else None,
        config=parse_rp_module_config(row.config_json),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def serialize_narrative_outcome_weights(
    weights: models.NarrativeOutcomeWeights | None,
) -> str | None:
    if weights is None:
        return None
    return json.dumps(weights.to_dict(), ensure_ascii=False, separators=(",", ":"))


def serialize_rp_module_config(config: Mapping[str, object]) -> str:
    return json.dumps(dict(config), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_rp_module_config(raw: object) -> dict[str, object]:
    try:
        payload = json.loads(str(raw or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid RP module config JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("RP module config JSON must be an object")
    return payload


def _parse_narrative_outcome_weights(
    raw: object,
) -> models.NarrativeOutcomeWeights | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid narrative outcome weights JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("narrative outcome weights JSON must be an object")
    return models.NarrativeOutcomeWeights.from_mapping(payload)


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
