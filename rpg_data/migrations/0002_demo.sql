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
        '{"scene":"北境森林·石林·祭坛下层回廊","time":"1 年 1 月 1 日 9 时 20 分"}'
    ),
    (
        's_academy01',
        'demo_workspace',
        (
            SELECT id FROM rpg_stories
            WHERE workspace_id = 'demo_workspace' AND title = '奥术学院 Demo'
        ),
        '{"scene":"奥术学院·东塔侧门前","time":"1 年 1 月 3 日 15 时 10 分"}'
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
    UNION ALL SELECT 's_forest001', 'user', '我用内衬包住黑羽，让 Alice 用最弱的冷蓝火焰照亮银字，看看它们是否会变化。', 9, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>冷蓝火焰没有点燃羽毛，银字却像细小的鱼群一样游离羽轴，重新排列成四个方向标记。最后一枚符号指向祭坛中央，青石缝隙随之浮出一条此前看不见的环形接缝。</rp-narration><rp-character name="Alice">这不是一句警告，是一张被折叠进文字里的路线图。入口就在圆盘下面。</rp-character>', 9, 2, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_forest001', 'user', '我用剑柄敲击环形接缝，确认下面没有空洞陷阱，再和 Alice 一起转动圆盘。', 10, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>圆盘转过半圈后缓慢下沉，露出铺满灰白树根的石阶。下方传来一长两短的旧巡林哨音，一只覆着霜的铜铃在无人触碰时轻轻摇晃。Alice 用法术照亮前路，你们在石阶尽头看见一扇被烧黑的金属门。</rp-narration>', 10, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_forest001', 'user', '我把剑横在门缝前，检查烧痕的新旧，并让 Alice 解读门框上的刻痕。', 11, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>门上的焦痕至少存在了二十年，最近却又被高温重新唤醒。Alice 从树根遮住的门框上拓出一句古北境语：守门人只回答尚未被点燃的人。与此同时，来路上的湿泥脚印一枚接一枚重新出现，像有什么东西正沿着你们的足迹走下来。</rp-narration>', 11, 2, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_forest001', 'user', '我不回头，朝黑门报上名字，说明我们带着研究会铜扣和黑羽来找北门。', 12, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>黑门中央裂开一条炭红细线，灰烬从门缝倒流，在台阶上聚成披斗篷的人形。它没有五官，胸口却嵌着与你手中相同的树枝铜扣。</rp-narration><rp-character name="灰烬守门人">把铜扣留下。我会告诉你们北门在哪里，以及谁在昨夜先一步打开了学院的东塔。</rp-character>', 12, 2, '{"kind":"demo","speaker":"灰烬守门人"}'
    UNION ALL SELECT 's_forest001', 'user', '我暂时不交铜扣，要求它先证明东塔确实被打开过，也说明它和研究会是什么关系。', 13, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>守门人抬起覆灰的手，一片霜玻璃从树根间生长出来。玻璃里映出学院东塔昨夜的影像：一个发热的人影用树枝烙印开启侧门，门内随即闪过与祭坛相同的潮湿黑烟。</rp-narration><rp-character name="灰烬守门人">我曾替研究会看守被他们点燃的路。如今我只看守还没有燃烧的那一条。</rp-character>', 13, 2, '{"kind":"demo","speaker":"灰烬守门人"}'
    UNION ALL SELECT 's_forest001', 'user', '我提出只把铜扣暂时封在它面前，换取北门路线；Alice 负责记录契约，任何一方越界就立即终止。', 14, 1, '{"kind":"demo","speaker":"Bob"}'
    UNION ALL SELECT 's_forest001', 'assistant', '<rp-narration>你把铜扣放进空灯笼，Alice 以冷蓝火焰封住灯门。守门人接受了这份有限契约，在黑门上划出一条通往北方山脊的发光路线，并约定正午前仍可在此交换情报。祭坛下层的潮声暂时平息，但霜玻璃中的东塔影像没有消失。</rp-narration>', 14, 2, '{"kind":"demo","speaker":"Narrator"}'
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
    UNION ALL SELECT 's_academy01', 'user', '我走到窗边确认多出的回音来自哪座塔，同时观察阅览室里有没有人在留意我们。', 7, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>回音来自本不该在白天鸣响的东塔警钟。你在玻璃反光里看见一名灰袍监察员停在阅览室门外，他没有进来，只用指节在门框上敲出一长两短的节奏，随后转身走向侧廊。</rp-narration><rp-character name="莫兰">那是旧巡林队的联络哨，不是学院暗号。</rp-character>', 7, 2, '{"kind":"demo","speaker":"莫兰"}'
    UNION ALL SELECT 's_academy01', 'user', '我请莫兰带我走档案员使用的侧廊，避开监察员，先去检查东塔侧门的温度。', 8, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>莫兰锁上登记簿，领你穿过堆满待修羊皮卷的准备室。东塔侧门的黄铜把手隔着三步就能感到热意，门边温度刻盘却覆盖着一层薄霜，像有人刚用冰系法术掩盖过读数。</rp-narration>', 8, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_academy01', 'user', '我不碰门把手，用霜线术读取刻盘残留的温度变化，并让莫兰抄下时间。', 9, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>刻盘恢复后显出两条异常曲线：昨夜 23:10 有一次人为制造的极低温，今天 13:47 又出现接近高烧的热度。两次记录都被同一枚树枝烙印覆盖。莫兰把数字抄在封蜡纸上，手指微微发抖。</rp-narration>', 9, 2, '{"kind":"demo","speaker":"莫兰"}'
    UNION ALL SELECT 's_academy01', 'user', '我让莫兰调出昨夜值班与访客名单，再用铜扣背面的划痕拓印被擦除的登记栏。', 10, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>银粉落入纸张压痕后，一列被刮掉的访客编号逐渐显现。编号属于早已注销的档案监护人塞伦；同一页边缘还有一句倒写旁注：北门先于树火开启。名单显示塞伦二十年前已经死于一次封印事故。</rp-narration>', 10, 2, '{"kind":"demo","speaker":"Narrator"}'
    UNION ALL SELECT 's_academy01', 'user', '我追问塞伦的遗物由谁保管，并检查旁注是否是后来补写的。', 11, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>旁注使用的墨水只有不到一天，笔迹却与塞伦留下的样本完全一致。莫兰从贴身钥匙袋里取出一枚旧式火漆钥匙，承认塞伦的遗物一直由档案馆秘密保管。</rp-narration><rp-character name="莫兰">我昨夜没有打开东塔，但这把钥匙在清晨是温热的。有人隔着保管匣借用了它。</rp-character>', 11, 2, '{"kind":"demo","speaker":"莫兰"}'
    UNION ALL SELECT 's_academy01', 'user', '我请莫兰封存登记簿和温度记录，把钥匙交给我保管；我们先守在侧门外，等下一次异常温度。', 12, 1, '{"kind":"demo","speaker":"Alice"}'
    UNION ALL SELECT 's_academy01', 'assistant', '<rp-narration>莫兰以档案馆最高级别的黑蜡封存两份证据，把火漆钥匙放进你的隔热匣。下午三点十分，东塔门后的锁芯自行转过半圈，门缝中渗出带海盐气味的冷雾；你们都没有碰门。</rp-narration><rp-character name="莫兰">我留下协助你。下一次读数出现时，我们就知道门里的人究竟在等谁。</rp-character>', 12, 2, '{"kind":"demo","speaker":"莫兰"}'
) AS demo_messages
WHERE NOT EXISTS (
    SELECT 1
    FROM rpg_session_messages existing
    WHERE existing.session_id = demo_messages.session_id
      AND existing.turn_id = demo_messages.turn_id
      AND existing.seq_in_turn = demo_messages.seq_in_turn
);

