INSERT INTO rpg_rp_module_catalog (
    module_name,
    display_name,
    description,
    sort_order,
    config_version,
    default_story_enabled
) VALUES (
    'plot_scheduler',
    '剧情动态调度',
    '按照当前 scene 时间动态调度剧情大纲节点与事件池事件。',
    15,
    1,
    1
);

CREATE TABLE IF NOT EXISTS rpg_story_plot_event_pools (
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

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_event_pools_story
ON rpg_story_plot_event_pools(story_id, priority DESC, id);

CREATE TABLE IF NOT EXISTS rpg_story_plot_events (
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
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    FOREIGN KEY (pool_id) REFERENCES rpg_story_plot_event_pools(id) ON DELETE RESTRICT,
    CHECK (
        (allow_repeat = 0 AND repeat_cooldown_minutes = 0)
        OR (allow_repeat = 1 AND repeat_cooldown_minutes > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_events_pool
ON rpg_story_plot_events(pool_id, position, id);

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_events_story
ON rpg_story_plot_events(story_id, id);

CREATE TABLE IF NOT EXISTS rpg_story_plot_outlines (
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

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_outlines_story
ON rpg_story_plot_outlines(story_id, priority DESC, id);

CREATE TABLE IF NOT EXISTS rpg_story_plot_outline_nodes (
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

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_outline_nodes_outline
ON rpg_story_plot_outline_nodes(outline_id, position, id);

CREATE INDEX IF NOT EXISTS idx_rpg_story_plot_outline_nodes_story
ON rpg_story_plot_outline_nodes(story_id, id);

CREATE TABLE IF NOT EXISTS rpg_session_plot_event_overrides (
    session_id TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 1 CHECK (disabled = 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, event_id),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES rpg_story_plot_events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_plot_outline_node_overrides (
    session_id TEXT NOT NULL,
    node_id INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 1 CHECK (disabled = 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, node_id),
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (node_id) REFERENCES rpg_story_plot_outline_nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpg_session_plot_schedule_decisions (
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
    scene_time_json TEXT NOT NULL,
    scene_time_ordinal INTEGER NOT NULL CHECK (scene_time_ordinal >= 0),
    event_snapshot_json TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    UNIQUE (session_id, turn_id, source_kind)
);

CREATE INDEX IF NOT EXISTS idx_rpg_session_plot_decisions_session_turn
ON rpg_session_plot_schedule_decisions(session_id, turn_id DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_rpg_session_plot_decisions_session_id
ON rpg_session_plot_schedule_decisions(session_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_rpg_session_plot_decisions_source
ON rpg_session_plot_schedule_decisions(session_id, source_kind, source_id, decision_status, turn_id);
