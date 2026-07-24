-- Demo data for the clean Story-owned schema.

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
    story_prompt,
    metadata_json
)
VALUES
    (
        'demo_workspace',
        '北境森林 Demo',
        'Bob 与 Alice 在北境森林追查幽蓝封印。',
        '用于验证 Story 直属角色卡、世界书、状态表与 Session 运行时副本的演示故事。',
        '{"kind":"demo","order":1}'
    ),
    (
        'demo_workspace',
        '奥术学院 Demo',
        'Alice 返回学院调查炎心之木的旧档案。',
        '用于验证不同 Story 各自拥有独立角色卡、世界书与状态表。',
        '{"kind":"demo","order":2}'
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
    '默认开局',
    CASE title
        WHEN '北境森林 Demo' THEN '北境森林的霜雾刚漫过石林入口，幽蓝封印在远处一明一暗。你——{USER_PLAY_ROLE_NAME}——听见祭坛方向再次传来潮声。'
        ELSE '旧档案馆的铜铃在午后轻响，管理员莫兰把一叠封蜡破损的登记簿推到桌边，看向你：“{USER_PLAY_ROLE_NAME}，如果你真要查炎心之木，就从这一本开始。”'
    END,
    0
FROM rpg_stories
WHERE workspace_id = 'demo_workspace'
  AND title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_sessions (
    id,
    workspace_id,
    story_id,
    state_json
)
VALUES
    (
        's_forest001',
        'demo_workspace',
        (
            SELECT id FROM rpg_stories
            WHERE workspace_id = 'demo_workspace' AND title = '北境森林 Demo'
        ),
        '{"scene":"北境森林·石林·圆形封印祭坛","time":"第 1 年 1 月 1 日 8 时 30 分"}'
    ),
    (
        's_academy01',
        'demo_workspace',
        (
            SELECT id FROM rpg_stories
            WHERE workspace_id = 'demo_workspace' AND title = '奥术学院 Demo'
        ),
        '{"scene":"奥术学院·旧档案馆","time":"第 1 年 1 月 3 日 14 时"}'
    );

INSERT OR IGNORE INTO rpg_session_profiles (
    session_id,
    title,
    story_opening_id,
    metadata_json
)
VALUES
    (
        's_forest001',
        '北境森林主线',
        (
            SELECT openings.id
            FROM rpg_story_openings AS openings
            JOIN rpg_stories AS stories ON stories.id = openings.story_id
            WHERE stories.workspace_id = 'demo_workspace'
              AND stories.title = '北境森林 Demo'
            ORDER BY openings.sort_order, openings.id
            LIMIT 1
        ),
        '{"kind":"demo"}'
    ),
    (
        's_academy01',
        '奥术学院档案',
        (
            SELECT openings.id
            FROM rpg_story_openings AS openings
            JOIN rpg_stories AS stories ON stories.id = openings.story_id
            WHERE stories.workspace_id = 'demo_workspace'
              AND stories.title = '奥术学院 Demo'
            ORDER BY openings.sort_order, openings.id
            LIMIT 1
        ),
        '{"kind":"demo"}'
    );

INSERT INTO rpg_session_messages (
    session_id,
    role,
    content,
    turn_id,
    seq_in_turn,
    metadata_json
)
SELECT
    demo_messages.session_id,
    demo_messages.role,
    demo_messages.content,
    demo_messages.turn_id,
    demo_messages.seq_in_turn,
    demo_messages.metadata_json
FROM (
    SELECT 's_forest001' AS session_id, 'user' AS role, '我拨开覆盖在石林入口的霜藤，确认 Alice 是否跟在身后。' AS content, 1 AS turn_id, 1 AS seq_in_turn, '{"kind":"demo","speaker":"Bob"}' AS metadata_json
    UNION ALL SELECT 's_forest001', 'assistant', '霜藤被剑鞘挑开，露出一条向下倾斜的青石小径。Alice 把斗篷帽檐压低，指尖浮起一粒冷蓝色火星：“封印的光比昨晚更亮了。”', 1, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我让 Alice 先别靠近圆盘，自己蹲下检查石板上有没有新鲜脚印。', 2, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '石板缝里有半枚湿泥脚印，鞋底纹路细窄，不像巡林人的重靴。脚印一路绕开主径，停在祭坛东侧一块刻着火焰纹的立石前。', 2, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我低声问 Alice：学院里有人会用这种鞋底纹路吗？', 3, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', 'Alice 的表情僵了一瞬：“高阶学徒常穿软底靴进档案塔，但他们不该知道这座祭坛的位置。”她把冷蓝火星靠近脚印，火星突然向东偏折。', 3, 2, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_forest001', 'user', '我沿着火星偏折的方向看过去，寻找有没有被移动过的石块。', 4, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '东侧立石背后，一枚刻着树枝图案的铜扣卡在裂缝里。铜扣边缘还残留微热，像刚从某件制服上扯下来。', 4, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我把铜扣交给 Alice，看她能不能认出树枝图案。', 5, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', 'Alice 用拇指擦去铜扣上的灰，声音压得很低：“这是炎心之木研究会的旧徽记。学院二十年前就禁止这个社团活动了。”', 5, 2, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_forest001', 'user', '我问她这个研究会为什么被禁止，同时注意祭坛圆盘有没有变化。', 6, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '“他们试图把封印当作燃料。”Alice 话音刚落，圆盘中心的幽蓝光芒猛地收缩，像有一只眼睛在石下睁开。周围立石依次响起细微的裂声。', 6, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我立刻后退半步，举起剑挡在 Alice 身前，观察哪块立石先裂开。', 7, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '最先裂开的是北侧立石。裂缝里没有火光，只有一缕潮湿的黑烟，烟中传出不属于森林的海潮声。Alice 抬头看你：“Bob，这不是学院记录里的封印反应。”', 7, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我让 Alice 记录海潮声，然后准备撬开北侧立石外层的碎片。', 8, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '碎片被剑尖撬下时，一枚潮湿的黑色羽毛从裂缝里滑落。羽轴上写着一行极细的银字：North Gate opens when the tree burns.', 8, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_academy01', 'user', '我把北境带回来的铜扣放在旧档案馆桌面上，询问管理员有没有炎心之木研究会的禁档。', 1, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '管理员莫兰抬起眼镜，先看铜扣，再看你袖口残留的蓝霜：“如果你问的是二十年前那批档案，它们已经被封入东塔地下库。”', 1, 2, '{"kind":"demo","speaker":"Morlan"}'
    UNION ALL SELECT 's_academy01', 'user', '我追问是谁有权限进入东塔地下库。', 2, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '“院长、三名档案监护人，以及持有旧式火漆钥匙的人。”莫兰把铜扣推回你面前，“而这枚扣子属于已经注销的监护人制服。”', 2, 2, '{"kind":"demo","speaker":"Morlan"}'
    UNION ALL SELECT 's_academy01', 'user', '我检查铜扣背面是否有火漆残留或编号。', 3, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '铜扣背面被划过三道细痕，像是有人故意抹掉编号。但在扣针根部，你找到一点暗红火漆，火漆里混着微量银粉。', 3, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_academy01', 'user', '我请求莫兰查最近一次调阅东塔地下库的登记。', 4, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '莫兰犹豫片刻，还是抽出一册灰皮登记簿。最近一次调阅写在昨夜 23:10，签名处不是姓名，而是一枚小小的树枝烙印。', 4, 2, '{"kind":"demo","speaker":"Morlan"}'
    UNION ALL SELECT 's_academy01', 'user', '我问这枚树枝烙印是否和炎心之木研究会有关。', 5, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '“有关，但不完整。”莫兰翻到二十年前的禁令页，“研究会原本的徽记有树枝和火焰。只有树枝，意味着他们在寻找还没点燃的载体。”', 5, 2, '{"kind":"demo","speaker":"Morlan"}'
    UNION ALL SELECT 's_academy01', 'user', '我准备去东塔地下库，同时让莫兰留意是否有人跟踪我。', 6, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '莫兰递给你一枚临时通行铜片：“地下库会记录每一次开门的温度。若门把手是热的，别进去。”窗外，学院钟声在下午两点敲响，却多出了一记低沉回音。', 6, 2, '{"kind":"demo","speaker":"Narrator"}'
) AS demo_messages
WHERE NOT EXISTS (
    SELECT 1
    FROM rpg_session_messages existing
    WHERE existing.session_id = demo_messages.session_id
      AND existing.turn_id = demo_messages.turn_id
      AND existing.seq_in_turn = demo_messages.seq_in_turn
);

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
FROM rpg_session_messages demo_messages
WHERE demo_messages.session_id IN ('s_forest001', 's_academy01')
  AND demo_messages.metadata_json LIKE '%"kind":"demo"%'
  AND NOT EXISTS (
      SELECT 1
      FROM rpg_session_backup_messages existing
      WHERE existing.session_id = demo_messages.session_id
        AND existing.turn_id = demo_messages.turn_id
        AND existing.seq_in_turn = demo_messages.seq_in_turn
  );

INSERT OR IGNORE INTO rpg_story_characters (
    workspace_id,
    story_id,
    name,
    description,
    sort_order,
    metadata_json
)
SELECT
    stories.workspace_id,
    stories.id,
    characters.name,
    characters.description,
    characters.sort_order,
    '{"kind":"demo"}'
FROM rpg_stories AS stories
CROSS JOIN (
    SELECT
        'Bob' AS name,
        'A knight trained in two-handed swords who serves the northern watch.' AS description,
        10 AS sort_order
    UNION ALL
    SELECT
        'Alice',
        'A young wizard from the Arcanum Academy with formal training in elemental magic.',
        20
) AS characters
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_story_character_details (
    story_character_id,
    name,
    content,
    tags_json,
    sort_order
)
SELECT
    characters.id,
    CASE characters.name WHEN 'Bob' THEN '战斗风格' ELSE '外貌' END,
    CASE characters.name
        WHEN 'Bob' THEN '擅长双手重剑，战斗时喜欢正面冲锋。'
        ELSE '银白色长发，紫罗兰色瞳孔，战斗时穿轻便法师袍。'
    END,
    CASE characters.name
        WHEN 'Bob' THEN '["kind:behavior","scope:npc_portrayal"]'
        ELSE '["kind:appearance"]'
    END,
    10
FROM rpg_story_characters AS characters
JOIN rpg_stories AS stories ON stories.id = characters.story_id
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND characters.name IN ('Bob', 'Alice');

UPDATE rpg_session_profiles
SET
    player_character_id = (
        SELECT characters.id
        FROM rpg_story_characters AS characters
        JOIN rpg_stories AS stories ON stories.id = characters.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '北境森林 Demo'
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
          AND stories.title = '北境森林 Demo'
          AND characters.name = 'Bob'
    )
WHERE session_id = 's_forest001';

UPDATE rpg_session_profiles
SET
    player_character_id = (
        SELECT characters.id
        FROM rpg_story_characters AS characters
        JOIN rpg_stories AS stories ON stories.id = characters.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '奥术学院 Demo'
          AND characters.name = 'Alice'
    ),
    player_character_snapshot_json = (
        SELECT
            '{"characterId":' || characters.id
            || ',"storyId":' || stories.id
            || ',"name":"Alice","avatarUrl":"","roleLabel":"","updatedAt":"' || characters.updated_at || '"}'
        FROM rpg_story_characters AS characters
        JOIN rpg_stories AS stories ON stories.id = characters.story_id
        WHERE stories.workspace_id = 'demo_workspace'
          AND stories.title = '奥术学院 Demo'
          AND characters.name = 'Alice'
    )
WHERE session_id = 's_academy01';

INSERT OR IGNORE INTO rpg_story_lorebook_entries (
    workspace_id,
    story_id,
    name,
    content,
    description,
    tags_json,
    sort_order,
    metadata_json
)
SELECT
    stories.workspace_id,
    stories.id,
    entries.name,
    entries.content,
    entries.description,
    entries.tags_json,
    entries.sort_order,
    '{"kind":"demo"}'
FROM rpg_stories AS stories
CROSS JOIN (
    SELECT
        '炎心之木' AS name,
        '北境森林传说中的世界之树，树干中流淌着永不熄灭的火焰。' AS content,
        '与火焰符文和最初的燃烧有关的核心传说。' AS description,
        '["history","magic"]' AS tags_json,
        10 AS sort_order
    UNION ALL
    SELECT
        '圆形封印祭坛',
        '北境森林石林深处的青石板空地，中央金属圆盘微微渗出幽蓝光芒。',
        '用于演示场景与世界设定词条。',
        '["scene","seal"]',
        20
) AS entries
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    name,
    status_kind,
    description,
    document_json,
    sort_order,
    metadata_json
)
SELECT
    stories.workspace_id,
    stories.id,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '北境森林当前场景'
        ELSE '奥术学院当前场景'
    END,
    'scene',
    CASE stories.title
        WHEN '北境森林 Demo' THEN '北境森林演示故事的当前场景。'
        ELSE '奥术学院演示故事的当前场景。'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"属性","valueColumn":"值","rows":[{"key":"时间","value":"第 1 年 1 月 1 日 8 时 30 分","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"位置","value":"北境森林·石林·圆形封印祭坛","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"在场人物","value":"Bob, Alice","runtimeKeyLocked":true,"updateRule":"","metadata":{}}],"metadata":{"ui":{}}}'
        ELSE '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"属性","valueColumn":"值","rows":[{"key":"时间","value":"第 1 年 1 月 3 日 14 时","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"位置","value":"奥术学院·旧档案馆","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"在场人物","value":"Alice","runtimeKeyLocked":true,"updateRule":"","metadata":{}}],"metadata":{"ui":{}}}'
    END,
    0,
    '{"kind":"demo"}'