UPDATE rpg_session_messages
SET
    summary_processed = 1,
    summary_batch_id = CASE
        WHEN session_id = 's_forest001' AND turn_id BETWEEN 1 AND 6 THEN 1
        WHEN session_id = 's_forest001' AND turn_id BETWEEN 7 AND 12 THEN 2
        WHEN session_id = 's_academy01' AND turn_id BETWEEN 1 AND 6 THEN 1
        WHEN session_id = 's_academy01' AND turn_id BETWEEN 7 AND 10 THEN 2
    END,
    summary_processed_at = CURRENT_TIMESTAMP
WHERE
    (session_id = 's_forest001' AND turn_id BETWEEN 1 AND 12)
    OR (session_id = 's_academy01' AND turn_id BETWEEN 1 AND 10);

UPDATE rpg_session_messages
SET
    story_memory_processed = 1,
    story_memory_processed_at = CURRENT_TIMESTAMP
WHERE
    (session_id = 's_forest001' AND turn_id BETWEEN 1 AND 13)
    OR (session_id = 's_academy01' AND turn_id BETWEEN 1 AND 12);

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
    CASE stories.title
        WHEN '北境森林 Demo' THEN '伊芙'
        ELSE '莫兰'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '负责石林外围巡逻的北境巡林人，熟悉旧巡林队哨音与封印事故记录。'
        ELSE '奥术学院旧档案馆管理员，负责禁档、监护人登记与东塔地下库历史资料。'
    END,
    30,
    '{"kind":"demo","role":"npc"}'
FROM rpg_stories AS stories
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

INSERT OR IGNORE INTO rpg_story_character_details (
    story_character_id,
    name,
    content,
    tags_json,
    sort_order
)
SELECT
    characters.id,
    CASE characters.name
        WHEN '伊芙' THEN '巡林职责'
        ELSE '档案权限'
    END,
    CASE characters.name
        WHEN '伊芙' THEN '负责石林外围与北方山脊的日常巡逻，掌握一长两短的旧巡林联络哨。'
        ELSE '可以调阅旧档案馆登记簿、封存证据，并持有东塔地下库旧式火漆钥匙。'
    END,
    CASE characters.name
        WHEN '伊芙' THEN '["kind:background"]'
        ELSE '["kind:ability"]'
    END,
    10
