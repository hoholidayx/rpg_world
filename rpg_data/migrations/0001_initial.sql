-- Consolidated clean-install schema. Legacy databases are intentionally unsupported.

CREATE TABLE rpg_workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rpg_stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    story_prompt TEXT NOT NULL DEFAULT '',
    main_llm_provider_key TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, title),
    UNIQUE (id, workspace_id)
);

CREATE TABLE rpg_sessions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, lifecycle TEXT NOT NULL DEFAULT 'ready'
        CHECK (lifecycle IN ('provisioning', 'ready')),
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    -- 会话必须绑定到同一 workspace 下的 story，避免跨 workspace 误挂载。
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE
);

CREATE TABLE rpg_session_profiles (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    player_character_id INTEGER,
    player_character_snapshot_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, main_llm_provider_key TEXT, story_opening_id INTEGER
REFERENCES rpg_story_openings(id) ON DELETE SET NULL,
    -- 可读标题/描述独立存放，rpg_sessions.id 保持稳定的公开定位 ID。
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE rpg_session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    seq_in_turn INTEGER NOT NULL CHECK (seq_in_turn > 0),
    tool_call_id TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    summary_processed INTEGER NOT NULL DEFAULT 0 CHECK (summary_processed IN (0, 1)),
    summary_batch_id INTEGER,
    summary_processed_at TEXT,
    story_memory_processed INTEGER NOT NULL DEFAULT 0 CHECK (story_memory_processed IN (0, 1)),
    story_memory_processed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, mode TEXT NOT NULL DEFAULT 'neutral'
CHECK (mode IN ('neutral', 'ic', 'ooc', 'gm')),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE rpg_session_backup_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    seq_in_turn INTEGER NOT NULL CHECK (seq_in_turn > 0),
    tool_call_id TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, mode TEXT NOT NULL DEFAULT 'neutral'
CHECK (mode IN ('neutral', 'ic', 'ooc', 'gm')),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE rpg_story_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, name)
);

CREATE TABLE rpg_story_character_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_character_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_character_id) REFERENCES rpg_story_characters(id) ON DELETE CASCADE,
    UNIQUE (story_character_id, name)
);

CREATE TABLE rpg_story_lorebook_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, name)
);

CREATE TABLE rpg_story_status_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    story_character_id INTEGER,
    name TEXT NOT NULL,
    status_kind TEXT NOT NULL DEFAULT 'normal' CHECK (status_kind IN ('scene', 'normal')),
    description TEXT NOT NULL DEFAULT '',
    document_json TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (story_character_id) REFERENCES rpg_story_characters(id) ON DELETE SET NULL,
    UNIQUE (story_id, name)
);

CREATE TABLE rpg_session_status_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    source_story_status_table_id INTEGER,
    origin TEXT NOT NULL CHECK (origin IN ('story_copy', 'session_native')),
    name TEXT NOT NULL,
    status_kind TEXT NOT NULL DEFAULT 'normal' CHECK (status_kind IN ('scene', 'normal')),
    description TEXT NOT NULL DEFAULT '',
    document_json TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (source_story_status_table_id) REFERENCES rpg_story_status_tables(id) ON DELETE SET NULL,
    UNIQUE (session_id, name)
);

CREATE INDEX idx_rpg_story_characters_workspace_story
ON rpg_story_characters(workspace_id, story_id, sort_order, id);

CREATE INDEX idx_rpg_story_character_details_character
ON rpg_story_character_details(story_character_id, sort_order, id);

CREATE INDEX idx_rpg_story_lorebook_entries_workspace_story
ON rpg_story_lorebook_entries(workspace_id, story_id, sort_order, id);

CREATE INDEX idx_rpg_story_status_tables_workspace_story
ON rpg_story_status_tables(workspace_id, story_id, status_kind, sort_order, id);

CREATE INDEX idx_rpg_story_status_tables_character
ON rpg_story_status_tables(story_character_id);

CREATE INDEX idx_rpg_session_status_tables_session
ON rpg_session_status_tables(session_id, status_kind, sort_order, id);

CREATE INDEX idx_rpg_session_status_tables_source
ON rpg_session_status_tables(source_story_status_table_id);

CREATE INDEX idx_rpg_stories_workspace_id ON rpg_stories(workspace_id);

CREATE INDEX idx_rpg_sessions_workspace_id ON rpg_sessions(workspace_id);

CREATE INDEX idx_rpg_sessions_story_id ON rpg_sessions(story_id);