FROM rpg_stories AS stories
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    name,
    status_kind,
    description,
    document_json,
    sort_order,
    metadata_json
)
SELECT
    stories.workspace_id,
    stories.id,
    '世界线索',
    'normal',
    '演示普通状态表如何进入上下文。',
    '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"状态","rows":[{"key":"幽蓝封印","value":"异常波动","runtimeKeyLocked":false,"updateRule":"","metadata":{"备注":"圆形封印祭坛附近出现微弱蓝光。"}},{"key":"炎心之木","value":"待调查","runtimeKeyLocked":false,"updateRule":"获得与炎心之木相关的新线索时更新","metadata":{"备注":"相关记载散落在北境与学院档案中。"}}],"metadata":{"ui":{}}}',
    10,
    '{"kind":"demo"}'
FROM rpg_stories AS stories
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_session_status_tables (
    session_id,
    workspace_id,
    story_id,
    source_story_status_table_id,
    origin,
    name,
    status_kind,
    description,
    document_json,
    sort_order,
    metadata_json
)
SELECT
    sessions.id,
    sessions.workspace_id,
    sessions.story_id,
    tables.id,
    'story_copy',
    tables.name,
    tables.status_kind,
    tables.description,
    tables.document_json,
    tables.sort_order,
    '{"kind":"demo","storyStatusSource":{"storyStatusTableId":' || tables.id
        || ',"characterId":null,"characterName":null}}'
FROM rpg_sessions AS sessions
JOIN rpg_story_status_tables AS tables ON tables.story_id = sessions.story_id
WHERE sessions.id IN ('s_forest001', 's_academy01');

INSERT OR IGNORE INTO rpg_narrative_styles (
    workspace_id,
    name,
    prompt,
    sort_order
)
VALUES
    ('demo_workspace', '细腻描写', '请用细腻描写推进这一幕。', 10),
    ('demo_workspace', '快速推进', '请快速推进到下一个关键选择。', 20),
    ('demo_workspace', '多给选项', '请在回应末尾给出多个可选择的行动方向。', 30);

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
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

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
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo')
  AND modules.module_name IN ('message_mode', 'dice', 'narrative_outcome');