FROM rpg_story_characters AS characters
JOIN rpg_stories AS stories ON stories.id = characters.story_id
WHERE stories.workspace_id = 'demo_workspace'
  AND (
      (stories.title = '北境森林 Demo' AND characters.name = '伊芙')
      OR (stories.title = '奥术学院 Demo' AND characters.name = '莫兰')
  );

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
        WHEN '北境森林 Demo' THEN '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"属性","valueColumn":"值","rows":[{"key":"时间","value":"1 年 1 月 1 日 9 时 20 分","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"位置","value":"北境森林·石林·祭坛下层回廊","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"在场人物","value":"Bob, Alice, 灰烬守门人","runtimeKeyLocked":true,"updateRule":"","metadata":{}}],"metadata":{"ui":{}}}'
        ELSE '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"属性","valueColumn":"值","rows":[{"key":"时间","value":"1 年 1 月 3 日 15 时 10 分","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"位置","value":"奥术学院·东塔侧门前","runtimeKeyLocked":true,"updateRule":"","metadata":{}},{"key":"在场人物","value":"Alice, 莫兰","runtimeKeyLocked":true,"updateRule":"","metadata":{}}],"metadata":{"ui":{}}}'
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
    CASE stories.title
        WHEN '北境森林 Demo' THEN '追踪北门封印、炎心之木与研究会活动的当前线索。'
        ELSE '追踪东塔地下库、火漆钥匙与研究会调阅记录的当前线索。'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"状态","rows":[{"key":"幽蓝封印","value":"北侧立石已裂开，潮声暂时平息","runtimeKeyLocked":false,"updateRule":"封印强度、裂缝或异常声响发生明确变化时更新","metadata":{}},{"key":"炎心之木研究会","value":"旧徽记与祭坛活动已确认有关","runtimeKeyLocked":false,"updateRule":"确认研究会成员、目的或遗留设施时更新","metadata":{}},{"key":"黑色羽毛","value":"银字已重排为祭坛下层路线","runtimeKeyLocked":false,"updateRule":"羽毛文字、用途或归属得到新证据时更新","metadata":{}}],"metadata":{"ui":{}}}'
        ELSE '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"状态","rows":[{"key":"东塔地下库","value":"侧门锁芯自行转动，门缝出现海盐冷雾","runtimeKeyLocked":false,"updateRule":"入口状态、温度记录或开启者身份变化时更新","metadata":{}},{"key":"旧式火漆钥匙","value":"已由 Alice 保存在隔热匣中","runtimeKeyLocked":false,"updateRule":"钥匙持有人、温度或使用记录变化时更新","metadata":{}},{"key":"树枝烙印","value":"昨夜调阅与两次异常温度均出现","runtimeKeyLocked":false,"updateRule":"确认烙印持有者或新出现位置时更新","metadata":{}}],"metadata":{"ui":{}}}'
    END,
    10,
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
    CASE stories.title
        WHEN '北境森林 Demo' THEN '调查进度'
        ELSE '档案调查进度'
    END,
    'normal',
    CASE stories.title
        WHEN '北境森林 Demo' THEN '保存北境石林调查中已经确认的阶段、证物与下一目标。'
        ELSE '保存学院禁档调查中已经确认的证据链、权限与下一目标。'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"当前记录","rows":[{"key":"当前阶段","value":"与灰烬守门人达成有限情报契约","runtimeKeyLocked":true,"updateRule":"主线调查进入新的明确阶段时更新","metadata":{}},{"key":"关键证物","value":"树枝铜扣、黑色羽毛、Alice 的银字拓本","runtimeKeyLocked":true,"updateRule":"获得或失去足以推进调查的证物时更新","metadata":{}},{"key":"下一目标","value":"正午前确认北门路线并核对学院东塔异动","runtimeKeyLocked":true,"updateRule":"角色明确改变调查目标时更新","metadata":{}}],"metadata":{"ui":{}}}'
        ELSE '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"当前记录","rows":[{"key":"当前阶段","value":"在东塔侧门外监测下一次异常温度","runtimeKeyLocked":true,"updateRule":"档案调查进入新的明确阶段时更新","metadata":{}},{"key":"已封存证据","value":"调阅登记、温度曲线、塞伦姓名拓印","runtimeKeyLocked":true,"updateRule":"证据被新增、移交、破坏或证明无效时更新","metadata":{}},{"key":"下一目标","value":"确认门内等待对象并追查塞伦身份被冒用的方式","runtimeKeyLocked":true,"updateRule":"角色明确改变调查目标时更新","metadata":{}}],"metadata":{"ui":{}}}'
    END,
    20,
    '{"kind":"demo"}'
FROM rpg_stories AS stories
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT OR IGNORE INTO rpg_story_status_tables (
    workspace_id,
    story_id,
    story_character_id,
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
    characters.id,
    CASE stories.title
        WHEN '北境森林 Demo' THEN 'Alice 同行状态'
        ELSE '莫兰协助状态'
    END,
    'normal',
    CASE stories.title
        WHEN '北境森林 Demo' THEN 'Alice 在北境调查中的即时协作状态。'
        ELSE '管理员莫兰在东塔调查中的即时协作状态。'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"状态","rows":[{"key":"协作立场","value":"支持有限契约，但要求保留随时终止权","runtimeKeyLocked":true,"updateRule":"Alice 对当前计划的明确立场变化时更新","metadata":{}},{"key":"法术负荷","value":"轻度消耗，可继续使用冷蓝火焰与拓印术","runtimeKeyLocked":true,"updateRule":"Alice 明确施法、受伤或休息后更新","metadata":{}},{"key":"掌握资料","value":"银字路线拓本、守门人古北境语刻痕","runtimeKeyLocked":true,"updateRule":"Alice 获得或交出关键资料时更新","metadata":{}}],"metadata":{"ui":{}}}'
        ELSE '{"schemaVersion":2,"kind":"status_table","mode":"key_value","keyColumn":"项目","valueColumn":"状态","rows":[{"key":"协助立场","value":"已决定留下协助 Alice","runtimeKeyLocked":true,"updateRule":"莫兰明确改变合作立场时更新","metadata":{}},{"key":"可用权限","value":"旧档案馆封存权、监护人登记调阅权","runtimeKeyLocked":true,"updateRule":"莫兰的权限被使用、暂停或扩大时更新","metadata":{}},{"key":"当前风险","value":"可能因私自移交火漆钥匙受到学院问责","runtimeKeyLocked":true,"updateRule":"莫兰面临的明确风险发生变化时更新","metadata":{}}],"metadata":{"ui":{}}}'
    END,
    30,
    '{"kind":"demo","characterBound":true}'
FROM rpg_stories AS stories
JOIN rpg_story_characters AS characters ON characters.story_id = stories.id
WHERE stories.workspace_id = 'demo_workspace'
  AND (
      (stories.title = '北境森林 Demo' AND characters.name = 'Alice')
      OR (stories.title = '奥术学院 Demo' AND characters.name = '莫兰')
  );

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
    json_object(
        'kind',
        'demo',
        'storyStatusSource',
        json_object(
            'storyStatusTableId',
            tables.id,
            'characterId',
            tables.story_character_id,
            'characterName',
            characters.name
        )
    )
FROM rpg_sessions AS sessions
JOIN rpg_story_status_tables AS tables ON tables.story_id = sessions.story_id
LEFT JOIN rpg_story_characters AS characters
    ON characters.id = tables.story_character_id
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
  AND modules.module_name IN (
      'message_mode',
      'dice',
      'narrative_outcome',
      'plot_scheduler'
  );

-- Plot Scheduler demo definitions. Mainline event libraries stay disabled as
-- pools so their events are only dispatched through ordered outline nodes.
INSERT INTO rpg_story_plot_event_pools (
    story_id,
    name,
    description,
    selection_mode,
    priority,
    enabled
)
SELECT
    stories.id,
    pools.name,
    pools.description,
    pools.selection_mode,
    pools.priority,
    pools.enabled
