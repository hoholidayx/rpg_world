CREATE TABLE IF NOT EXISTS rpg_workspaces (
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

CREATE TABLE IF NOT EXISTS rpg_stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    -- Story-level fixed system prompt; stored now and planned for fix layer integration later.
    story_prompt TEXT NOT NULL DEFAULT '',
    first_message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, title),
    UNIQUE (id, workspace_id)
);

CREATE TABLE IF NOT EXISTS rpg_sessions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    -- 会话必须绑定到同一 workspace 下的 story，避免跨 workspace 误挂载。
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_profiles (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    player_character_id INTEGER,
    player_character_snapshot_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 可读标题/描述独立存放，rpg_sessions.id 保持稳定的公开定位 ID。
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    turn_id INTEGER NOT NULL DEFAULT 0,
    seq_in_turn INTEGER NOT NULL DEFAULT 0,
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
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_backup_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    turn_id INTEGER NOT NULL DEFAULT 0,
    seq_in_turn INTEGER NOT NULL DEFAULT 0,
    tool_call_id TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_story_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL DEFAULT '',
    dream_processed INTEGER NOT NULL DEFAULT 0 CHECK (dream_processed IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    personality TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, name),
    UNIQUE (id, workspace_id)
);

CREATE TABLE IF NOT EXISTS rpg_character_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES rpg_characters(id) ON DELETE CASCADE,
    UNIQUE (character_id, name)
);

CREATE TABLE IF NOT EXISTS rpg_lorebook_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, name),
    UNIQUE (id, workspace_id)
);

CREATE TABLE IF NOT EXISTS rpg_story_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    -- 角色卡可挂载到多个 story；这里只禁止同一 story 重复挂同一角色。
    FOREIGN KEY (character_id, workspace_id) REFERENCES rpg_characters(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, character_id)
);

CREATE TABLE IF NOT EXISTS rpg_story_lorebook_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    lorebook_entry_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    -- 世界书条目可挂载到多个 story；这里只禁止同一 story 重复挂同一条目。
    FOREIGN KEY (lorebook_entry_id, workspace_id) REFERENCES rpg_lorebook_entries(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, lorebook_entry_id)
);

CREATE TABLE IF NOT EXISTS rpg_status_table_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
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
    UNIQUE (workspace_id, name),
    UNIQUE (id, workspace_id)
);

CREATE TABLE IF NOT EXISTS rpg_story_status_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    status_table_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (status_table_id, workspace_id) REFERENCES rpg_status_table_templates(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, status_table_id)
);

CREATE TABLE IF NOT EXISTS rpg_session_status_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    source_table_id INTEGER,
    origin TEXT NOT NULL CHECK (origin IN ('template_copy', 'session_native')),
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
    FOREIGN KEY (source_table_id) REFERENCES rpg_status_table_templates(id) ON DELETE SET NULL,
    UNIQUE (session_id, name)
);

CREATE INDEX IF NOT EXISTS idx_rpg_stories_workspace_id ON rpg_stories(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_sessions_workspace_id ON rpg_sessions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_sessions_story_id ON rpg_sessions(story_id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_messages_session_id_id ON rpg_session_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_messages_turn ON rpg_session_messages(session_id, turn_id, seq_in_turn, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_messages_summary_cursor ON rpg_session_messages(session_id, summary_processed, turn_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_messages_story_cursor ON rpg_session_messages(session_id, story_memory_processed, turn_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_backup_messages_session_id_id ON rpg_session_backup_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_backup_messages_turn ON rpg_session_backup_messages(session_id, turn_id, seq_in_turn, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_story_memories_session_id_id ON rpg_session_story_memories(session_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_story_memories_turn ON rpg_session_story_memories(session_id, turn_id, id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_story_memories_dream ON rpg_session_story_memories(session_id, dream_processed, id);
CREATE INDEX IF NOT EXISTS idx_rpg_characters_workspace_id ON rpg_characters(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_character_details_character_id ON rpg_character_details(character_id);
CREATE INDEX IF NOT EXISTS idx_rpg_lorebook_entries_workspace_id ON rpg_lorebook_entries(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_characters_workspace_id ON rpg_story_characters(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_characters_story_id ON rpg_story_characters(story_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_characters_character_id ON rpg_story_characters(character_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_lorebook_entries_workspace_id ON rpg_story_lorebook_entries(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_lorebook_entries_story_id ON rpg_story_lorebook_entries(story_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_lorebook_entries_lorebook_entry_id ON rpg_story_lorebook_entries(lorebook_entry_id);
CREATE INDEX IF NOT EXISTS idx_rpg_status_table_templates_workspace_id ON rpg_status_table_templates(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_status_table_templates_kind ON rpg_status_table_templates(workspace_id, status_kind);
CREATE INDEX IF NOT EXISTS idx_rpg_story_status_tables_workspace_id ON rpg_story_status_tables(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_status_tables_story_id ON rpg_story_status_tables(story_id);
CREATE INDEX IF NOT EXISTS idx_rpg_story_status_tables_status_table_id ON rpg_story_status_tables(status_table_id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_status_tables_session_id ON rpg_session_status_tables(session_id);
CREATE INDEX IF NOT EXISTS idx_rpg_session_status_tables_kind ON rpg_session_status_tables(session_id, status_kind);