CREATE INDEX idx_rpg_session_messages_session_id_id ON rpg_session_messages(session_id, id);

CREATE INDEX idx_rpg_session_messages_turn ON rpg_session_messages(session_id, turn_id, seq_in_turn, id);

CREATE UNIQUE INDEX ux_rpg_session_messages_turn_seq ON rpg_session_messages(session_id, turn_id, seq_in_turn);

CREATE INDEX idx_rpg_session_messages_summary_cursor ON rpg_session_messages(session_id, summary_processed, turn_id, id);

CREATE INDEX idx_rpg_session_messages_story_cursor ON rpg_session_messages(session_id, story_memory_processed, turn_id, id);

CREATE INDEX idx_rpg_session_backup_messages_session_id_id ON rpg_session_backup_messages(session_id, id);

CREATE INDEX idx_rpg_session_backup_messages_turn ON rpg_session_backup_messages(session_id, turn_id, seq_in_turn, id);

CREATE TABLE rpg_story_pack_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    resource_kind TEXT NOT NULL CHECK (length(trim(resource_kind)) > 0),
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    resource_id TEXT NOT NULL CHECK (length(trim(resource_id)) > 0),
    source_digest TEXT NOT NULL CHECK (
        length(source_digest) = 64
        AND source_digest NOT GLOB '*[^0-9a-f]*'
    ),
    resource_version INTEGER NOT NULL CHECK (resource_version > 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id)
        REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, resource_kind, source_id),
    UNIQUE (story_id, resource_kind, resource_id)
);

CREATE INDEX idx_rpg_story_pack_bindings_story
ON rpg_story_pack_bindings(story_id, resource_kind, source_id);

CREATE TABLE rpg_story_pack_operations (
    id TEXT PRIMARY KEY,
    operation_kind TEXT NOT NULL CHECK (length(trim(operation_kind)) > 0),
    status TEXT NOT NULL DEFAULT 'previewed'
        CHECK (
            status IN (
                'previewed',
                'applying',
                'applied',
                'applied_with_local_sync_pending',
                'failed'
            )
        ),
    project_id TEXT NOT NULL CHECK (length(trim(project_id)) > 0),
    pack_id TEXT NOT NULL CHECK (length(trim(pack_id)) > 0),
    pack_digest TEXT NOT NULL CHECK (
        length(pack_digest) = 64
        AND pack_digest NOT GLOB '*[^0-9a-f]*'
    ),
    workspace_id TEXT NOT NULL CHECK (length(trim(workspace_id)) > 0),
    story_stable_id TEXT NOT NULL CHECK (length(trim(story_stable_id)) > 0),
    story_id INTEGER,
    pack_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TEXT,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE SET NULL
);

CREATE INDEX idx_rpg_story_pack_operations_pack
ON rpg_story_pack_operations(
    workspace_id,
    story_stable_id,
    pack_digest,
    status,
    created_at
);

CREATE TABLE rpg_rp_module_catalog (
    module_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    config_version INTEGER NOT NULL DEFAULT 1 CHECK (config_version > 0),
    default_story_enabled INTEGER NOT NULL DEFAULT 1 CHECK (default_story_enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rpg_story_rp_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    module_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    config_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    FOREIGN KEY (module_name) REFERENCES rpg_rp_module_catalog(module_name) ON DELETE CASCADE,
    UNIQUE (story_id, module_name)
);

CREATE INDEX idx_rpg_story_rp_modules_story_sort
ON rpg_story_rp_modules(story_id, module_name);

CREATE TABLE rpg_session_rp_module_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    module_name TEXT NOT NULL,
    enabled INTEGER CHECK (enabled IS NULL OR enabled IN (0, 1)),
    config_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (module_name) REFERENCES rpg_rp_module_catalog(module_name) ON DELETE CASCADE,
    UNIQUE (session_id, module_name)
);

CREATE INDEX idx_rpg_session_rp_module_overrides_session
ON rpg_session_rp_module_overrides(session_id, module_name);

CREATE TABLE rpg_session_narrative_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    outcome_code TEXT NOT NULL CHECK (
        outcome_code IN (
            'critical_success',
            'success',
            'success_with_cost',
            'setback',
            'critical_failure'
        )
    ),
    reason TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    sample_value INTEGER NOT NULL CHECK (sample_value BETWEEN 1 AND 100),
    effective_weights_json TEXT NOT NULL,
    effective_source TEXT NOT NULL CHECK (effective_source IN ('config', 'story', 'session')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    UNIQUE (session_id, turn_id)
);

