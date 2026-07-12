UPDATE rpg_stories
SET
    first_message = '北境森林的霜雾刚漫过石林入口，幽蓝封印在远处一明一暗。你——{USER_PLAY_ROLE_NAME}——听见祭坛方向再次传来潮声。',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = 'demo_workspace'
  AND title = '北境森林 Demo'
  AND first_message = '北境森林的霜雾刚漫过石林入口，幽蓝封印在远处一明一暗。Alice 收紧斗篷，看向你：“Bob，祭坛那边又有潮声了。”';

UPDATE rpg_stories
SET
    first_message = '旧档案馆的铜铃在午后轻响，管理员莫兰把一叠封蜡破损的登记簿推到桌边，看向你：“{USER_PLAY_ROLE_NAME}，如果你真要查炎心之木，就从这一本开始。”',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = 'demo_workspace'
  AND title = '奥术学院 Demo'
  AND first_message = '旧档案馆的铜铃在午后轻响，管理员莫兰把一叠封蜡破损的登记簿推到桌边：“Alice，如果你真要查炎心之木，就从这一本开始。”';

UPDATE rpg_characters
SET
    metadata_json = '{"kind":"demo"}',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = 'demo_workspace'
  AND name = 'Bob'
  AND metadata_json = '{"kind":"demo","role":"player"}';

UPDATE rpg_characters
SET
    metadata_json = '{"kind":"demo"}',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = 'demo_workspace'
  AND name = 'Alice'
  AND metadata_json = '{"kind":"demo","role":"companion"}';
