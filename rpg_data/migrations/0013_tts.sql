CREATE TABLE IF NOT EXISTS rpg_tts_blobs (
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

CREATE TABLE IF NOT EXISTS rpg_tts_cache_entries (
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

CREATE TABLE IF NOT EXISTS rpg_tts_audio_parts (
    id TEXT PRIMARY KEY,
    cache_entry_id TEXT NOT NULL,
    blob_id TEXT NOT NULL,
    part_index INTEGER NOT NULL CHECK (part_index >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cache_entry_id) REFERENCES rpg_tts_cache_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (blob_id) REFERENCES rpg_tts_blobs(id) ON DELETE NO ACTION,
    UNIQUE (cache_entry_id, part_index)
);

CREATE TABLE IF NOT EXISTS rpg_tts_jobs (
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

CREATE INDEX IF NOT EXISTS idx_rpg_tts_jobs_queue
ON rpg_tts_jobs(status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_rpg_tts_jobs_session_message
ON rpg_tts_jobs(session_id, message_id, created_at);

CREATE INDEX IF NOT EXISTS idx_rpg_tts_parts_cache
ON rpg_tts_audio_parts(cache_entry_id, part_index);

CREATE INDEX IF NOT EXISTS idx_rpg_tts_parts_blob
ON rpg_tts_audio_parts(blob_id);

CREATE INDEX IF NOT EXISTS idx_rpg_tts_jobs_cache
ON rpg_tts_jobs(cache_entry_id);