CREATE INDEX idx_rpg_session_narrative_outcomes_session_turn
ON rpg_session_narrative_outcomes(session_id, turn_id);

CREATE TABLE rpg_narrative_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, name),
    UNIQUE (id, workspace_id)
);

CREATE TABLE rpg_story_narrative_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    narrative_style_id INTEGER NOT NULL,
    is_base INTEGER NOT NULL DEFAULT 0 CHECK (is_base IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (narrative_style_id, workspace_id) REFERENCES rpg_narrative_styles(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, narrative_style_id)
);

CREATE INDEX idx_rpg_story_narrative_styles_story
ON rpg_story_narrative_styles(story_id, sort_order, id);

CREATE UNIQUE INDEX ux_rpg_story_narrative_styles_base
ON rpg_story_narrative_styles(story_id)
WHERE is_base = 1;

CREATE TABLE rpg_story_quick_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, title)
);

CREATE INDEX idx_rpg_story_quick_replies_story
ON rpg_story_quick_replies(story_id, enabled, sort_order, id);

CREATE TABLE rpg_media_blobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    canonical_ext TEXT NOT NULL CHECK (canonical_ext IN ('png', 'jpg', 'webp')),
    mime_type TEXT NOT NULL CHECK (mime_type IN ('image/png', 'image/jpeg', 'image/webp')),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    relative_path TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, sha256)
);

CREATE TABLE rpg_media_assets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    blob_id TEXT NOT NULL,
    provider_key TEXT NOT NULL,
    provider_asset_id TEXT NOT NULL DEFAULT '',
    visual_brief_json TEXT NOT NULL,
    generation_params_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, origin_kind TEXT NOT NULL DEFAULT 'generated'
CHECK (origin_kind IN ('generated', 'upload')),
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (blob_id) REFERENCES rpg_media_blobs(id) ON DELETE CASCADE
);

CREATE TABLE rpg_media_jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    provider_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'cancelling', 'succeeded', 'failed', 'cancelled', 'interrupted')),
    source_start_turn_id INTEGER NOT NULL CHECK (source_start_turn_id > 0),
    source_end_turn_id INTEGER NOT NULL CHECK (source_end_turn_id >= source_start_turn_id),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    source_snapshot_json TEXT NOT NULL,
    visual_brief_json TEXT NOT NULL,
    generation_params_json TEXT NOT NULL DEFAULT '{}',
    output_asset_id TEXT,
    retry_of_job_id TEXT,
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (output_asset_id) REFERENCES rpg_media_assets(id) ON DELETE SET NULL,
    FOREIGN KEY (retry_of_job_id) REFERENCES rpg_media_jobs(id) ON DELETE SET NULL
);

CREATE TABLE rpg_session_media_gallery_items (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    job_id TEXT,
    source_start_turn_id INTEGER NOT NULL CHECK (source_start_turn_id > 0),
    source_end_turn_id INTEGER NOT NULL CHECK (source_end_turn_id >= source_start_turn_id),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    source_snapshot_json TEXT NOT NULL,
    visual_brief_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES rpg_media_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES rpg_media_jobs(id) ON DELETE SET NULL,
    UNIQUE (asset_id)
);

CREATE TABLE rpg_session_media_backgrounds (
    session_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source_mode TEXT NOT NULL DEFAULT 'manual'
CHECK (source_mode IN ('manual', 'auto')),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES rpg_media_assets(id) ON DELETE RESTRICT
);

CREATE INDEX idx_rpg_media_blobs_workspace_sha
ON rpg_media_blobs(workspace_id, sha256);

CREATE INDEX idx_rpg_media_assets_workspace_created
ON rpg_media_assets(workspace_id, created_at, id);

CREATE INDEX idx_rpg_media_assets_blob
ON rpg_media_assets(blob_id);

CREATE INDEX idx_rpg_media_jobs_queue
ON rpg_media_jobs(status, created_at, id);

CREATE INDEX idx_rpg_media_jobs_session_created
ON rpg_media_jobs(session_id, created_at, id);

CREATE INDEX idx_rpg_session_media_gallery_session_created
ON rpg_session_media_gallery_items(session_id, created_at, id);

CREATE INDEX idx_rpg_session_media_background_asset
ON rpg_session_media_backgrounds(asset_id);

