CREATE TABLE IF NOT EXISTS rpg_media_blobs (
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

CREATE TABLE IF NOT EXISTS rpg_media_assets (
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
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (blob_id) REFERENCES rpg_media_blobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_media_jobs (
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

CREATE TABLE IF NOT EXISTS rpg_session_media_gallery_items (
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

CREATE TABLE IF NOT EXISTS rpg_session_media_backgrounds (
    session_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES rpg_media_assets(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rpg_media_blobs_workspace_sha
ON rpg_media_blobs(workspace_id, sha256);

CREATE INDEX IF NOT EXISTS idx_rpg_media_assets_workspace_created
ON rpg_media_assets(workspace_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_media_assets_blob
ON rpg_media_assets(blob_id);

CREATE INDEX IF NOT EXISTS idx_rpg_media_jobs_queue
ON rpg_media_jobs(status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_media_jobs_session_created
ON rpg_media_jobs(session_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_session_media_gallery_session_created
ON rpg_session_media_gallery_items(session_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_session_media_background_asset
ON rpg_session_media_backgrounds(asset_id);
