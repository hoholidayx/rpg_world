"""Shared helpers for Peewee repositories."""

from __future__ import annotations

import json
from typing import Mapping, TypeVar, cast

from peewee import SQL, DoesNotExist, Model

from commons.types import JsonObject, JsonValue
from rpg_data import models
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
    WorkspaceTurnMode,
)
from rpg_data.model.narrative_outcome import (
    NarrativeOutcomeRecord,
    NarrativeOutcomeWeights,
)
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    StoryRPModule,
)
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


def to_workspace_turn_mode(row: records.WorkspaceTurnModeRecord) -> WorkspaceTurnMode:
    return WorkspaceTurnMode(
        workspace_id=str(row.workspace_id),
        mode=str(row.mode),
        short_name=str(row.short_name),
        prompt=str(row.prompt or ""),
        sort_order=int(row.sort_order),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_narrative_style(row: records.NarrativeStyleRecord) -> NarrativeStyle:
    return NarrativeStyle(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        name=str(row.name),
        prompt=str(row.prompt or ""),
        sort_order=int(row.sort_order),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_narrative_style(
    row: records.StoryNarrativeStyleRecord,
) -> StoryNarrativeStyle:
    style = row.narrative_style
    return StoryNarrativeStyle(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        narrative_style_id=int(row.narrative_style_id),
        name=str(style.name),
        prompt=str(style.prompt or ""),
        is_base=bool(row.is_base),
        sort_order=int(row.sort_order),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_quick_reply(row: records.StoryQuickReplyRecord) -> StoryQuickReply:
    return StoryQuickReply(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        title=str(row.title),
        message=str(row.message or ""),
        sort_order=int(row.sort_order),
        enabled=bool(row.enabled),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_opening(row: records.StoryOpeningRecord) -> models.StoryOpening:
    return models.StoryOpening(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        title=str(row.title),
        message=str(row.message),
        sort_order=int(row.sort_order),
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
        lifecycle=str(row.lifecycle or models.SESSION_LIFECYCLE_READY),
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
        story_opening_id=(
            int(profile.story_opening_id)
            if profile is not None and profile.story_opening_id is not None
            else None
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
        story_opening_id=int(row.story_opening_id) if row.story_opening_id is not None else None,
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
        mode=str(getattr(row, "mode", models.TURN_MODE_IC) or models.TURN_MODE_IC),
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


def to_media_blob(row: records.MediaBlobRecord) -> models.MediaBlob:
    return models.MediaBlob(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        sha256=str(row.sha256),
        canonical_ext=str(row.canonical_ext),
        mime_type=str(row.mime_type),
        byte_size=int(row.byte_size),
        relative_path=str(row.relative_path),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_media_asset(row: records.MediaAssetRecord) -> models.MediaAsset:
    return models.MediaAsset(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        blob_id=str(row.blob_id),
        provider_key=str(row.provider_key),
        provider_asset_id=str(row.provider_asset_id or ""),
        visual_brief_json=str(row.visual_brief_json),
        generation_params_json=str(row.generation_params_json or "{}"),
        metadata_json=str(row.metadata_json or "{}"),
        origin_kind=str(row.origin_kind or models.MEDIA_ASSET_ORIGIN_GENERATED),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_media_library_item(
    row: records.MediaLibraryItemRecord,
) -> models.MediaLibraryItem:
    return models.MediaLibraryItem(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        asset_id=str(row.asset_id),
        scope=str(row.scope),
        story_id=int(row.story_id) if row.story_id is not None else None,
        media_type=str(row.media_type),
        title=str(row.title),
        description=str(row.description),
        is_default=bool(row.is_default),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_media_background_state(
    row: records.SessionMediaBackgroundStateRecord,
) -> models.SessionMediaBackgroundState:
    return models.SessionMediaBackgroundState(
        session_id=str(row.session_id),
        latest_observed_turn_id=int(row.latest_observed_turn_id),
        latest_source_fingerprint=str(row.latest_source_fingerprint or ""),
        auto_suppressed=bool(row.auto_suppressed),
        suppressed_through_turn_id=int(row.suppressed_through_turn_id),
        desired_turn_id=int(row.desired_turn_id),
        desired_source_fingerprint=str(row.desired_source_fingerprint or ""),
        last_applied_turn_id=int(row.last_applied_turn_id),
        last_applied_fingerprint=str(row.last_applied_fingerprint or ""),
        last_decision=str(row.last_decision or ""),
        last_reason=str(row.last_reason or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_media_background_evaluation(
    row: records.MediaBackgroundEvaluationRecord,
) -> models.MediaBackgroundEvaluation:
    return models.MediaBackgroundEvaluation(
        id=str(row.id),
        session_id=str(row.session_id),
        status=str(row.status),
        target_turn_id=int(row.target_turn_id),
        source_fingerprint=str(row.source_fingerprint),
        source_snapshot_json=str(row.source_snapshot_json),
        decision=str(row.decision or ""),
        selected_asset_id=(
            str(row.selected_asset_id)
            if row.selected_asset_id is not None
            else None
        ),
        reason=str(row.reason or ""),
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        started_at=str(row.started_at or ""),
        finished_at=str(row.finished_at or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_media_job(row: records.MediaJobRecord) -> models.MediaJob:
    return models.MediaJob(
        id=str(row.id),
        session_id=str(row.session_id),
        provider_key=str(row.provider_key),
        status=str(row.status),
        source_start_turn_id=int(row.source_start_turn_id),
        source_end_turn_id=int(row.source_end_turn_id),
        source_fingerprint=str(row.source_fingerprint),
        source_snapshot_json=str(row.source_snapshot_json),
        visual_brief_json=str(row.visual_brief_json),
        generation_params_json=str(row.generation_params_json or "{}"),
        output_asset_id=(
            str(row.output_asset_id) if row.output_asset_id is not None else None
        ),
        retry_of_job_id=(
            str(row.retry_of_job_id) if row.retry_of_job_id is not None else None
        ),
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        started_at=str(row.started_at or ""),
        finished_at=str(row.finished_at or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_media_gallery_item(
    row: records.SessionMediaGalleryItemRecord,
) -> models.SessionMediaGalleryItem:
    return models.SessionMediaGalleryItem(
        id=str(row.id),
        session_id=str(row.session_id),
        asset_id=str(row.asset_id),
        job_id=str(row.job_id) if row.job_id is not None else None,
        source_start_turn_id=int(row.source_start_turn_id),
        source_end_turn_id=int(row.source_end_turn_id),
        source_fingerprint=str(row.source_fingerprint),
        source_snapshot_json=str(row.source_snapshot_json),
        visual_brief_json=str(row.visual_brief_json),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_session_media_background(
    row: records.SessionMediaBackgroundRecord,
) -> models.SessionMediaBackground:
    return models.SessionMediaBackground(
        session_id=str(row.session_id),
        asset_id=str(row.asset_id),
        source_mode=str(row.source_mode or models.MEDIA_BACKGROUND_SOURCE_MANUAL),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_narrative_outcome(
    row: records.SessionNarrativeOutcomeRecord,
) -> NarrativeOutcomeRecord:
    weights = _parse_narrative_outcome_weights(row.effective_weights_json)
    if weights is None:
        raise ValueError("narrative outcome record is missing effective weights")
    return NarrativeOutcomeRecord(
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
) -> RPModuleCatalogEntry:
    return RPModuleCatalogEntry(
        module_name=str(row.module_name),
        display_name=str(row.display_name),
        description=str(row.description or ""),
        sort_order=int(row.sort_order),
        config_version=int(row.config_version),
        default_story_enabled=bool(row.default_story_enabled),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def to_story_rp_module(row: records.StoryRPModuleRecord) -> StoryRPModule:
    return StoryRPModule(
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
) -> SessionRPModuleOverride:
    return SessionRPModuleOverride(
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
    weights: NarrativeOutcomeWeights | None,
) -> str | None:
    if weights is None:
        return None
    return json.dumps(weights.to_dict(), ensure_ascii=False, separators=(",", ":"))


def serialize_rp_module_config(config: Mapping[str, JsonValue]) -> str:
    return json.dumps(dict(config), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_rp_module_config(raw: object) -> JsonObject:
    try:
        payload = json.loads(str(raw or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid RP module config JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("RP module config JSON must be an object")
    return cast(JsonObject, payload)


def _parse_narrative_outcome_weights(
    raw: object,
) -> NarrativeOutcomeWeights | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid narrative outcome weights JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("narrative outcome weights JSON must be an object")
    return NarrativeOutcomeWeights.from_mapping(payload)


def to_memory_evidence(
    row: records.SessionStoryMemoryEvidenceRecord,
) -> models.MemoryEvidence:
    return models.MemoryEvidence(
        message_id=int(row.message_id),
        turn_id=int(row.turn_id),
        message_version=int(row.message_version),
        content_hash=str(row.content_hash),
    )


def to_session_story_memory(
    row: records.SessionStoryMemoryRecord,
    *,
    evidence: tuple[models.MemoryEvidence, ...] = (),
) -> models.SessionStoryMemory:
    return models.SessionStoryMemory(
        id=int(row.id),
        session_id=str(row.session_id),
        turn_id=int(row.turn_id),
        text=str(row.text or ""),
        memory_kind=str(row.memory_kind),
        epistemic_status=str(row.epistemic_status),
        salience=float(row.salience),
        source_turn_start=int(row.source_turn_start),
        source_turn_end=int(row.source_turn_end),
        dedupe_key=str(row.dedupe_key),
        dream_processed=bool(row.dream_processed),
        metadata_schema_version=int(row.metadata_schema_version),
        metadata_json=str(row.metadata_json or "{}"),
        evidence=evidence,
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