CREATE TABLE rpg_session_media_background_states (
    session_id TEXT PRIMARY KEY,
    latest_observed_turn_id INTEGER NOT NULL DEFAULT 0 CHECK (latest_observed_turn_id >= 0),
    latest_source_fingerprint TEXT NOT NULL DEFAULT '',
    auto_suppressed INTEGER NOT NULL DEFAULT 0 CHECK (auto_suppressed IN (0, 1)),
    suppressed_through_turn_id INTEGER NOT NULL DEFAULT 0 CHECK (suppressed_through_turn_id >= 0),
    desired_turn_id INTEGER NOT NULL DEFAULT 0 CHECK (desired_turn_id >= 0),
    desired_source_fingerprint TEXT NOT NULL DEFAULT '',
    last_applied_turn_id INTEGER NOT NULL DEFAULT 0 CHECK (last_applied_turn_id >= 0),
    last_applied_fingerprint TEXT NOT NULL DEFAULT '',
    last_decision TEXT NOT NULL DEFAULT '',
    last_reason TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE rpg_media_background_evaluations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'superseded', 'skipped_manual', 'interrupted')),
    target_turn_id INTEGER NOT NULL CHECK (target_turn_id > 0),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    source_snapshot_json TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT '' CHECK (decision IN ('', 'keep', 'switch')),
    selected_asset_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (selected_asset_id) REFERENCES rpg_media_assets(id) ON DELETE SET NULL
);

CREATE INDEX idx_rpg_media_background_eval_queue
ON rpg_media_background_evaluations(status, created_at, id);

CREATE INDEX idx_rpg_media_background_eval_session
ON rpg_media_background_evaluations(session_id, created_at, id);

CREATE TABLE IF NOT EXISTS "rpg_media_library_items" (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL CHECK (scope IN ('story', 'workspace')),
    story_id INTEGER,
    media_type TEXT NOT NULL DEFAULT 'background'
        CHECK (media_type IN (
            'background',
            'avatar',
            'character_sprite',
            'scene_illustration',
            'map',
            'item',
            'ui',
            'reference',
            'other'
        )),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES rpg_media_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    CHECK (
        (scope = 'story' AND story_id IS NOT NULL)
        OR (scope = 'workspace' AND story_id IS NULL)
    ),
    CHECK (scope = 'story' OR is_default = 0),
    CHECK (media_type = 'background' OR is_default = 0)
);

CREATE TABLE IF NOT EXISTS "rpg_media_library_item_tags" (
    item_id TEXT NOT NULL,
    tag TEXT NOT NULL CHECK (length(trim(tag)) > 0),
    normalized_tag TEXT GENERATED ALWAYS AS (lower(trim(tag))) STORED,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, tag),
    UNIQUE (item_id, normalized_tag),
    FOREIGN KEY (item_id) REFERENCES rpg_media_library_items(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_rpg_media_library_story_default
ON rpg_media_library_items(story_id)
WHERE scope = 'story' AND media_type = 'background' AND is_default = 1;

CREATE INDEX idx_rpg_media_library_workspace_taxonomy
ON rpg_media_library_items(workspace_id, media_type, scope, story_id, updated_at, id);

CREATE INDEX idx_rpg_media_library_tags_normalized
ON rpg_media_library_item_tags(normalized_tag, item_id);

CREATE TABLE rpg_tts_blobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    mime_type TEXT NOT NULL CHECK (mime_type = 'audio/mpeg'),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    relative_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, sha256)
);

CREATE TABLE rpg_tts_cache_entries (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    config_fingerprint TEXT NOT NULL CHECK (length(config_fingerprint) = 64),
    normalization_revision TEXT NOT NULL,
    part_count INTEGER NOT NULL CHECK (part_count > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, source_fingerprint, config_fingerprint, normalization_revision)
);

CREATE TABLE rpg_tts_audio_parts (
    id TEXT PRIMARY KEY,
    cache_entry_id TEXT NOT NULL,
    blob_id TEXT NOT NULL,
    part_index INTEGER NOT NULL CHECK (part_index >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cache_entry_id) REFERENCES rpg_tts_cache_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (blob_id) REFERENCES rpg_tts_blobs(id) ON DELETE NO ACTION,
    UNIQUE (cache_entry_id, part_index)
);

