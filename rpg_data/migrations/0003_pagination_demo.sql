-- Long-history demo. Its character is owned by this Story and is not shared.

INSERT OR IGNORE INTO rpg_stories (
    workspace_id,
    title,
    summary,
    story_prompt,
    metadata_json
)
VALUES (
    'demo_workspace',
    '分页压力测试 Demo',
    '专用于验证 Play WebUI 历史分页滑动窗口的长历史故事。',
    '分页测试专用背景：这不是正式 RP 剧情，只用于验证 history-page 接口、按 turn 分页、两段 buffer 缓存、顶部/底部边界加载和长历史渲染性能。',
    '{"kind":"pagination_demo","order":99,"purpose":"history_pagination"}'
);

INSERT OR IGNORE INTO rpg_story_openings (
    workspace_id,
    story_id,
    title,
    message,
    sort_order
)
SELECT
    workspace_id,
    id,
    '分页测试开局',
    '分页测试会话已经预置大量短 turn。请在时间线上滚动到顶部或底部，验证历史分页窗口是否按需切换。',
    0
FROM rpg_stories
WHERE workspace_id = 'demo_workspace'
  AND title = '分页压力测试 Demo';

INSERT OR IGNORE INTO rpg_sessions (
    id,
    workspace_id,
    story_id,
    state_json
)
VALUES (
    's_pagination001',
    'demo_workspace',
    (
        SELECT id FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '分页压力测试 Demo'
    ),
    '{"scene":"分页测试·长历史记录","time":"分页测试第 1 页"}'
);

INSERT OR IGNORE INTO rpg_session_profiles (
    session_id,
    title,
    description,
    story_opening_id,
    metadata_json
)
VALUES (
    's_pagination001',
    '分页压力测试长历史',
    '专用于验证 Play WebUI 历史分页滑动窗口的预置长会话。',
    (
        SELECT openings.id
        FROM rpg_story_openings AS openings
        JOIN rpg_stories AS stories ON stories.id = openings.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '分页压力测试 Demo'
        ORDER BY openings.sort_order, openings.id
        LIMIT 1
    ),
    '{"kind":"pagination_demo"}'
);

INSERT OR IGNORE INTO rpg_story_characters (
    workspace_id,
    story_id,
    name,
    personality,
    content,
    sort_order,
    metadata_json
)
SELECT
    workspace_id,
    id,
    'Bob',
    'bold',
    'Pagination-demo player character owned only by this Story.',
    10,
    '{"kind":"pagination_demo"}'
FROM rpg_stories
WHERE workspace_id = 'demo_workspace'
  AND title = '分页压力测试 Demo';

UPDATE rpg_session_profiles
SET
    player_character_id = (
        SELECT characters.id
        FROM rpg_story_characters AS characters
        JOIN rpg_stories AS stories ON stories.id = characters.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '分页压力测试 Demo'
          AND characters.name = 'Bob'
    ),
    player_character_snapshot_json = (
        SELECT
            '{"characterId":' || characters.id
            || ',"storyId":' || stories.id
            || ',"name":"Bob","avatarUrl":"","roleLabel":"","updatedAt":"' || characters.updated_at || '"}'
        FROM rpg_story_characters AS characters
        JOIN rpg_stories AS stories ON stories.id = characters.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '分页压力测试 Demo'
          AND characters.name = 'Bob'
    )
WHERE session_id = 's_pagination001';

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
JOIN rpg_narrative_styles AS styles ON styles.workspace_id = stories.workspace_id
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title = '分页压力测试 Demo';

INSERT OR IGNORE INTO rpg_story_rp_modules (
    story_id,
    module_name,
    enabled,
    config_json
)
SELECT
    stories.id,
    modules.module_name,
    1,
    '{}'
FROM rpg_stories AS stories
CROSS JOIN rpg_rp_module_catalog AS modules
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title = '分页压力测试 Demo'
  AND modules.default_story_enabled = 1;

WITH RECURSIVE turn_numbers(turn_id) AS (
    SELECT 1
    UNION ALL
    SELECT turn_id + 1
    FROM turn_numbers
    WHERE turn_id < 160
),
pagination_messages AS (
    SELECT
        's_pagination001' AS session_id,
        'user' AS role,
        '分页测试 user turn ' || printf('%03d', turn_id) AS content,
        turn_id,
        1 AS seq_in_turn,
        '{"kind":"pagination_demo","speaker":"Bob"}' AS metadata_json
    FROM turn_numbers

    UNION ALL

    SELECT
        's_pagination001' AS session_id,
        'assistant' AS role,
        '分页测试 assistant turn ' || printf('%03d', turn_id) AS content,
        turn_id,
        2 AS seq_in_turn,
        '{"kind":"pagination_demo","speaker":"Narrator"}' AS metadata_json
    FROM turn_numbers
)
INSERT INTO rpg_session_messages (
    session_id,
    role,
    content,
    turn_id,
    seq_in_turn,
    metadata_json
)
SELECT
    pagination_messages.session_id,
    pagination_messages.role,
    pagination_messages.content,
    pagination_messages.turn_id,
    pagination_messages.seq_in_turn,
    pagination_messages.metadata_json
FROM pagination_messages
WHERE NOT EXISTS (
    SELECT 1
    FROM rpg_session_messages existing
    WHERE existing.session_id = pagination_messages.session_id
      AND existing.turn_id = pagination_messages.turn_id
      AND existing.seq_in_turn = pagination_messages.seq_in_turn
)
ORDER BY pagination_messages.turn_id, pagination_messages.seq_in_turn;
INSERT INTO rpg_session_backup_messages (
    session_id,
    role,
    content,
    turn_id,
    seq_in_turn,
    metadata_json
)
SELECT
    session_id,
    role,
    content,
    turn_id,
    seq_in_turn,
    metadata_json
FROM rpg_session_messages pagination_messages
WHERE pagination_messages.session_id = 's_pagination001'
  AND pagination_messages.metadata_json LIKE '%"kind":"pagination_demo"%'
  AND NOT EXISTS (
      SELECT 1
      FROM rpg_session_backup_messages existing
      WHERE existing.session_id = pagination_messages.session_id
        AND existing.turn_id = pagination_messages.turn_id
        AND existing.seq_in_turn = pagination_messages.seq_in_turn
  )
ORDER BY pagination_messages.turn_id, pagination_messages.seq_in_turn;
