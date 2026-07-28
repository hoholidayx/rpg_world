# 角色与世界书字段

> authoringRulesVersion=1.1 · catalogDigest=1acda22f205196e619d530f3034bbf002d9ced110199a5e35fa5ba089507be2a

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `CharacterDetailSpec` | `/resources/characters/*/details/*/content` | 只写当前 kind 对应的一类信息，避免客观事实与演绎要求混写。 | 不要在同一 detail 混合客观信息和 NPC 演绎要求。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterDetailSpec` | `/resources/characters/*/details/*/name` | 该条详情的职责标题，例如“外貌”或“NPC 说话方式”。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterDetailSpec` | `/resources/characters/*/details/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterDetailSpec` | `/resources/characters/*/details/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterDetailSpec` | `/resources/characters/*/details/*/tags` | 使用一个主要 kind 标签；演绎 kind 会自动附加 scope:npc_portrayal。 | 不要发明 kind:/scope: 保留标签或手工移除演绎 scope。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/aliases` | 角色可被识别的别名、称呼或旧名。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/description` | 只写角色身份、经历和客观事实；性格、口癖、行为倾向与心理必须拆到带演绎 kind 标签的 details。 | 不要写性格、说话方式、行为倾向或心理活动。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/details` | 按职责拆分的角色客观详情或 NPC 演绎详情。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `CharacterSpec` | `/resources/characters/*/visual` | 与本资源绑定的视觉身份锚点和可变造型资料。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `LorebookSpec` | `/resources/lorebook/*/content` | Agent 可使用的完整世界事实、规则、地点或组织资料。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/description` | 供作者浏览的短管理摘要，不代替 content 世界事实。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/tags` | 检索和运行时过滤使用的去重标签。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `LorebookSpec` | `/resources/lorebook/*/visual` | 与本资源绑定的视觉身份锚点和可变造型资料。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `character.description-portrayal-leak` | warning | 角色 description 疑似包含性格、说话、行为或心理演绎。 | description 只保留身份/经历/客观事实；演绎内容拆到带 kind 标签的 details。 |
| `character.detail-mixed-kinds` | warning | 同一角色 detail 同时包含客观 kind 与演绎 kind。 | 拆成两条 detail；整条演绎 detail 会按 npc_portrayal 过滤。 |
| `character.detail-kind-missing` | warning | 角色 detail 没有主要 kind 标签。 | 选择一个 objective 或 portrayal kind；自定义普通标签可额外保留。 |
| `lorebook.content-empty` | warning | 世界书条目只有名称/摘要，没有可供 Agent 使用的 content。 | 补充稳定的世界事实、规则或关系；纯视觉内容可改放 visualCatalog。 |