CREATE TABLE rpg_tts_jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    config_fingerprint TEXT NOT NULL CHECK (length(config_fingerprint) = 64),
    normalization_revision TEXT NOT NULL,
    cache_entry_id TEXT,
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES rpg_session_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (cache_entry_id) REFERENCES rpg_tts_cache_entries(id) ON DELETE SET NULL,
    UNIQUE (session_id, message_id, source_fingerprint, config_fingerprint, normalization_revision)
);

CREATE INDEX idx_rpg_tts_jobs_queue
ON rpg_tts_jobs(status, created_at, id);

CREATE INDEX idx_rpg_tts_jobs_session_message
ON rpg_tts_jobs(session_id, message_id, created_at);

CREATE INDEX idx_rpg_tts_parts_cache
ON rpg_tts_audio_parts(cache_entry_id, part_index);

CREATE INDEX idx_rpg_tts_parts_blob
ON rpg_tts_audio_parts(blob_id);

CREATE INDEX idx_rpg_tts_jobs_cache
ON rpg_tts_jobs(cache_entry_id);

CREATE TABLE rpg_session_story_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    text TEXT NOT NULL DEFAULT '',
    memory_kind TEXT NOT NULL DEFAULT 'event'
        CHECK (memory_kind IN ('character', 'event', 'relationship', 'commitment', 'clue', 'world_fact', 'state_change')),
    epistemic_status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (epistemic_status IN ('confirmed', 'reported', 'inferred', 'uncertain', 'contradicted')),
    salience REAL NOT NULL DEFAULT 0.5 CHECK (salience >= 0.0 AND salience <= 1.0),
    source_turn_start INTEGER NOT NULL CHECK (source_turn_start > 0),
    source_turn_end INTEGER NOT NULL CHECK (source_turn_end >= source_turn_start),
    dedupe_key TEXT NOT NULL CHECK (length(dedupe_key) = 64),
    dream_processed INTEGER NOT NULL DEFAULT 0 CHECK (dream_processed IN (0, 1)),
    metadata_schema_version INTEGER NOT NULL DEFAULT 1 CHECK (metadata_schema_version > 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    UNIQUE (session_id, dedupe_key)
);

CREATE INDEX idx_rpg_session_story_memories_session_id_id
    ON rpg_session_story_memories(session_id, id);

CREATE INDEX idx_rpg_session_story_memories_turn
    ON rpg_session_story_memories(session_id, source_turn_start, source_turn_end, id);

CREATE INDEX idx_rpg_session_story_memories_dream
    ON rpg_session_story_memories(session_id, dream_processed, id);

CREATE INDEX idx_rpg_session_story_memories_kind_status
    ON rpg_session_story_memories(session_id, memory_kind, epistemic_status, id);

CREATE INDEX idx_rpg_session_story_memories_salience
    ON rpg_session_story_memories(session_id, salience DESC, id);

CREATE TABLE rpg_session_dream_proposals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    depth TEXT NOT NULL CHECK (depth IN ('shallow', 'deep')),
    scope TEXT NOT NULL CHECK (scope IN ('incremental', 'full')),
    status TEXT NOT NULL DEFAULT 'generating'
        CHECK (status IN ('generating', 'ready', 'applied', 'rejected', 'failed', 'interrupted', 'stale')),
    history_fingerprint TEXT NOT NULL CHECK (length(history_fingerprint) = 64),
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 64),
    ledger_revision INTEGER NOT NULL DEFAULT 0 CHECK (ledger_revision >= 0),
    next_messages_manifest_json TEXT NOT NULL DEFAULT '{}',
    next_story_memories_manifest_json TEXT NOT NULL DEFAULT '{}',
    next_summary_batches_manifest_json TEXT NOT NULL DEFAULT '{}',
    source_story_memory_ids_json TEXT NOT NULL DEFAULT '[]',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    applied_at TEXT,
    rejected_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ux_rpg_session_dream_proposals_generating
    ON rpg_session_dream_proposals(session_id)
    WHERE status = 'generating';

CREATE INDEX idx_rpg_session_dream_proposals_session_created
    ON rpg_session_dream_proposals(session_id, created_at DESC, id);

CREATE TABLE rpg_session_persistent_memories (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    dedupe_key TEXT NOT NULL CHECK (length(dedupe_key) = 64),
    lifecycle TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle IN ('active', 'retired', 'superseded')),
    current_revision_number INTEGER NOT NULL DEFAULT 1 CHECK (current_revision_number > 0),
    superseded_by_memory_id TEXT,
    created_from_proposal_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (superseded_by_memory_id) REFERENCES rpg_session_persistent_memories(id) ON DELETE SET NULL,
    FOREIGN KEY (created_from_proposal_id) REFERENCES rpg_session_dream_proposals(id) ON DELETE SET NULL,
    UNIQUE (session_id, dedupe_key)
);

