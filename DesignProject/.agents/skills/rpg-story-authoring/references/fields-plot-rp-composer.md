# 剧情调度、RP Module 与 Composer 字段

> authoringRulesVersion=1.0 · catalogDigest=527f14f1bdb07acefe4cc182cea18f3379fb220f4f8b81a8992381f805d4625f

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### message_mode 由代码内置

message_mode 只声明启用且 config 为空；neutral/ic/ooc/gm 的标签和 Prompt 不属于设计数据。

运行时影响：OOC 不推进 Plot、Status、Scene 或 Memory 事实。

### 节点触发不等于章节完成

大纲节点被注入只表示其 directive 已触发，不代表玩家完成、跳过或解决了章节。

运行时影响：当前 Plot ledger 记录 triggered，不提供章节完成生命周期。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `NarrativeStyleSpec` | `/resources/narrativeStyles/*/isBase` | 是否作为唯一基础叙事风格；同一 Story 最多一个。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `NarrativeStyleSpec` | `/resources/narrativeStyles/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `NarrativeStyleSpec` | `/resources/narrativeStyles/*/prompt` | 提供给对应生成环节的正向指令正文。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `NarrativeStyleSpec` | `/resources/narrativeStyles/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `NarrativeStyleSpec` | `/resources/narrativeStyles/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `QuickReplySpec` | `/resources/quickReplies/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `QuickReplySpec` | `/resources/quickReplies/*/message` | 实际提交给玩家或 Agent 的正文文本。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `QuickReplySpec` | `/resources/quickReplies/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `QuickReplySpec` | `/resources/quickReplies/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `QuickReplySpec` | `/resources/quickReplies/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/allowRepeat` | 该事件触发后是否允许再次候选。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/deadlineTime` | 事件窗口的排他上界；到达此时即不再候选。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/description` | 管理摘要：事件是什么、为什么存在；不承担触发指令。 | 不要用命令语气要求主 Agent 落实剧情。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/directive` | 事件触发后必须落实的世界/NPC行为；保留玩家选择，不把后果提前写成事实。 | 不要替玩家决定行动、同意或情绪，也不要预写未发生后果。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/dispatchMode` | forced 到时直接注入；soft 还需适宜性判断。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/poolRef` | 该事件所属事件池的 stableId。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/position` | 同一容器内的稳定顺序位置。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/repeatCooldownMinutes` | 重复事件两次触发之间的故事分钟冷却。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/scheduledTime` | 事件或节点最早可进入候选的 SceneTime。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/suitabilityHint` | 只说明 soft 事件何时适合开始，包括阶段、地点、在场角色、前置事实和安全边界；不重复 directive。 | 不要把它当确定性 DSL 或重复剧情正文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/dispatchMode` | forced 到时直接注入；soft 还需适宜性判断。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/eventRef` | 该节点引用的剧情事件 stableId。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/position` | 同一容器内的稳定顺序位置。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/scheduledTime` | 节点最早可注入时间；注入只代表触发 directive，不代表章节完成。 | 不要把节点触发时间解释成章节完成时间。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/description` | 供作者和管理界面理解对象用途的说明。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/nodes` | 该大纲按 position 排列的节点。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/priority` | 同类调度对象之间的相对优先级。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/description` | 说明池的主题、用途和候选边界，不写单个事件指令。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/priority` | 同类调度对象之间的相对优先级。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/selectionMode` | 池内候选的 random 或 sequential 抽取方式。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/events` | 剧情事件定义；每条事件只归一个池。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/outlines` | 顺序大纲定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/pools` | 剧情事件池定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响可推进世界 turn 的剧情候选、判断和 directive 注入。 |
| `RPModuleSpec` | `/resources/rpModules/*/config` | 只填写模块公开 Schema 支持的配置；message_mode 是代码内置空配置模块。 | 不要为 message_mode 创建 Prompt、模式标签或 Workspace 配置。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |
| `RPModuleSpec` | `/resources/rpModules/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |
| `RPModuleSpec` | `/resources/rpModules/*/moduleName` | 仓库内置 RP Module 的代码名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `plot.soft-event-hint-empty` | warning | soft 事件没有 suitabilityHint。 | 补充适合开始的阶段、地点、在场人物、前置事实与安全边界。 |
| `plot.forced-event-unused-hint` | warning | forced 事件填写了 suitabilityHint，但 forced 调度不会等待 soft 判断。 | 若条件必须被判断，改用 soft；否则把必要内容移入 directive 或管理说明。 |
| `plot.event-description-empty` | warning | 剧情事件缺少管理摘要 description。 | 用一两句话说明事件是什么及其设计用途，不重复 directive。 |
| `plot.directive-controls-player` | warning | 剧情 directive 疑似替玩家决定行动、同意或结果。 | 只控制世界与 NPC，给出有意义选择，并把后果留到玩家行动后确认。 |
| `composer.style-prompt-empty` | warning | 叙事风格没有 Prompt。 | 填写可稳定复用的写作约束，或移除无效风格。 |