FROM rpg_stories AS stories
JOIN (
    SELECT
        '北境森林 Demo' AS story_title,
        '北门主线节点库' AS name,
        '仅供北门封印主线大纲引用的事件定义。' AS description,
        'sequential' AS selection_mode,
        100 AS priority,
        0 AS enabled
    UNION ALL SELECT
        '北境森林 Demo',
        '石林动态事件池',
        '可在石林调查中按当前场景择机出现的环境事件。',
        'random',
        50,
        1
    UNION ALL SELECT
        '奥术学院 Demo',
        '东塔主线节点库',
        '仅供东塔禁档主线大纲引用的事件定义。',
        'sequential',
        100,
        0
    UNION ALL SELECT
        '奥术学院 Demo',
        '学院调查事件池',
        '可在学院调查期间择机出现的监察与通信事件。',
        'sequential',
        50,
        1
) AS pools ON pools.story_title = stories.title
WHERE stories.workspace_id = 'demo_workspace';

INSERT INTO rpg_story_plot_events (
    story_id,
    pool_id,
    title,
    description,
    directive,
    suitability_hint,
    dispatch_mode,
    scheduled_time_json,
    deadline_time_json,
    position,
    enabled,
    allow_repeat,
    repeat_cooldown_minutes
)
SELECT
    stories.id,
    pools.id,
    events.title,
    events.description,
    events.directive,
    events.suitability_hint,
    events.dispatch_mode,
    events.scheduled_time_json,
    events.deadline_time_json,
    events.position,
    1,
    events.allow_repeat,
    events.repeat_cooldown_minutes
FROM rpg_stories AS stories
JOIN rpg_story_plot_event_pools AS pools ON pools.story_id = stories.id
JOIN (
    SELECT
        '北门主线节点库' AS pool_name,
        '北侧立石迸裂' AS title,
        '北侧立石出现第一处明确裂口，封印从静态异常转为活动状态。' AS description,
        '描写北侧立石裂开并释放潮湿黑烟与海潮声，但不要替玩家决定如何应对。' AS directive,
        '玩家正在观察祭坛或封印异动时适合触发。' AS suitability_hint,
        'soft' AS dispatch_mode,
        NULL AS scheduled_time_json,
        NULL AS deadline_time_json,
        0 AS position,
        0 AS allow_repeat,
        0 AS repeat_cooldown_minutes
    UNION ALL SELECT
        '北门主线节点库',
        '黑羽显露银字',
        '封印裂缝掉出带有银字的潮湿黑色羽毛。',
        '让黑色羽毛从裂缝中出现，并保留银字 North Gate opens when the tree burns 作为可调查证据。',
        '立石已经裂开且玩家有机会检查裂缝时适合触发。',
        'soft',
        NULL,
        NULL,
        1,
        0,
        0
    UNION ALL SELECT
        '北门主线节点库',
        '灰烬守门人现身',
        '被烧黑的门扉释放灰烬并聚成守门人形体。',
        '让灰烬守门人出现并提出以研究会铜扣交换北门路线；只提出条件，不替玩家接受。',
        '玩家已经进入祭坛下层并主动与黑门沟通时适合触发。',
        'soft',
        NULL,
        NULL,
        2,
        0,
        0
    UNION ALL SELECT
        '北门主线节点库',
        '炎心树根苏醒',
        '祭坛下层的灰白树根开始传递来自炎心之木的热量。',
        '让树根逐段亮起暗红火线，显示北门路线正在缩短可用时间，但不要直接开启北门。',
        '玩家已经取得北门路线且场景时间达到上午十时后触发。',
        'forced',
        NULL,
        NULL,
        3,
        0,
        0
    UNION ALL SELECT
        '石林动态事件池',
        '旧巡林哨音',
        '祭坛下层传来一长两短的旧巡林联络哨。',
        '从无人的方向传来一长两短的巡林哨音，并留下可以追查但不强制追查的声源。',
        '角色正在石林或祭坛通道中移动、短暂停顿或侦查时适合触发。',
        'soft',
        '{"day":1,"hour":9,"minute":0,"month":1,"year":1}',
        '{"day":1,"hour":9,"minute":30,"month":1,"year":1}',
        0,
        0,
        0
    UNION ALL SELECT
        '石林动态事件池',
        '霜角白鹿示警',
        '一只霜角白鹿短暂出现，以蹄印提示附近有第二条通路。',
        '让霜角白鹿在远处短暂现身并留下指向岔路的蹄印；它不会停下回答问题。',
        '玩家尚未离开北境石林且当前节奏允许出现短暂环境插曲时适合触发。',
        'soft',
        '{"day":1,"hour":9,"minute":25,"month":1,"year":1}',
        '{"day":1,"hour":10,"minute":0,"month":1,"year":1}',
        1,
        1,
        60
    UNION ALL SELECT
        '东塔主线节点库',
        '多出的一记钟声',
        '学院钟声在正常报时后出现一记来自东塔的低沉回音。',
        '让东塔警钟多响一记低沉回音，并给出可追查的方向线索。',
        '角色仍在旧档案馆调查研究会记录时适合触发。',
        'soft',
        NULL,
        NULL,
        0,
        0,
        0
    UNION ALL SELECT
        '东塔主线节点库',
        '东塔侧门温度异常',
        '东塔侧门同时留下人为低温与近似高烧的热度记录。',
        '展示东塔侧门的两条异常温度曲线，并让树枝烙印成为两次记录的共同线索。',
        'Alice 已抵达东塔侧门并主动检查温度刻盘时适合触发。',
        'soft',
        NULL,
        NULL,
        1,
        0,
        0
    UNION ALL SELECT
        '东塔主线节点库',
        '塞伦姓名重新显现',
        '被擦除的访客编号指向二十年前已经死亡的档案监护人塞伦。',
        '让铜扣拓印恢复塞伦的姓名和北门先于树火开启的旁注，同时保留身份被冒用的疑问。',
        '角色正在核对昨夜访客名单或被擦除的登记栏时适合触发。',
        'soft',
        NULL,
        NULL,
        2,
        0,
        0
    UNION ALL SELECT
        '东塔主线节点库',
        '东塔地下库开启',
        '侧门将在无人触碰时完全开启，冷雾通往地下库。',
        '让东塔侧门自行完全开启并显露向下的冷雾阶梯，但不要替玩家进入。',
        '场景时间达到下午三时二十分且角色仍守在东塔侧门时触发。',
        'forced',
        NULL,
        NULL,
        3,
        0,
        0
    UNION ALL SELECT
        '学院调查事件池',
        '灰袍监察员经过',
        '一名灰袍监察员在门外观察调查者并敲出旧巡林哨。',
        '让灰袍监察员短暂停在视线边缘，敲出一长两短节奏后离开，不立即揭示身份。',
        '角色在学院公共区域讨论禁档或准备前往东塔时适合触发。',
        'soft',
        '{"day":3,"hour":14,"minute":20,"month":1,"year":1}',
        '{"day":3,"hour":15,"minute":0,"month":1,"year":1}',
        0,
        0,
        0
    UNION ALL SELECT
        '学院调查事件池',
        '无署名纸鹤送达',
        '一只无署名纸鹤带来关于火漆钥匙的模糊警告。',
        '让一只纸鹤从通风窗飞入，留下不要让钥匙接触树火的短句；来源保持未知。',
        '角色取得火漆钥匙之后、当前对话允许插入短线索时适合触发。',
        'soft',
        '{"day":3,"hour":15,"minute":15,"month":1,"year":1}',
        '{"day":3,"hour":16,"minute":0,"month":1,"year":1}',
        1,
        1,
        90
) AS events ON events.pool_name = pools.name
WHERE stories.workspace_id = 'demo_workspace';