CREATE INDEX idx_rpg_session_persistent_memories_session_lifecycle
    ON rpg_session_persistent_memories(session_id, lifecycle, created_at, id);

CREATE TABLE rpg_session_persistent_memory_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    text TEXT NOT NULL CHECK (length(trim(text)) > 0 AND length(text) <= 1000),
    memory_kind TEXT NOT NULL
        CHECK (memory_kind IN ('character', 'event', 'relationship', 'commitment', 'clue', 'world_fact', 'state_change')),
    epistemic_status TEXT NOT NULL
        CHECK (epistemic_status IN ('confirmed', 'reported', 'inferred', 'uncertain', 'contradicted')),
    salience REAL NOT NULL CHECK (salience >= 0.0 AND salience <= 1.0),
    source_proposal_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES rpg_session_persistent_memories(id) ON DELETE CASCADE,
    FOREIGN KEY (source_proposal_id) REFERENCES rpg_session_dream_proposals(id) ON DELETE SET NULL,
    UNIQUE (memory_id, revision_number)
);

CREATE INDEX idx_rpg_session_persistent_memory_revisions_memory
    ON rpg_session_persistent_memory_revisions(memory_id, revision_number DESC);

CREATE TABLE rpg_session_persistent_memory_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL CHECK (message_id > 0),
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    message_version INTEGER NOT NULL CHECK (message_version > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (revision_id) REFERENCES rpg_session_persistent_memory_revisions(id) ON DELETE CASCADE,
    UNIQUE (revision_id, message_id)
);

CREATE INDEX idx_rpg_session_persistent_memory_evidence_message
    ON rpg_session_persistent_memory_evidence(message_id, message_version, content_hash);

CREATE TABLE rpg_session_dream_proposal_items (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('add', 'revise', 'supersede', 'retire')),
    target_memory_id TEXT,
    base_revision_number INTEGER CHECK (base_revision_number IS NULL OR base_revision_number > 0),
    dedupe_key TEXT NOT NULL CHECK (length(dedupe_key) = 64),
    selected INTEGER NOT NULL DEFAULT 1 CHECK (selected IN (0, 1)),
    text TEXT NOT NULL DEFAULT '' CHECK (length(text) <= 1000),
    memory_kind TEXT NOT NULL DEFAULT 'event'
        CHECK (memory_kind IN ('character', 'event', 'relationship', 'commitment', 'clue', 'world_fact', 'state_change')),
    epistemic_status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (epistemic_status IN ('confirmed', 'reported', 'inferred', 'uncertain', 'contradicted')),
    salience REAL NOT NULL DEFAULT 0.5 CHECK (salience >= 0.0 AND salience <= 1.0),
    reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 1000),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_id) REFERENCES rpg_session_dream_proposals(id) ON DELETE CASCADE,
    FOREIGN KEY (target_memory_id) REFERENCES rpg_session_persistent_memories(id) ON DELETE SET NULL
);

CREATE INDEX idx_rpg_session_dream_proposal_items_proposal
    ON rpg_session_dream_proposal_items(proposal_id, sort_order, id);

CREATE TABLE rpg_session_dream_proposal_item_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_item_id TEXT NOT NULL,
    message_id INTEGER NOT NULL CHECK (message_id > 0),
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    message_version INTEGER NOT NULL CHECK (message_version > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_item_id) REFERENCES rpg_session_dream_proposal_items(id) ON DELETE CASCADE,
    UNIQUE (proposal_item_id, message_id)
);

