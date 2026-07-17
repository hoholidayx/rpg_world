ALTER TABLE rpg_sessions
    ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'ready'
        CHECK (lifecycle IN ('provisioning', 'ready'));

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
