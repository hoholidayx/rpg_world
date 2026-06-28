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
    id,
    workspace_id,
    story_id,
    state_json,
    story_memory_last_turn_id
)
VALUES (
    's_forest001',
    'demo_workspace',
    (
        SELECT id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '北境森林 Demo'
    ),
    '{"scene":"北境森林·石林·圆形封印祭坛","time":"第 1 年 1 月 1 日 8 时 30 分"}',
    0
);

INSERT OR IGNORE INTO rpg_session_profiles (
    session_id,
    title,
    metadata_json
)
VALUES (
    's_forest001',
    '北境森林主线',
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_sessions (
    id,
    workspace_id,
    story_id,
    state_json,
    story_memory_last_turn_id
)
VALUES (
    's_academy01',
    'demo_workspace',
    (
        SELECT id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '奥术学院 Demo'
    ),
    '{"scene":"奥术学院·旧档案馆","time":"第 1 年 1 月 3 日 14 时"}',
    0
);

INSERT OR IGNORE INTO rpg_session_profiles (
    session_id,
    title,
    metadata_json
)
VALUES (
    's_academy01',
    '奥术学院档案',
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
    '擅长双手重剑，战斗时喜欢正面冲锋。',
    '["战斗"]',
    10
);

INSERT OR IGNORE INTO rpg_character_details (
    character_id,
    name,
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
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_characters.id,
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
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_lorebook_entries.id,
    CASE rpg_lorebook_entries.name WHEN '炎心之木' THEN 10 ELSE 20 END,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_lorebook_entries ON rpg_lorebook_entries.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND rpg_lorebook_entries.name IN ('炎心之木', '圆形封印祭坛');

INSERT OR IGNORE INTO rpg_status_types (
    workspace_id,
    name,
    builtin_key,
    sort_order,
    metadata_json
)
VALUES (
    'demo_workspace',
    '场景',
    'scene',
    0,
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_status_types (
    workspace_id,
    name,
    builtin_key,
    sort_order,
    metadata_json
)
VALUES (
    'demo_workspace',
    '世界状态',
    '',
    10,
    '{"kind":"demo"}'
);

INSERT OR IGNORE INTO rpg_status_table_templates (
    workspace_id,
    type_id,
    name,
    relative_path,
    description,
    sort_order,
    metadata_json
)
VALUES (
    'demo_workspace',
    (
        SELECT id
        FROM rpg_status_types
        WHERE workspace_id = 'demo_workspace' AND builtin_key = 'scene'
    ),
    '北境森林当前场景',
    'template_status/场景/北境森林当前场景.csv',
    '北境森林演示故事的当前场景。',
    0,
    '{"kind":"demo","_bootstrap_csv":{"headers":["属性","值"],"rows":[["时间","第 1 年 1 月 1 日 8 时 30 分"],["位置","北境森林·石林·圆形封印祭坛"],["在场人物","Bob, Alice"]]}}'
);

INSERT OR IGNORE INTO rpg_status_table_templates (
    workspace_id,
    type_id,
    name,
    relative_path,
    description,
    sort_order,
    metadata_json
)
VALUES (
    'demo_workspace',
    (
        SELECT id
        FROM rpg_status_types
        WHERE workspace_id = 'demo_workspace' AND builtin_key = 'scene'
    ),
    '奥术学院当前场景',
    'template_status/场景/奥术学院当前场景.csv',
    '奥术学院演示故事的当前场景。',
    0,
    '{"kind":"demo","_bootstrap_csv":{"headers":["属性","值"],"rows":[["时间","第 1 年 1 月 3 日 14 时"],["位置","奥术学院·旧档案馆"],["在场人物","Alice"]]}}'
);

INSERT OR IGNORE INTO rpg_status_table_templates (
    workspace_id,
    type_id,
    name,
    relative_path,
    description,
    sort_order,
    metadata_json
)
VALUES (
    'demo_workspace',
    (
        SELECT id
        FROM rpg_status_types
        WHERE workspace_id = 'demo_workspace' AND name = '世界状态'
    ),
    '世界线索',
    'template_status/世界状态/世界线索.csv',
    '演示普通状态表如何进入上下文。',
    10,
    '{"kind":"demo","_bootstrap_csv":{"headers":["项目","状态","备注"],"rows":[["幽蓝封印","异常波动","圆形封印祭坛附近出现微弱蓝光。"],["炎心之木","待调查","相关记载散落在北境与学院档案中。"]]}}'
);

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    status_table_id,
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_status_table_templates.id,
    0,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_status_table_templates
  ON rpg_status_table_templates.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title = '北境森林 Demo'
  AND rpg_status_table_templates.name = '北境森林当前场景';

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    status_table_id,
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_status_table_templates.id,
    0,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_status_table_templates
  ON rpg_status_table_templates.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title = '奥术学院 Demo'
  AND rpg_status_table_templates.name = '奥术学院当前场景';

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    status_table_id,
    sort_order,
    metadata_json
)
SELECT
    'demo_workspace',
    rpg_stories.id,
    rpg_status_table_templates.id,
    10,
    '{"kind":"demo"}'
FROM rpg_stories
JOIN rpg_status_table_templates
  ON rpg_status_table_templates.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND rpg_status_table_templates.name = '世界线索';