INSERT INTO rpg_story_plot_outlines (
    story_id,
    name,
    description,
    priority,
    enabled
)
SELECT
    stories.id,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '北门封印主线'
        ELSE '东塔禁档主线'
    END,
    CASE stories.title
        WHEN '北境森林 Demo' THEN '从祭坛异动、黑羽线索推进到北门路线与炎心树根苏醒。'
        ELSE '从禁档回音、温度记录推进到塞伦身份与东塔地下库开启。'
    END,
    100,
    1
FROM rpg_stories AS stories
WHERE stories.workspace_id = 'demo_workspace'
  AND stories.title IN ('北境森林 Demo', '奥术学院 Demo');

INSERT INTO rpg_story_plot_outline_nodes (
    story_id,
    outline_id,
    event_id,
    scheduled_time_json,
    dispatch_mode,
    position,
    enabled
)
SELECT
    stories.id,
    outlines.id,
    events.id,
    nodes.scheduled_time_json,
    nodes.dispatch_mode,
    nodes.position,
    1
FROM rpg_stories AS stories
JOIN rpg_story_plot_outlines AS outlines ON outlines.story_id = stories.id
JOIN (
    SELECT
        '北境森林 Demo' AS story_title,
        '北侧立石迸裂' AS event_title,
        '{"day":1,"hour":8,"minute":45,"month":1,"year":1}' AS scheduled_time_json,
        'forced' AS dispatch_mode,
        0 AS position
    UNION ALL SELECT
        '北境森林 Demo',
        '黑羽显露银字',
        '{"day":1,"hour":8,"minute":55,"month":1,"year":1}',
        'forced',
        1
    UNION ALL SELECT
        '北境森林 Demo',
        '灰烬守门人现身',
        '{"day":1,"hour":9,"minute":10,"month":1,"year":1}',
        'soft',
        2
    UNION ALL SELECT
        '北境森林 Demo',
        '炎心树根苏醒',
        '{"day":1,"hour":10,"minute":0,"month":1,"year":1}',
        'forced',
        3
    UNION ALL SELECT
        '奥术学院 Demo',
        '多出的一记钟声',
        '{"day":3,"hour":14,"minute":15,"month":1,"year":1}',
        'forced',
        0
    UNION ALL SELECT
        '奥术学院 Demo',
        '东塔侧门温度异常',
        '{"day":3,"hour":14,"minute":40,"month":1,"year":1}',
        'forced',
        1
    UNION ALL SELECT
        '奥术学院 Demo',
        '塞伦姓名重新显现',
        '{"day":3,"hour":14,"minute":55,"month":1,"year":1}',
        'soft',
        2
    UNION ALL SELECT
        '奥术学院 Demo',
        '东塔地下库开启',
        '{"day":3,"hour":15,"minute":20,"month":1,"year":1}',
        'forced',
        3
) AS nodes ON nodes.story_title = stories.title
JOIN rpg_story_plot_events AS events
    ON events.story_id = stories.id
    AND events.title = nodes.event_title
WHERE stories.workspace_id = 'demo_workspace';