CREATE TABLE rpg_session_dream_states (
    session_id TEXT PRIMARY KEY,
    ledger_revision INTEGER NOT NULL DEFAULT 0 CHECK (ledger_revision >= 0),
    messages_manifest_json TEXT NOT NULL DEFAULT '{}',
    story_memories_manifest_json TEXT NOT NULL DEFAULT '{}',
    summary_batches_manifest_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_rpg_sessions_lifecycle
    ON rpg_sessions(lifecycle, workspace_id, story_id, created_at, id);

CREATE TABLE rpg_session_derivation_jobs (
    id TEXT PRIMARY KEY,
    source_session_id TEXT NOT NULL,
    target_session_id TEXT,
    branch_turn_id INTEGER NOT NULL CHECK (branch_turn_id > 0),
    requested_title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'ready', 'failed', 'interrupted')),
    stage TEXT NOT NULL DEFAULT 'queued'
        CHECK (stage IN (
            'queued',
            'snapshotting',
            'copying',
            'rebuilding_status',
            'extracting_story_memory',
            'summarizing',
            'evaluating_context',
            'finalizing',
            'ready',
            'failed',
            'interrupted'
        )),
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    context_used_tokens INTEGER CHECK (context_used_tokens IS NULL OR context_used_tokens >= 0),
    context_limit INTEGER CHECK (context_limit IS NULL OR context_limit > 0),
    context_threshold_exceeded INTEGER NOT NULL DEFAULT 0
        CHECK (context_threshold_exceeded IN (0, 1)),
    started_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ux_rpg_session_derivation_jobs_active_source
    ON rpg_session_derivation_jobs(source_session_id)
    WHERE status IN ('queued', 'running');

CREATE INDEX idx_rpg_session_derivation_jobs_status_created
    ON rpg_session_derivation_jobs(status, created_at, id);

CREATE INDEX idx_rpg_session_derivation_jobs_target
    ON rpg_session_derivation_jobs(target_session_id);

CREATE TABLE rpg_session_story_memory_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_memory_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL CHECK (message_id > 0),
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    message_version INTEGER NOT NULL CHECK (message_version > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_memory_id) REFERENCES rpg_session_story_memories(id) ON DELETE CASCADE,
    UNIQUE (story_memory_id, message_id)
);

CREATE INDEX idx_rpg_session_story_memory_evidence_message
    ON rpg_session_story_memory_evidence(message_id, message_version, content_hash);

CREATE TABLE rpg_story_openings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    message TEXT NOT NULL CHECK (length(trim(message)) > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, title)
);

CREATE INDEX idx_rpg_story_openings_story
ON rpg_story_openings(story_id, sort_order, id);

CREATE INDEX idx_rpg_session_profiles_story_opening
ON rpg_session_profiles(story_opening_id);

CREATE TABLE rpg_story_plot_event_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    selection_mode TEXT NOT NULL DEFAULT 'random'
        CHECK (selection_mode IN ('random', 'sequential')),
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE
);

CREATE INDEX idx_rpg_story_plot_event_pools_story
ON rpg_story_plot_event_pools(story_id, priority DESC, id);

CREATE TABLE rpg_story_plot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    pool_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    directive TEXT NOT NULL,
    suitability_hint TEXT NOT NULL DEFAULT '',
    dispatch_mode TEXT NOT NULL DEFAULT 'soft'
        CHECK (dispatch_mode IN ('forced', 'soft')),
    scheduled_time_json TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    allow_repeat INTEGER NOT NULL DEFAULT 0 CHECK (allow_repeat IN (0, 1)),
    repeat_cooldown_minutes INTEGER NOT NULL DEFAULT 0
        CHECK (repeat_cooldown_minutes >= 0),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deadline_time_json TEXT,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    FOREIGN KEY (pool_id) REFERENCES rpg_story_plot_event_pools(id) ON DELETE RESTRICT,
    CHECK (
        (allow_repeat = 0 AND repeat_cooldown_minutes = 0)
        OR (allow_repeat = 1 AND repeat_cooldown_minutes > 0)
    )
);

CREATE INDEX idx_rpg_story_plot_events_pool
ON rpg_story_plot_events(pool_id, position, id);

CREATE INDEX idx_rpg_story_plot_events_story
ON rpg_story_plot_events(story_id, id);

CREATE TABLE rpg_story_plot_outlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE
);

CREATE INDEX idx_rpg_story_plot_outlines_story
ON rpg_story_plot_outlines(story_id, priority DESC, id);

CREATE TABLE rpg_story_plot_outline_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    outline_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    scheduled_time_json TEXT NOT NULL,
    dispatch_mode TEXT NOT NULL DEFAULT 'soft'
        CHECK (dispatch_mode IN ('forced', 'soft')),
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    FOREIGN KEY (outline_id) REFERENCES rpg_story_plot_outlines(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES rpg_story_plot_events(id) ON DELETE RESTRICT
);

CREATE INDEX idx_rpg_story_plot_outline_nodes_outline
ON rpg_story_plot_outline_nodes(outline_id, position, id);

