ALTER TABLE rpg_stories
ADD COLUMN narrative_outcome_weights_json TEXT;

ALTER TABLE rpg_session_profiles
ADD COLUMN narrative_outcome_weights_json TEXT;

CREATE TABLE IF NOT EXISTS rpg_session_narrative_outcomes (
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

CREATE INDEX IF NOT EXISTS idx_rpg_session_narrative_outcomes_session_turn
ON rpg_session_narrative_outcomes(session_id, turn_id);