WITH decision_seeds AS (
    SELECT
        's_forest001' AS session_id,
        7 AS turn_id,
        'outline' AS source_kind,
        '北门封印主线' AS container_name,
        '北侧立石迸裂' AS event_title,
        'triggered' AS decision_status,
        'forced' AS dispatch_mode,
        '{"day":1,"hour":8,"minute":48,"month":1,"year":1}' AS scene_time_json,
        528 AS scene_time_ordinal,
        '节点到时强制注入。' AS reason
    UNION ALL SELECT
        's_forest001',
        8,
        'outline',
        '北门封印主线',
        '黑羽显露银字',
        'triggered',
        'forced',
        '{"day":1,"hour":8,"minute":55,"month":1,"year":1}',
        535,
        '节点到时强制注入。'
    UNION ALL SELECT
        's_forest001',
        10,
        'pool',
        '石林动态事件池',
        '旧巡林哨音',
        'triggered',
        'soft',
        '{"day":1,"hour":9,"minute":5,"month":1,"year":1}',
        545,
        '角色正在探索祭坛下层，适合加入环境线索。'
    UNION ALL SELECT
        's_forest001',
        12,
        'outline',
        '北门封印主线',
        '灰烬守门人现身',
        'triggered',
        'soft',
        '{"day":1,"hour":9,"minute":14,"month":1,"year":1}',
        554,
        '玩家主动向黑门表明来意，满足现身条件。'
    UNION ALL SELECT
        's_academy01',
        6,
        'outline',
        '东塔禁档主线',
        '多出的一记钟声',
        'triggered',
        'forced',
        '{"day":3,"hour":14,"minute":18,"month":1,"year":1}',
        3738,
        '节点到时强制注入。'
    UNION ALL SELECT
        's_academy01',
        7,
        'pool',
        '学院调查事件池',
        '灰袍监察员经过',
        'triggered',
        'soft',
        '{"day":3,"hour":14,"minute":25,"month":1,"year":1}',
        3745,
        '角色正准备离开公共阅览区，适合加入监视线索。'
    UNION ALL SELECT
        's_academy01',
        9,
        'outline',
        '东塔禁档主线',
        '东塔侧门温度异常',
        'triggered',
        'forced',
        '{"day":3,"hour":14,"minute":42,"month":1,"year":1}',
        3762,
        '节点到时强制注入。'
    UNION ALL SELECT
        's_academy01',
        10,
        'outline',
        '东塔禁档主线',
        '塞伦姓名重新显现',
        'triggered',
        'soft',
        '{"day":3,"hour":14,"minute":58,"month":1,"year":1}',
        3778,
        '玩家主动拓印被擦除的登记栏，适合揭示姓名。'
)
INSERT INTO rpg_session_plot_schedule_decisions (
    session_id,
    turn_id,
    source_kind,
    source_id,
    event_id,
    container_id,
    decision_status,
    dispatch_mode,
    scene_time_json,
    scene_time_ordinal,
    event_snapshot_json,
    reason
)
SELECT
    seeds.session_id,
    seeds.turn_id,
    seeds.source_kind,
    CASE seeds.source_kind
        WHEN 'outline' THEN nodes.id
        ELSE events.id
    END,
    events.id,
    CASE seeds.source_kind
        WHEN 'outline' THEN outlines.id
        ELSE pools.id
    END,
    seeds.decision_status,
    seeds.dispatch_mode,
    seeds.scene_time_json,
    seeds.scene_time_ordinal,
    json_object(
        'eventTitle',
        events.title,
        'directive',
        events.directive
    ),
    seeds.reason
FROM decision_seeds AS seeds
JOIN rpg_sessions AS sessions ON sessions.id = seeds.session_id
JOIN rpg_story_plot_events AS events
    ON events.story_id = sessions.story_id
    AND events.title = seeds.event_title
LEFT JOIN rpg_story_plot_event_pools AS pools
    ON seeds.source_kind = 'pool'
    AND pools.story_id = sessions.story_id
    AND pools.name = seeds.container_name
LEFT JOIN rpg_story_plot_outlines AS outlines
    ON seeds.source_kind = 'outline'
    AND outlines.story_id = sessions.story_id
    AND outlines.name = seeds.container_name
LEFT JOIN rpg_story_plot_outline_nodes AS nodes
    ON seeds.source_kind = 'outline'
    AND nodes.outline_id = outlines.id
    AND nodes.event_id = events.id;

-- Story Memory rows use the same code-owned dedupe identities and exact
-- message Evidence shape as online extraction.
INSERT OR IGNORE INTO rpg_session_story_memories (
    session_id,
    turn_id,
    text,
    memory_kind,
    epistemic_status,
    salience,
    source_turn_start,
    source_turn_end,
    dedupe_key,
    dream_processed,
    metadata_schema_version,
    metadata_json
)
SELECT
    facts.session_id,
    facts.turn_id,
    facts.text,
    facts.memory_kind,
    facts.epistemic_status,
    facts.salience,
    facts.source_turn_start,
    facts.source_turn_end,
    facts.dedupe_key,
    facts.dream_processed,
    1,
    '{"kind":"demo","source":"seed"}'
FROM (
    SELECT
        's_forest001' AS session_id,
        2 AS turn_id,
        '石林祭坛东侧留有一串高阶学徒常用软底靴的湿泥脚印，脚印停在火焰纹立石前。' AS text,
        'clue' AS memory_kind,
        'confirmed' AS epistemic_status,
        0.72 AS salience,
        2 AS source_turn_start,
        2 AS source_turn_end,
        '0106bbcb98caa2f8d5898a59bb40470cb32613cd32cb2d07ab621ec726a4ae97' AS dedupe_key,
        1 AS dream_processed
    UNION ALL SELECT
        's_forest001',
        5,
        'Alice 辨认出裂缝中的树枝铜扣属于二十年前被学院取缔的炎心之木研究会。',
        'world_fact',
        'confirmed',
        0.86,
        4,
        5,
        'fbbcf827d13d798dd3ea594932ae7c34d5ec83b279569998f2cf718e8abb8214',
        1
    UNION ALL SELECT
        's_forest001',
        8,
        '北侧立石裂开后涌出潮湿黑烟与海潮声，并掉出写有“North Gate opens when the tree burns”的黑色羽毛。',
        'event',
        'confirmed',
        0.94,
        7,
        8,
        'f813bd954f461a9874587e655a6de653160d14f882f8e6e80c88bb1fbd82da9f',
        1
    UNION ALL SELECT
        's_forest001',
        9,
        '黑羽银字在 Alice 的冷蓝火焰下重排成一条通往祭坛下层回廊的路线。',
        'clue',
        'confirmed',
        0.88,
        9,
        9,
        '59df3f32cdf8b9310411d5212475522a4bb7429da7536bb5600249f81181583e',
        0
    UNION ALL SELECT
        's_forest001',
        11,
        '祭坛下层门扉的刻痕表明，灰烬守门人只回应“尚未被点燃的人”。',
        'world_fact',
        'confirmed',
        0.82,
        11,
        11,
        '7932a13618be636879ab45d4b21c538b2a2c0afae31b6f4b63438754e5dbc065',
        0
    UNION ALL SELECT
        's_forest001',
        13,
        '灰烬守门人用霜玻璃展示了学院东塔昨夜被同一组织开启的画面，并提出用铜扣交换北门路线。',
        'event',
        'confirmed',
        0.96,
        12,
        13,
        '4d136b8b50e7e5f12b0a9c01a0eda31dd6d8d4ecfd7a61fc0e2554e9897e2349',
        0
    UNION ALL SELECT
        's_academy01',
        2,
        '东塔地下库只允许院长、三名档案监护人或持旧式火漆钥匙者进入。',
        'world_fact',
        'confirmed',
        0.84,
        2,
        2,
        'af73425e9aad863f3ed6a4519e896b29da9c89b4e5d9275b215df4fd55debc1b',
        1
    UNION ALL SELECT
        's_academy01',
        5,
        '昨夜 23:10 的地下库调阅记录以树枝烙印代替姓名；该标记代表研究会寻找尚未点燃的载体。',
        'clue',
        'confirmed',
        0.91,
        4,
        5,
        '6392c2b605ae178387b48b16600d98c285f8bf7a949419e40a5a963af64e6bcf',
        1
    UNION ALL SELECT
        's_academy01',
        6,
        '莫兰警告：地下库会记录每次开门温度，若门把手发热就不要进入。',
        'clue',
        'reported',
        0.75,
        6,
        6,
        '868ab3aa1a54bcb596e8ea75d7cdb348bb8bc65494a76a869c519fa628e3c4bb',
        0
    UNION ALL SELECT
        's_academy01',
        9,
        '东塔侧门记录到两次异常温度：一次人为制造的低温，另一次接近高烧的热度。',
        'clue',
        'confirmed',
        0.88,
        8,
        9,
        '45a8ac6b7c0906a53bf69b2b504bc7e173c6579c605ac5ef724c68325e8c862a',
        0
    UNION ALL SELECT
        's_academy01',
        10,
        '被擦除的访客姓名通过铜扣拓印显现为“塞伦”，其旁注写着“北门先于树火开启”。',
        'clue',
        'confirmed',
        0.95,
        10,
        10,
        'eecba76b10c60ea71747885efe64bff5c67309bfe4d5622cfa14597eabdd6faf',
        0
    UNION ALL SELECT
        's_academy01',
        12,
        '莫兰答应封存登记簿和温度记录，并把一枚旧式火漆钥匙交给 Alice。',
        'commitment',
        'confirmed',
        0.87,
        11,
        12,
        'b2c0634bae00760d79130d7936771c7526f5a90121f9dca9d96e0b64317f9b2d',
        0
) AS facts;

