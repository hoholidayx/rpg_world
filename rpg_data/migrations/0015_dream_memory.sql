ALTER TABLE rpg_session_story_memories
    ADD COLUMN source_messages_manifest_json TEXT NOT NULL DEFAULT '[]';

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

-- message_id intentionally has no foreign key: evidence survives mutable-history
-- deletion so validity can be checked and old revisions remain auditable.
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