CREATE INDEX idx_rpg_story_plot_outline_nodes_story
ON rpg_story_plot_outline_nodes(story_id, id);

CREATE TABLE rpg_session_plot_event_overrides (
    session_id TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 1 CHECK (disabled = 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, event_id),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES rpg_story_plot_events(id) ON DELETE CASCADE
);

CREATE TABLE rpg_session_plot_outline_node_overrides (
    session_id TEXT NOT NULL,
    node_id INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 1 CHECK (disabled = 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, node_id),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (node_id) REFERENCES rpg_story_plot_outline_nodes(id) ON DELETE CASCADE
);

CREATE TABLE rpg_session_plot_pending_injections (
    session_id TEXT PRIMARY KEY,
    story_id INTEGER NOT NULL,
    source_event_id INTEGER NOT NULL CHECK (source_event_id > 0),
    source_event_version INTEGER NOT NULL CHECK (source_event_version > 0),
    source_pool_id INTEGER NOT NULL CHECK (source_pool_id > 0),
    source_pool_name TEXT NOT NULL CHECK (length(trim(source_pool_name)) > 0),
    event_title TEXT NOT NULL CHECK (length(trim(event_title)) > 0),
    directive TEXT NOT NULL CHECK (length(trim(directive)) > 0),
    event_snapshot_json TEXT NOT NULL,
    requested_turn_id INTEGER NOT NULL CHECK (requested_turn_id > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE
);

CREATE INDEX idx_rpg_session_plot_pending_requested_turn
ON rpg_session_plot_pending_injections(session_id, requested_turn_id);

CREATE TABLE rpg_session_plot_scene_opportunities (
    session_id TEXT PRIMARY KEY,
    source_turn_id INTEGER NOT NULL CHECK (source_turn_id > 0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_rpg_session_plot_scene_opportunity_turn
ON rpg_session_plot_scene_opportunities(session_id, source_turn_id);

CREATE TABLE rpg_session_plot_schedule_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('outline', 'pool')),
    source_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    container_id INTEGER NOT NULL,
    decision_status TEXT NOT NULL
        CHECK (decision_status IN ('triggered', 'deferred', 'error')),
    dispatch_mode TEXT NOT NULL CHECK (dispatch_mode IN ('forced', 'soft')),
    selection_origin TEXT NOT NULL DEFAULT 'scheduler'
        CHECK (selection_origin IN ('scheduler', 'manual')),
    scene_time_json TEXT,
    scene_time_ordinal INTEGER CHECK (scene_time_ordinal IS NULL OR scene_time_ordinal >= 0),
    event_snapshot_json TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    CHECK (
        (selection_origin = 'scheduler' AND scene_time_json IS NOT NULL AND scene_time_ordinal IS NOT NULL)
        OR (
            selection_origin = 'manual'
            AND (
                (scene_time_json IS NULL AND scene_time_ordinal IS NULL)
                OR (scene_time_json IS NOT NULL AND scene_time_ordinal IS NOT NULL)
            )
        )
    ),
    UNIQUE (session_id, turn_id, source_kind)
);

CREATE INDEX idx_rpg_session_plot_decisions_session_turn
ON rpg_session_plot_schedule_decisions(session_id, turn_id DESC, id DESC);

CREATE INDEX idx_rpg_session_plot_decisions_session_id
ON rpg_session_plot_schedule_decisions(session_id, id DESC);

CREATE INDEX idx_rpg_session_plot_decisions_source
ON rpg_session_plot_schedule_decisions(session_id, source_kind, source_id, decision_status, turn_id);

INSERT INTO rpg_rp_module_catalog (
    module_name,
    display_name,
    description,
    sort_order,
    config_version,
    default_story_enabled
) VALUES
    (
        'message_mode',
        '消息模式',
        '提供 Neutral、IC、OOC 与 GM 的本轮语义及 GM 玩家角色托管。',
        5,
        1,
        1
    ),
    (
        'narrative_outcome',
        '剧情结果裁定',
        '按五档随机结果裁定存在外部实质变数的剧情分支。',
        10,
        1,
        1
    ),
    (
        'plot_scheduler',
        '剧情动态调度',
        '按照当前 scene 时间动态调度剧情大纲节点与事件池事件。',
        15,
        1,
        1
    ),
    (
        'dice',
        '骰子调试',
        '提供 /roll 与 /check_dc 低层随机调试命令，不进入 LLM 工具 schema。',
        20,
        1,
        1
    );
