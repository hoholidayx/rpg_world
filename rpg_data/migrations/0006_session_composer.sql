ALTER TABLE rpg_session_messages
ADD COLUMN mode TEXT NOT NULL DEFAULT 'ic'
CHECK (mode IN ('ic', 'ooc', 'gm'));

ALTER TABLE rpg_session_backup_messages
ADD COLUMN mode TEXT NOT NULL DEFAULT 'ic'
CHECK (mode IN ('ic', 'ooc', 'gm'));

CREATE TABLE IF NOT EXISTS rpg_workspace_turn_modes (
    workspace_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('ic', 'ooc', 'gm')),
    short_name TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, mode),
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO rpg_workspace_turn_modes (
    workspace_id,
    mode,
    short_name,
    prompt,
    sort_order
)
SELECT
    workspaces.id,
    defaults.mode,
    defaults.short_name,
    defaults.prompt,
    defaults.sort_order
FROM rpg_workspaces AS workspaces
CROSS JOIN (
    SELECT
        'ic' AS mode,
        '角色内' AS short_name,
        '将本轮输入视为玩家角色在故事内的行动或发言，保持沉浸式叙事并自然推进当前场景。' AS prompt,
        10 AS sort_order
    UNION ALL
    SELECT
        'ooc',
        '场外',
        '将本轮输入视为场外讨论：直接、清晰地回应，不推进剧情，不产生剧情裁定或状态变化。',
        20
    UNION ALL
    SELECT
        'gm',
        '主持',
        '将本轮输入视为主持人或导演指令，在遵守既有事实的前提下执行指令，并同步已经确定的剧情状态变化。',
        30
) AS defaults;

CREATE TABLE IF NOT EXISTS rpg_narrative_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, name),
    UNIQUE (id, workspace_id)
);

INSERT OR IGNORE INTO rpg_narrative_styles (
    workspace_id,
    name,
    prompt,
    sort_order
)
SELECT
    workspaces.id,
    defaults.name,
    defaults.prompt,
    defaults.sort_order
FROM rpg_workspaces AS workspaces
CROSS JOIN (
    SELECT
        '细腻描写' AS name,
        '请用细腻描写推进这一幕。' AS prompt,
        10 AS sort_order
    UNION ALL
    SELECT
        '快速推进',
        '请快速推进到下一个关键选择。',
        20
    UNION ALL
    SELECT
        '多给选项',
        '请在回应末尾给出多个可选择的行动方向。',
        30
) AS defaults;

CREATE TABLE IF NOT EXISTS rpg_story_narrative_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    narrative_style_id INTEGER NOT NULL,
    is_base INTEGER NOT NULL DEFAULT 0 CHECK (is_base IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (narrative_style_id, workspace_id) REFERENCES rpg_narrative_styles(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, narrative_style_id)
);

CREATE INDEX IF NOT EXISTS idx_rpg_story_narrative_styles_story
ON rpg_story_narrative_styles(story_id, sort_order, id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_rpg_story_narrative_styles_base
ON rpg_story_narrative_styles(story_id)
WHERE is_base = 1;

INSERT OR IGNORE INTO rpg_story_narrative_styles (
    workspace_id,
    story_id,
    narrative_style_id,
    is_base,
    sort_order
)
SELECT
    stories.workspace_id,
    stories.id,
    styles.id,
    0,
    styles.sort_order
FROM rpg_stories AS stories
JOIN rpg_narrative_styles AS styles
  ON styles.workspace_id = stories.workspace_id;

CREATE TABLE IF NOT EXISTS rpg_story_quick_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, title)
);

CREATE INDEX IF NOT EXISTS idx_rpg_story_quick_replies_story
ON rpg_story_quick_replies(story_id, enabled, sort_order, id);