WITH evidence_seeds AS (
    SELECT
        's_forest001' AS session_id,
        '0106bbcb98caa2f8d5898a59bb40470cb32613cd32cb2d07ab621ec726a4ae97' AS dedupe_key,
        2 AS turn_id,
        2 AS seq_in_turn,
        '63b48339c9e1dd90e33c4e771ef42c36a51c043e3f693a13ccad97535bbc9b7e' AS content_hash
    UNION ALL SELECT
        's_forest001',
        'fbbcf827d13d798dd3ea594932ae7c34d5ec83b279569998f2cf718e8abb8214',
        5,
        2,
        'f8f0a4501e250e2cbcd0aca36fe70f21b1f414bccbb046e30cefe45c0ea2dcb3'
    UNION ALL SELECT
        's_forest001',
        'f813bd954f461a9874587e655a6de653160d14f882f8e6e80c88bb1fbd82da9f',
        8,
        2,
        '55b4e38748c98ceb127fad9c5b6bad0ac9feb5f034b3e53974f190ae7786d54f'
    UNION ALL SELECT
        's_forest001',
        '59df3f32cdf8b9310411d5212475522a4bb7429da7536bb5600249f81181583e',
        9,
        2,
        'dcaee7191dbb80d284f41a1d201094e303f1db7eb9dc4fb685c369de4046734d'
    UNION ALL SELECT
        's_forest001',
        '7932a13618be636879ab45d4b21c538b2a2c0afae31b6f4b63438754e5dbc065',
        11,
        2,
        'afc1716a64a4884dec48ada70dab3900ad2ba2fc2f2677f31a7e1732c57fe63b'
    UNION ALL SELECT
        's_forest001',
        '4d136b8b50e7e5f12b0a9c01a0eda31dd6d8d4ecfd7a61fc0e2554e9897e2349',
        13,
        2,
        '12e584cfe9bee24f20dd2b12d3f01fbc4d3d9846851a6810c1b49b2015958efc'
    UNION ALL SELECT
        's_academy01',
        'af73425e9aad863f3ed6a4519e896b29da9c89b4e5d9275b215df4fd55debc1b',
        2,
        2,
        '1d2a15545fffa134429f907ba660ed0c04258a79fc241cbfc2f883f4ce278808'
    UNION ALL SELECT
        's_academy01',
        '6392c2b605ae178387b48b16600d98c285f8bf7a949419e40a5a963af64e6bcf',
        4,
        2,
        'f4b034704209e841a510c3a73344acefb34ac6f69f9ca24502b89ba419e11752'
    UNION ALL SELECT
        's_academy01',
        '6392c2b605ae178387b48b16600d98c285f8bf7a949419e40a5a963af64e6bcf',
        5,
        2,
        '03a57209f0c0f61f631612fa0af1367cb07c4a6d8d64977b0838cf13a805efdb'
    UNION ALL SELECT
        's_academy01',
        '868ab3aa1a54bcb596e8ea75d7cdb348bb8bc65494a76a869c519fa628e3c4bb',
        6,
        2,
        'ba7fd587ddd3b00f9d597887034a6cd4cfe5c3780c8416849b8a870c5bc2febc'
    UNION ALL SELECT
        's_academy01',
        '45a8ac6b7c0906a53bf69b2b504bc7e173c6579c605ac5ef724c68325e8c862a',
        9,
        2,
        '424432e67ceaddb365e3b800346ef23a205e2812c1a3d8b886c8304d32e5eabe'
    UNION ALL SELECT
        's_academy01',
        'eecba76b10c60ea71747885efe64bff5c67309bfe4d5622cfa14597eabdd6faf',
        10,
        2,
        'b11c9dc952f53f970e3b9bd205d7c078616a7a7763616a930e555f85cf0032a7'
    UNION ALL SELECT
        's_academy01',
        'b2c0634bae00760d79130d7936771c7526f5a90121f9dca9d96e0b64317f9b2d',
        12,
        2,
        'a5ec0ff75edfbf04a470e1cb7d0715ee0116b9caeaad5464cbc0af9f95b5a47b'
)
INSERT OR IGNORE INTO rpg_session_story_memory_evidence (
    story_memory_id,
    message_id,
    turn_id,
    message_version,
    content_hash
)
SELECT
    memories.id,
    messages.id,
    messages.turn_id,
    messages.version,
    seeds.content_hash
