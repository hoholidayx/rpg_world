"""Peewee ORM bindings for the RPG World data module."""

from __future__ import annotations

from pathlib import Path

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    Check,
    CompositeKey,
    Database,
    DatabaseProxy,
    ForeignKeyField,
    FloatField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from rpg_data.models import STATUS_KIND_NORMAL, STORY_STATUS_MOUNT_ORIGIN_SYSTEM, TURN_MODE_IC
from rpg_data.settings import resolve_database_path

__all__ = [
    "CharacterDetailRecord",
    "CharacterRecord",
    "LorebookEntryRecord",
    "MediaAssetRecord",
    "MediaBlobRecord",
    "MediaJobRecord",
    "MediaLibraryItemRecord",
    "MediaLibraryItemTagRecord",
    "MediaBackgroundEvaluationRecord",
    "NarrativeStyleRecord",
    "RPModuleCatalogRecord",
    "SessionBackupMessageRecord",
    "SessionMessageRecord",
    "SessionMediaBackgroundRecord",
    "SessionMediaBackgroundStateRecord",
    "SessionMediaGalleryItemRecord",
    "SessionNarrativeOutcomeRecord",
    "SessionProfileRecord",
    "SessionRPModuleOverrideRecord",
    "SessionRecord",
    "SessionStoryMemoryRecord",
    "SessionStatusTableRecord",
    "SessionStatusDeferredProgressRecord",
    "StoryCharacterRecord",
    "StoryLorebookEntryRecord",
    "StoryNarrativeStyleRecord",
    "StoryQuickReplyRecord",
    "StoryStatusTableRecord",
    "TTSBlobRecord",
    "TTSCacheEntryRecord",
    "TTSAudioPartRecord",
    "TTSJobRecord",
    "StoryRecord",
    "StoryRPModuleRecord",
    "StatusTableTemplateRecord",
    "WorkspaceRecord",
    "WorkspaceTurnModeRecord",
    "bind_database",
    "make_database",
]

_database_proxy = DatabaseProxy()


def make_database(db_path: str | Path | None = None) -> SqliteDatabase:
    """Create a Peewee SQLite database using the rpg_data pragmas."""

    path = resolve_database_path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteDatabase(
        path,
        pragmas={
            "foreign_keys": 1,
            "journal_mode": "wal",
            "busy_timeout": 5000,
        },
    )


def bind_database(database: Database) -> Database:
    """Bind all ORM models to ``database`` and return it."""

    if _database_proxy.obj is not database:
        if _database_proxy.obj is None:
            _database_proxy.initialize(database)
        else:
            _database_proxy.initialize(database)
    database.bind(RECORD_MODELS, bind_refs=False, bind_backrefs=False)
    return database


class BaseRecord(Model):
    class Meta:
        database = _database_proxy


class WorkspaceRecord(BaseRecord):
    id = CharField(primary_key=True)
    name = TextField()
    root_path = TextField()
    description = TextField(default="")
    enabled = BooleanField(default=True)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_workspaces"


class WorkspaceTurnModeRecord(BaseRecord):
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="turn_modes",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    mode = TextField()
    short_name = TextField()
    prompt = TextField(default="")
    sort_order = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_workspace_turn_modes"
        primary_key = CompositeKey("workspace", "mode")


class StoryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="stories",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    title = TextField()
    summary = TextField(default="")
    # Story-level fixed system prompt; planned to be integrated into fix layer later.
    story_prompt = TextField(default="")
    first_message = TextField(default="")
    main_llm_provider_key = TextField(null=True)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_stories"


class NarrativeStyleRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="narrative_styles",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    prompt = TextField(default="")
    sort_order = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_narrative_styles"


class StoryNarrativeStyleRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_narrative_styles",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="narrative_style_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    narrative_style = ForeignKeyField(
        NarrativeStyleRecord,
        backref="story_mounts",
        column_name="narrative_style_id",
        on_delete="CASCADE",
    )
    is_base = BooleanField(default=False)
    sort_order = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_narrative_styles"


class StoryQuickReplyRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_quick_replies",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="quick_replies",
        column_name="story_id",
        on_delete="CASCADE",
    )
    title = TextField()
    message = TextField(default="")
    sort_order = IntegerField(default=0)
    enabled = BooleanField(default=True)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_quick_replies"


class SessionRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="sessions",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="sessions",
        column_name="story_id",
        on_delete="CASCADE",
    )
    state_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_sessions"


class SessionProfileRecord(BaseRecord):
    session = ForeignKeyField(
        SessionRecord,
        primary_key=True,
        backref="profile",
        column_name="session_id",
        on_delete="CASCADE",
    )
    title = TextField(default="")
    description = TextField(default="")
    main_llm_provider_key = TextField(null=True)
    player_character_id = IntegerField(null=True)
    player_character_snapshot_json = TextField(default="{}")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_profiles"


class SessionMessageRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="messages",
        column_name="session_id",
        on_delete="CASCADE",
    )
    role = TextField()
    content = TextField(default="")
    mode = TextField(default=TURN_MODE_IC)
    turn_id = IntegerField(constraints=[Check("turn_id > 0")])
    seq_in_turn = IntegerField(constraints=[Check("seq_in_turn > 0")])
    tool_call_id = TextField(default="")
    tool_calls_json = TextField(default="")
    metadata_json = TextField(default="{}")
    summary_processed = BooleanField(default=False)
    summary_batch_id = IntegerField(null=True)
    summary_processed_at = TextField(null=True)
    story_memory_processed = BooleanField(default=False)
    story_memory_processed_at = TextField(null=True)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_messages"


class SessionBackupMessageRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="backup_messages",
        column_name="session_id",
        on_delete="CASCADE",
    )
    role = TextField()
    content = TextField(default="")
    mode = TextField(default=TURN_MODE_IC)
    turn_id = IntegerField(constraints=[Check("turn_id > 0")])
    seq_in_turn = IntegerField(constraints=[Check("seq_in_turn > 0")])
    tool_call_id = TextField(default="")
    tool_calls_json = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_backup_messages"


class SessionStoryMemoryRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="story_memories",
        column_name="session_id",
        on_delete="CASCADE",
    )
    turn_id = IntegerField(constraints=[Check("turn_id > 0")])
    text = TextField(default="")
    memory_kind = TextField(default="event")
    epistemic_status = TextField(default="confirmed")
    salience = FloatField(default=0.5, constraints=[Check("salience >= 0.0 AND salience <= 1.0")])
    source_turn_start = IntegerField(constraints=[Check("source_turn_start > 0")])
    source_turn_end = IntegerField(constraints=[Check("source_turn_end >= source_turn_start")])
    dedupe_key = TextField(constraints=[Check("length(dedupe_key) = 64")])
    dream_processed = BooleanField(default=False)
    metadata_schema_version = IntegerField(default=1, constraints=[Check("metadata_schema_version > 0")])
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_story_memories"
        indexes = ((('session', 'dedupe_key'), True),)


class SessionNarrativeOutcomeRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="narrative_outcomes",
        column_name="session_id",
        on_delete="CASCADE",
    )
    turn_id = IntegerField(constraints=[Check("turn_id > 0")])
    outcome_code = TextField()
    reason = TextField(default="")
    actor = TextField(default="")
    sample_value = IntegerField()
    effective_weights_json = TextField()
    effective_source = TextField()
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_narrative_outcomes"
        indexes = ((('session', 'turn_id'), True),)


class MediaBlobRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="media_blobs",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    sha256 = CharField(constraints=[Check("length(sha256) = 64")])
    canonical_ext = CharField()
    mime_type = CharField()
    byte_size = IntegerField(constraints=[Check("byte_size > 0")])
    relative_path = TextField()
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_media_blobs"
        indexes = ((('workspace', 'sha256'), True),)


class MediaAssetRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="media_assets",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    blob = ForeignKeyField(
        MediaBlobRecord,
        backref="assets",
        column_name="blob_id",
        on_delete="CASCADE",
    )
    provider_key = TextField()
    provider_asset_id = TextField(default="")
    visual_brief_json = TextField()
    generation_params_json = TextField(default="{}")
    metadata_json = TextField(default="{}")
    origin_kind = TextField(default="generated")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_media_assets"


class MediaLibraryItemRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="media_library_items",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    asset = ForeignKeyField(
        MediaAssetRecord,
        backref="library_item",
        column_name="asset_id",
        on_delete="CASCADE",
        unique=True,
    )
    scope = TextField()
    media_type = TextField(default="background")
    story = ForeignKeyField(
        StoryRecord,
        backref="media_library_items",
        column_name="story_id",
        null=True,
        on_delete="CASCADE",
    )
    title = TextField()
    description = TextField()
    is_default = BooleanField(default=False)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_media_library_items"


class MediaLibraryItemTagRecord(BaseRecord):
    item = ForeignKeyField(
        MediaLibraryItemRecord,
        backref="tag_rows",
        column_name="item_id",
        on_delete="CASCADE",
    )
    tag = TextField()
    normalized_tag = TextField()
    created_at = TextField()

    class Meta:
        table_name = "rpg_media_library_item_tags"
        primary_key = CompositeKey("item", "tag")


class MediaJobRecord(BaseRecord):
    id = CharField(primary_key=True)
    session = ForeignKeyField(
        SessionRecord,
        backref="media_jobs",
        column_name="session_id",
        on_delete="CASCADE",
    )
    provider_key = TextField()
    status = TextField(default="queued")
    source_start_turn_id = IntegerField(constraints=[Check("source_start_turn_id > 0")])
    source_end_turn_id = IntegerField(
        constraints=[Check("source_end_turn_id >= source_start_turn_id")]
    )
    source_fingerprint = CharField(constraints=[Check("length(source_fingerprint) = 64")])
    source_snapshot_json = TextField()
    visual_brief_json = TextField()
    generation_params_json = TextField(default="{}")
    output_asset = ForeignKeyField(
        MediaAssetRecord,
        backref="output_jobs",
        column_name="output_asset_id",
        null=True,
        on_delete="SET NULL",
    )
    retry_of_job = ForeignKeyField(
        "self",
        backref="retry_jobs",
        column_name="retry_of_job_id",
        null=True,
        on_delete="SET NULL",
    )
    error_code = TextField(default="")
    error_message = TextField(default="")
    started_at = TextField(null=True)
    finished_at = TextField(null=True)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_media_jobs"


class SessionMediaGalleryItemRecord(BaseRecord):
    id = CharField(primary_key=True)
    session = ForeignKeyField(
        SessionRecord,
        backref="media_gallery_items",
        column_name="session_id",
        on_delete="CASCADE",
    )
    asset = ForeignKeyField(
        MediaAssetRecord,
        backref="session_gallery_items",
        column_name="asset_id",
        on_delete="CASCADE",
        unique=True,
    )
    job = ForeignKeyField(
        MediaJobRecord,
        backref="gallery_items",
        column_name="job_id",
        null=True,
        on_delete="SET NULL",
    )
    source_start_turn_id = IntegerField(constraints=[Check("source_start_turn_id > 0")])
    source_end_turn_id = IntegerField(
        constraints=[Check("source_end_turn_id >= source_start_turn_id")]
    )
    source_fingerprint = CharField(constraints=[Check("length(source_fingerprint) = 64")])
    source_snapshot_json = TextField()
    visual_brief_json = TextField()
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_media_gallery_items"


class TTSBlobRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="tts_blobs",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    sha256 = CharField()
    mime_type = TextField(default="audio/mpeg")
    byte_size = IntegerField()
    relative_path = TextField()
    created_at = TextField()

    class Meta:
        table_name = "rpg_tts_blobs"


class TTSCacheEntryRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="tts_cache_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    source_fingerprint = CharField()
    config_fingerprint = CharField()
    normalization_revision = TextField()
    part_count = IntegerField()
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_tts_cache_entries"


class TTSAudioPartRecord(BaseRecord):
    id = CharField(primary_key=True)
    cache_entry = ForeignKeyField(
        TTSCacheEntryRecord,
        backref="parts",
        column_name="cache_entry_id",
        on_delete="CASCADE",
    )
    blob = ForeignKeyField(
        TTSBlobRecord,
        backref="audio_parts",
        column_name="blob_id",
        on_delete="NO ACTION",
    )
    part_index = IntegerField()
    created_at = TextField()

    class Meta:
        table_name = "rpg_tts_audio_parts"


