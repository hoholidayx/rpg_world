ALTER TABLE rpg_media_assets
ADD COLUMN origin_kind TEXT NOT NULL DEFAULT 'generated'
CHECK (origin_kind IN ('generated', 'upload'));

ALTER TABLE rpg_session_media_backgrounds
ADD COLUMN source_mode TEXT NOT NULL DEFAULT 'manual'
CHECK (source_mode IN ('manual', 'auto'));

CREATE TABLE IF NOT EXISTS rpg_media_library_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL CHECK (scope IN ('story', 'workspace_fallback')),
    story_id INTEGER,
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
        OR (scope = 'workspace_fallback' AND story_id IS NULL)
    ),
    CHECK (scope = 'story' OR is_default = 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_media_library_story_default
ON rpg_media_library_items(story_id)
WHERE scope = 'story' AND is_default = 1;

CREATE INDEX IF NOT EXISTS idx_rpg_media_library_workspace_scope
ON rpg_media_library_items(workspace_id, scope, story_id, created_at, id);

CREATE TABLE IF NOT EXISTS rpg_media_library_item_tags (
    item_id TEXT NOT NULL,
    tag TEXT NOT NULL CHECK (length(trim(tag)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, tag),
    FOREIGN KEY (item_id) REFERENCES rpg_media_library_items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rpg_media_library_tags_tag
ON rpg_media_library_item_tags(tag, item_id);

CREATE TABLE IF NOT EXISTS rpg_session_media_background_states (
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

CREATE TABLE IF NOT EXISTS rpg_media_background_evaluations (
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

CREATE INDEX IF NOT EXISTS idx_rpg_media_background_eval_queue
ON rpg_media_background_evaluations(status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_media_background_eval_session
ON rpg_media_background_evaluations(session_id, created_at, id);
