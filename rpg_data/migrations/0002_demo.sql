INSERT OR IGNORE INTO rpg_workspaces (
    id,
    name,
    root_path,
    description,
    metadata_json
)
VALUES (
    'demo_workspace',
    'Demo Workspace',
    'data/demo_workspace',
    'Demo workspace for RPG World data module examples',
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_stories (
    workspace_id,
    title,
    summary,
    description,
    metadata_json
)
VALUES (
    'demo_workspace',
    '北境森林 Demo',
    'Bob 与 Alice 在北境森林追查幽蓝封印。',
    '用于验证 workspace、story、session、角色卡与 lorebook 挂载关系的演示故事。',
    '{"kind":"demo","order":1}'
);

INSERT OR IGNORE INTO rpg_stories (
    workspace_id,
    title,
    summary,
    description,
    metadata_json
)
VALUES (
    'demo_workspace',
    '奥术学院 Demo',
    'Alice 返回学院调查炎心之木的旧档案。',
    '用于验证同一角色卡和 lorebook entry 可挂载到多个 story。',
    '{"kind":"demo","order":2}'
);

INSERT OR IGNORE INTO rpg_sessions (
    workspace_id,
    story_id,
    session_key,
    title,
    state_json,
    last_story_turn_index,
    metadata_json
)
VALUES (
    'demo_workspace',
    (
        SELECT id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '北境森林 Demo'
    ),
    'demo_forest_main',
    '北境森林主线',
    '{"scene":"北境森林·石林·圆形封印祭坛","time":"第 1 年 1 月 1 日 8 时 30 分"}',
    0,
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_sessions (
    workspace_id,
    story_id,
    session_key,
    title,
    state_json,
    last_story_turn_index,
    metadata_json
)
VALUES (
    'demo_workspace',
    (
        SELECT id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '奥术学院 Demo'
    ),
    'demo_academy_main',
    '奥术学院档案',
    '{"scene":"奥术学院·旧档案馆","time":"第 1 年 1 月 3 日 14 时"}',
    0,
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_characters (
    workspace_id,
    name,
    personality,
    content,
    metadata_json
)
VALUES (
    'demo_workspace',
    'Bob',
    'bold',
    'A brave knight who favors direct charges and two-handed swords.',
    '{"kind":"demo","role":"player"}'
);

INSERT OR IGNORE INTO rpg_characters (
    workspace_id,
    name,
    personality,
    content,
    metadata_json
)
VALUES (
    'demo_workspace',
    'Alice',
    'curious',
    'A young wizard from the Arcanum Academy with a talent for elemental magic.',
    '{"kind":"demo","role":"companion"}'
);

INSERT OR IGNORE INTO rpg_character_details (
    character_id,
    name,
    enabled,
    content,
    tags_json,
    sort_order
)
VALUES (
    (
        SELECT id
        FROM rpg_characters
        WHERE workspace_id = 'demo_workspace' AND name = 'Bob'
    ),
    '战斗风格',
    1,
    '擅长双手重剑，战斗时喜欢正面冲锋。',
    '["战斗"]',
    10
);

INSERT OR IGNORE INTO rpg_character_details (
    character_id,
    name,
    enabled,
    content,
    tags_json,
    sort_order
)
VALUES (
    (
        SELECT id
        FROM rpg_characters
        WHERE workspace_id = 'demo_workspace' AND name = 'Alice'
    ),
    '外貌',
    1,
    '银白色长发，紫罗兰色瞳孔，战斗时穿轻便法师袍。',
    '["外观"]',
    10
);

INSERT OR IGNORE INTO rpg_lorebook_entries (
    workspace_id,
    name,
    content,
    description,
    tags_json,
    metadata_json
)
VALUES (
    'demo_workspace',
    '炎心之木',
    '北境森林传说中的世界之树，树干中流淌着永不熄灭的火焰。',
    '与火焰符文和最初的燃烧有关的核心传说。',
    '["history","magic"]',
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_lorebook_entries (
    workspace_id,
    name,
    content,
    description,
    tags_json,
    metadata_json
)
VALUES (
    'demo_workspace',
    '圆形封印祭坛',
    '北境森林石林深处的青石板空地，中央金属圆盘微微渗出幽蓝光芒。',
    '用于演示场景与世界设定词条。',
    '["scene","seal"]',
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_story_characters (
    workspace_id,
    story_id,
    character_id,
    enabled,
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_characters.id,
    1,
    CASE rpg_characters.name WHEN 'Bob' THEN 10 ELSE 20 END,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_characters ON rpg_characters.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND rpg_characters.name IN ('Bob', 'Alice');

INSERT OR IGNORE INTO rpg_story_lorebook_entries (
    workspace_id,
    story_id,
    lorebook_entry_id,
    enabled,
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_lorebook_entries.id,
    1,
    CASE rpg_lorebook_entries.name WHEN '炎心之木' THEN 10 ELSE 20 END,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_lorebook_entries ON rpg_lorebook_entries.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND rpg_lorebook_entries.name IN ('炎心之木', '圆形封印祭坛');
