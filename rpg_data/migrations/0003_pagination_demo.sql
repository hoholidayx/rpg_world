INSERT OR IGNORE INTO rpg_stories (
    workspace_id,
    title,
    summary,
    story_prompt,
    first_message,
    metadata_json
)
VALUES (
    'demo_workspace',
    '分页压力测试 Demo',
    '专用于验证 Play WebUI 历史分页滑动窗口的长历史故事。',
    '分页测试专用背景：这不是正式 RP 剧情，只用于验证 history-page 接口、按 turn 分页、两段 buffer 缓存、顶部/底部边界加载和长历史渲染性能。',
    '分页测试会话已经预置大量短 turn。请在时间线上滚动到顶部或底部，验证历史分页窗口是否按需切换。',
    '{"kind":"pagination_demo","order":99,"purpose":"history_pagination"}'
);

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
        SELECT id
        FROM rpg_stories
        WHERE workspace_id = 'demo_workspace' AND title = '分页压力测试 Demo'
    ),
    '{"scene":"分页测试·长历史记录","time":"分页测试第 1 页"}'
);

INSERT OR IGNORE INTO rpg_session_profiles (
    session_id,
    title,
    description,
    metadata_json
)
VALUES (
    's_pagination001',
    '分页压力测试长历史',
    '专用于验证 Play WebUI 历史分页滑动窗口的预置长会话。',
    '{"kind":"pagination_demo"}'
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
    10,
    '{"kind":"pagination_demo"}'
FROM rpg_stories
JOIN rpg_characters ON rpg_characters.workspace_id = rpg_stories.workspace_id
WHERE rpg_stories.workspace_id = 'demo_workspace'
  AND rpg_stories.title = '分页压力测试 Demo'
  AND rpg_characters.name = 'Bob';

UPDATE rpg_session_profiles
SET
    player_character_id = (
        SELECT rpg_characters.id
        FROM rpg_characters
        WHERE rpg_characters.workspace_id = 'demo_workspace'
          AND rpg_characters.name = 'Bob'
    ),
    player_character_snapshot_json = (
        SELECT
            '{"characterId":' || rpg_characters.id
            || ',"mountId":' || rpg_story_characters.id
            || ',"storyId":' || rpg_stories.id
            || ',"name":"Bob","avatarUrl":"","roleLabel":"","updatedAt":"' || rpg_characters.updated_at || '"}'
        FROM rpg_story_characters
        JOIN rpg_characters ON rpg_characters.id = rpg_story_characters.character_id
        JOIN rpg_stories ON rpg_stories.id = rpg_story_characters.story_id
        WHERE rpg_story_characters.workspace_id = 'demo_workspace'
          AND rpg_stories.title = '分页压力测试 Demo'
          AND rpg_characters.name = 'Bob'
    )
WHERE session_id = 's_pagination001';

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