FROM evidence_seeds AS seeds
JOIN rpg_session_story_memories AS memories
    ON memories.session_id = seeds.session_id
    AND memories.dedupe_key = seeds.dedupe_key
JOIN rpg_session_messages AS messages
    ON messages.session_id = seeds.session_id
    AND messages.turn_id = seeds.turn_id
    AND messages.seq_in_turn = seeds.seq_in_turn;

-- Persistent Memory demo ledger. These rows intentionally have no synthetic
-- proposal: they model already-applied, evidence-valid long-term facts.
INSERT OR IGNORE INTO rpg_session_persistent_memories (
    id,
    session_id,
    dedupe_key,
    lifecycle,
    current_revision_number
)
VALUES
    (
        'demo_forest_alice_companion',
        's_forest001',
        'd2816be98f2649f219d5793dbcdbeffc2fa719085442cb4b252889eee2b21e22',
        'active',
        1
    ),
    (
        'demo_forest_research_society',
        's_forest001',
        'd4d3e48f1fd77d21123a729f6d0266cf85894f1ffcf08aa9dec434d125140c3a',
        'active',
        1
    ),
    (
        'demo_forest_black_feather',
        's_forest001',
        '57ff671e7423f8b125903ddcbf837e5366451c0b31a0e8d99b61df30daad27ff',
        'active',
        1
    ),
    (
        'demo_academy_firewax_key',
        's_academy01',
        '876c9ced21761c345ca9ba1b55f3ed9a9c8e23d53eb720f3fd40ecf67b203709',
        'active',
        1
    ),
    (
        'demo_academy_morlan_cooperation',
        's_academy01',
        '7ff21226f8e9001c02aa0822712ff7ed878e916bf55229ef6f8acbf218f56b42',
        'active',
        1
    ),
    (
        'demo_academy_branch_brand',
        's_academy01',
        '8188e8bf471af38ec427dc0ef7e9cdf5463752ab2db47387b4bcc40652a8af82',
        'active',
        1
    );

INSERT OR IGNORE INTO rpg_session_persistent_memory_revisions (
    memory_id,
    revision_number,
    text,
    memory_kind,
    epistemic_status,
    salience
)
VALUES
    (
        'demo_forest_alice_companion',
        1,
        'Alice 是 Bob 在北境调查中的同行法师，能够用冷蓝火焰辨认封印与银字。',
        'relationship',
        'confirmed',
        0.90
    ),
    (
        'demo_forest_research_society',
        1,
        '炎心之木研究会二十年前因试图把封印当作燃料而被学院取缔。',
        'world_fact',
        'confirmed',
        0.93
    ),
    (
        'demo_forest_black_feather',
        1,
        '黑羽上的银字明确写着：North Gate opens when the tree burns.',
        'clue',
        'confirmed',
        0.96
    ),
    (
        'demo_academy_firewax_key',
        1,
        '东塔地下库的合法入口凭证包括旧式火漆钥匙。',
        'world_fact',
        'confirmed',
        0.88
    ),
    (
        'demo_academy_morlan_cooperation',
        1,
        '管理员莫兰已经选择协助 Alice 调查炎心之木禁档。',
        'relationship',
        'confirmed',
        0.91
    ),
    (
        'demo_academy_branch_brand',
        1,
        '树枝烙印代表炎心之木研究会正在寻找尚未点燃的载体。',
        'clue',
        'confirmed',
        0.90
    );

WITH evidence_seeds AS (
    SELECT
        'demo_forest_alice_companion' AS memory_id,
        's_forest001' AS session_id,
        9 AS turn_id,
        2 AS seq_in_turn,
        'dcaee7191dbb80d284f41a1d201094e303f1db7eb9dc4fb685c369de4046734d' AS content_hash
    UNION ALL SELECT
        'demo_forest_research_society',
        's_forest001',
        6,
        2,
        'e04f4a016222dc252590368ca9f1e9bfde925099d5bb2ebd9a6aef8c612ba68f'
    UNION ALL SELECT
        'demo_forest_black_feather',
        's_forest001',
        8,
        2,
        '55b4e38748c98ceb127fad9c5b6bad0ac9feb5f034b3e53974f190ae7786d54f'
    UNION ALL SELECT
        'demo_academy_firewax_key',
        's_academy01',
        2,
        2,
        '1d2a15545fffa134429f907ba660ed0c04258a79fc241cbfc2f883f4ce278808'
    UNION ALL SELECT
        'demo_academy_morlan_cooperation',
        's_academy01',
        12,
        2,
        'a5ec0ff75edfbf04a470e1cb7d0715ee0116b9caeaad5464cbc0af9f95b5a47b'
    UNION ALL SELECT
        'demo_academy_branch_brand',
        's_academy01',
        5,
        2,
        '03a57209f0c0f61f631612fa0af1367cb07c4a6d8d64977b0838cf13a805efdb'
)
INSERT OR IGNORE INTO rpg_session_persistent_memory_evidence (
    revision_id,
    message_id,
    turn_id,
    message_version,
    content_hash
)
SELECT
    revisions.id,
    messages.id,
    messages.turn_id,
    messages.version,
    seeds.content_hash
FROM evidence_seeds AS seeds
JOIN rpg_session_persistent_memory_revisions AS revisions
    ON revisions.memory_id = seeds.memory_id
    AND revisions.revision_number = 1
JOIN rpg_session_messages AS messages
    ON messages.session_id = seeds.session_id
    AND messages.turn_id = seeds.turn_id
    AND messages.seq_in_turn = seeds.seq_in_turn;

INSERT OR IGNORE INTO rpg_session_dream_states (
    session_id,
    ledger_revision,
    messages_manifest_json,
    story_memories_manifest_json,
    summary_batches_manifest_json
)
VALUES
    ('s_forest001', 1, '{}', '{}', '{}'),
    ('s_academy01', 1, '{}', '{}', '{}');