class TTSJobRecord(BaseRecord):
    id = CharField(primary_key=True)
    session = ForeignKeyField(
        SessionRecord,
        backref="tts_jobs",
        column_name="session_id",
        on_delete="CASCADE",
    )
    message = ForeignKeyField(
        SessionMessageRecord,
        backref="tts_jobs",
        column_name="message_id",
        on_delete="CASCADE",
    )
    status = TextField(default="queued")
    source_fingerprint = CharField()
    config_fingerprint = CharField()
    normalization_revision = TextField()
    cache_entry = ForeignKeyField(
        TTSCacheEntryRecord,
        backref="jobs",
        column_name="cache_entry_id",
        null=True,
        on_delete="SET NULL",
    )
    error_code = TextField(default="")
    error_message = TextField(default="")
    started_at = TextField(null=True)
    finished_at = TextField(null=True)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_tts_jobs"


class SessionMediaBackgroundRecord(BaseRecord):
    session = ForeignKeyField(
        SessionRecord,
        primary_key=True,
        backref="media_background",
        column_name="session_id",
        on_delete="CASCADE",
    )
    asset = ForeignKeyField(
        MediaAssetRecord,
        backref="session_backgrounds",
        column_name="asset_id",
        on_delete="RESTRICT",
    )
    source_mode = TextField(default="manual")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_media_backgrounds"


class SessionMediaBackgroundStateRecord(BaseRecord):
    session = ForeignKeyField(
        SessionRecord,
        primary_key=True,
        backref="media_background_state",
        column_name="session_id",
        on_delete="CASCADE",
    )
    latest_observed_turn_id = IntegerField(default=0)
    latest_source_fingerprint = TextField(default="")
    auto_suppressed = BooleanField(default=False)
    suppressed_through_turn_id = IntegerField(default=0)
    desired_turn_id = IntegerField(default=0)
    desired_source_fingerprint = TextField(default="")
    last_applied_turn_id = IntegerField(default=0)
    last_applied_fingerprint = TextField(default="")
    last_decision = TextField(default="")
    last_reason = TextField(default="")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_media_background_states"


class MediaBackgroundEvaluationRecord(BaseRecord):
    id = CharField(primary_key=True)
    session = ForeignKeyField(
        SessionRecord,
        backref="media_background_evaluations",
        column_name="session_id",
        on_delete="CASCADE",
    )
    status = TextField(default="queued")
    target_turn_id = IntegerField()
    source_fingerprint = CharField()
    source_snapshot_json = TextField()
    decision = TextField(default="")
    selected_asset = ForeignKeyField(
        MediaAssetRecord,
        backref="background_evaluations",
        column_name="selected_asset_id",
        null=True,
        on_delete="SET NULL",
    )
    reason = TextField(default="")
    error_code = TextField(default="")
    error_message = TextField(default="")
    started_at = TextField(null=True)
    finished_at = TextField(null=True)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_media_background_evaluations"


class RPModuleCatalogRecord(BaseRecord):
    module_name = TextField(primary_key=True)
    display_name = TextField()
    description = TextField(default="")
    sort_order = IntegerField(default=0)
    config_version = IntegerField(default=1)
    default_story_enabled = BooleanField(default=True)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_rp_module_catalog"


class StoryRPModuleRecord(BaseRecord):
    id = AutoField()
    story = ForeignKeyField(
        StoryRecord,
        backref="rp_modules",
        column_name="story_id",
        on_delete="CASCADE",
    )
    module_name = ForeignKeyField(
        RPModuleCatalogRecord,
        field=RPModuleCatalogRecord.module_name,
        backref="story_mounts",
        column_name="module_name",
        on_delete="CASCADE",
    )
    enabled = BooleanField(default=True)
    config_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_rp_modules"
        indexes = ((('story', 'module_name'), True),)


class SessionRPModuleOverrideRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="rp_module_overrides",
        column_name="session_id",
        on_delete="CASCADE",
    )
    module_name = ForeignKeyField(
        RPModuleCatalogRecord,
        field=RPModuleCatalogRecord.module_name,
        backref="session_overrides",
        column_name="module_name",
        on_delete="CASCADE",
    )
    enabled = BooleanField(null=True)
    config_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_rp_module_overrides"
        indexes = ((('session', 'module_name'), True),)


class CharacterRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="characters",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    personality = TextField(default="")
    content = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_characters"


class CharacterDetailRecord(BaseRecord):
    id = AutoField()
    character = ForeignKeyField(
        CharacterRecord,
        backref="details",
        column_name="character_id",
        on_delete="CASCADE",
    )
    name = TextField()
    content = TextField(default="")
    tags_json = TextField(default="[]")
    sort_order = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_character_details"


class LorebookEntryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="lorebook_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    content = TextField(default="")
    description = TextField(default="")
    tags_json = TextField(default="[]")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_lorebook_entries"


class StoryCharacterRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_characters",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="character_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    character = ForeignKeyField(
        CharacterRecord,
        backref="story_mounts",
        column_name="character_id",
        on_delete="CASCADE",
    )
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_characters"


class StoryLorebookEntryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_lorebook_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="lorebook_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    lorebook_entry = ForeignKeyField(
        LorebookEntryRecord,
        backref="story_mounts",
        column_name="lorebook_entry_id",
        on_delete="CASCADE",
    )
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_lorebook_entries"


class StatusTableTemplateRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="status_table_templates",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    status_kind = TextField(default=STATUS_KIND_NORMAL)
    description = TextField(default="")
    document_json = TextField()
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_status_table_templates"


class StoryStatusTableRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_status_tables",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="status_table_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    status_table = ForeignKeyField(
        StatusTableTemplateRecord,
        backref="story_mounts",
        column_name="status_table_id",
        on_delete="CASCADE",
    )
    story_character = ForeignKeyField(
        StoryCharacterRecord,
        backref="status_table_mounts",
        column_name="story_character_mount_id",
        on_delete="SET NULL",
        null=True,
    )
    mount_origin = TextField(default=STORY_STATUS_MOUNT_ORIGIN_SYSTEM)
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_status_tables"


class SessionStatusTableRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="status_tables",
        column_name="session_id",
        on_delete="CASCADE",
    )
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="session_status_tables",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="session_status_tables",
        column_name="story_id",
        on_delete="CASCADE",
    )
    source_table_id = IntegerField(null=True)
    origin = TextField()
    name = TextField()
    status_kind = TextField(default=STATUS_KIND_NORMAL)
    description = TextField(default="")
    document_json = TextField()
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_status_tables"


class SessionStatusDeferredProgressRecord(BaseRecord):
    session_status_table = ForeignKeyField(
        SessionStatusTableRecord,
        backref="deferred_progress",
        column_name="session_status_table_id",
        on_delete="CASCADE",
    )
    field_key = TextField()
    last_processed_turn_id = IntegerField(default=0)
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_status_deferred_progress"
        primary_key = CompositeKey("session_status_table", "field_key")


RECORD_MODELS = (
    WorkspaceRecord,
    WorkspaceTurnModeRecord,
    StoryRecord,
    NarrativeStyleRecord,
    StoryNarrativeStyleRecord,
    StoryQuickReplyRecord,
    SessionRecord,
    SessionProfileRecord,
    SessionMessageRecord,
    SessionBackupMessageRecord,
    SessionStoryMemoryRecord,
    RPModuleCatalogRecord,
    StoryRPModuleRecord,
    SessionRPModuleOverrideRecord,
    SessionNarrativeOutcomeRecord,
    MediaBlobRecord,
    MediaAssetRecord,
    MediaLibraryItemRecord,
    MediaLibraryItemTagRecord,
    MediaJobRecord,
    SessionMediaGalleryItemRecord,
    TTSBlobRecord,
    TTSCacheEntryRecord,
    TTSAudioPartRecord,
    TTSJobRecord,
    SessionMediaBackgroundRecord,
    SessionMediaBackgroundStateRecord,
    MediaBackgroundEvaluationRecord,
    CharacterRecord,
    CharacterDetailRecord,
    LorebookEntryRecord,
    StoryCharacterRecord,
    StoryLorebookEntryRecord,
    StatusTableTemplateRecord,
    StoryStatusTableRecord,
    SessionStatusTableRecord,
    SessionStatusDeferredProgressRecord,
)
