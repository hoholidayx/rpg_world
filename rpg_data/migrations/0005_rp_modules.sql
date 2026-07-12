CREATE TABLE IF NOT EXISTS rpg_rp_module_catalog (
    module_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    config_version INTEGER NOT NULL DEFAULT 1 CHECK (config_version > 0),
    default_story_enabled INTEGER NOT NULL DEFAULT 1 CHECK (default_story_enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO rpg_rp_module_catalog (
    module_name,
    display_name,
    description,
    sort_order,
    config_version,
    default_story_enabled
) VALUES
    (
        'narrative_outcome',
        '剧情结果裁定',
        '按五档随机结果裁定存在外部实质变数的剧情分支。',
        10,
        1,
        1
    ),
    (
        'dice',
        '骰子调试',
        '提供 /roll 与 /check_dc 低层随机调试命令，不进入 LLM 工具 schema。',
        20,
        1,
        1
    );

CREATE TABLE IF NOT EXISTS rpg_story_rp_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    module_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    config_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    FOREIGN KEY (module_name) REFERENCES rpg_rp_module_catalog(module_name) ON DELETE CASCADE,
    UNIQUE (story_id, module_name)
);

CREATE INDEX IF NOT EXISTS idx_rpg_story_rp_modules_story_sort
ON rpg_story_rp_modules(story_id, module_name);

INSERT INTO rpg_story_rp_modules (story_id, module_name, enabled, config_json)
SELECT stories.id, modules.module_name, 1, '{}'
FROM rpg_stories AS stories
CROSS JOIN rpg_rp_module_catalog AS modules
WHERE modules.default_story_enabled = 1;

CREATE TABLE IF NOT EXISTS rpg_session_rp_module_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    module_name TEXT NOT NULL,
    enabled INTEGER CHECK (enabled IS NULL OR enabled IN (0, 1)),
    config_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES rpg_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (module_name) REFERENCES rpg_rp_module_catalog(module_name) ON DELETE CASCADE,
    UNIQUE (session_id, module_name)
);

CREATE INDEX IF NOT EXISTS idx_rpg_session_rp_module_overrides_session
ON rpg_session_rp_module_overrides(session_id, module_name);

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
