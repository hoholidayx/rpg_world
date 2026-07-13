CREATE TABLE IF NOT EXISTS rpg_session_status_deferred_progress (
    session_status_table_id INTEGER NOT NULL,
    field_key TEXT NOT NULL,
    last_processed_turn_id INTEGER NOT NULL DEFAULT 0 CHECK (last_processed_turn_id >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_status_table_id, field_key),
    FOREIGN KEY (session_status_table_id) REFERENCES rpg_session_status_tables(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_status_deferred_progress_table
ON rpg_session_status_deferred_progress(session_status_table_id);
