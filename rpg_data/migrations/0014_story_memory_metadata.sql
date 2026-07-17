-- Story-memory rows are derived RP data. This hard-cut migration intentionally
-- drops legacy rows so core query and deduplication fields can be enforced by
-- SQLite instead of being hidden in metadata_json.
DROP TABLE IF EXISTS rpg_session_story_memories;

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
