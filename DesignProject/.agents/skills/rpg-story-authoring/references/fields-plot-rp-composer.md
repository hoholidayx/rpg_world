# 剧情调度、RP Module 与 Composer 字段

> authoringRulesVersion=1.3 · catalogDigest=340c9ac89c0854acee8f39bf0badd0e49c1171d21a497ef009431a680df9d431

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### message_mode 由代码内置

message_mode 只声明启用且 config 为空；neutral/ic/ooc/gm 的标签和 Prompt 不属于设计数据。

运行时影响：neutral、ic 与 gm 是非 OOC 正文 turn；OOC 不推进 Plot、Status、Scene 或 Memory 事实，命令也不属于正文 turn。

### Scene 净变化产生一次自动调度机会

自动 selector 不按每个 turn 运行。只有成功提交 turn 后整个 active Scene document 的最终内容发生净变化，才为下一次非 OOC turn 留下一次机会；变化覆盖时间、位置、在场人物、其他字段及获准的 key 结构变化。不要用无事实变化的 Scene 写入轮询事件。

运行时影响：下一次 neutral、ic 或 gm turn 在 StatusPreflight 后使用最新 scratch Scene 消费机会，最多选择一个大纲节点和一个池事件；消费 turn 若再次改变 Scene，则为再下一轮留下新机会。OOC、命令、Plot 模块禁用、失败或取消既不消费也不创建机会；无机会时不运行 selector 或 soft judge。

### 大纲绑定事件不占事件池调度

只要剧情事件仍被任意大纲节点引用，就永久从自动 pool lane 候选中排除，不受大纲、节点或 Session 覆盖当前是否启用影响。删除该事件的全部节点引用后，它才重新成为池内候选。

运行时影响：大纲 lane 仍按自身节点独立调度；结构绑定避免同一事件同时消耗大纲和事件池额度。Session 手动标记仍可绕过该结构隔离。

### 事件池共享自动注入冷却

cooldownMinutes 是非负 SceneTime 分钟。池内任意事件最近一次由自动 scheduler 在 pool lane 成功注入后，只要 elapsed 小于当前池配置，整个池都不参与候选；elapsed 大于或等于配置时恢复。高强度巧合还应只在已有关系、信息或利益张力时通过 suitabilityHint 表达适宜性。

运行时影响：冷却锚点只认 sourceKind=pool、selectionOrigin=scheduler、decisionStatus=triggered 的已提交决策及其 containerId。手动注入、大纲注入、deferred 和 error 均不启动、刷新或清除池级冷却。

### 手动下一轮标记是 Session 临时快照

`plot_event_mark_next` 只在 OOC/GM 运行时把现有事件冻结为 Session 一次性快照；可临时覆盖 title/directive，省略时保留原内容，event_id=null 清空。该快照及工具参数不是 Story Design 或 Story Pack 字段，也不修改原事件。

运行时影响：快照在下一次 neutral、ic 或 gm turn 强制注入，忽略 Scene 调度机会、SceneTime、enabled、时间窗、大纲绑定、重复和冷却等全部自动规则；即使无 SceneTime 也可触发并解除该事件已有的事件级冷却锚点，但不会启动、刷新或清除事件池级冷却锚点。

### 节点触发不等于章节完成

Plot 的 triggered 只表示事件或大纲节点已被选择并把 directive 注入当前请求，不代表模型已落实，也不代表玩家完成、跳过或解决了章节。

运行时影响：当前 Plot ledger 记录 selected-and-injected 的 triggered，不提供语义验收或章节完成生命周期。

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
| `PlotEventSpec` | `/resources/plotSchedule/events/*/allowRepeat` | 事件自动触发后是否可在后续 Scene 调度机会再次候选；手动标记忽略重复限制。 | 不要把手动标记的临时注入计入自动重复资格。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/deadlineTime` | 仅在 Scene 调度机会存在时作为自动事件候选窗口的排他上界；不是定时器。 | 不要把截止时间解释成会自行唤醒 selector 的定时器。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/description` | 管理摘要：事件是什么、为什么存在；不承担触发指令。 | 不要用命令语气要求主 Agent 落实剧情。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/directive` | 事件触发后必须落实的世界/NPC行为；保留玩家选择，不把后果提前写成事实。 | 不要替玩家决定行动、同意或情绪，也不要预写未发生后果。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/dispatchMode` | 一次 Scene 调度机会内的自动候选满足 SceneTime 窗口后，forced 跳过 soft judge，soft 仍需适宜性判断；手动标记不读取此字段。 | 不要把 forced 理解成定时器；没有 Scene 调度机会时不会因此自动运行。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/enabled` | 是否允许事件参与自动 pool lane 候选；大纲节点是否候选由大纲与节点自身开关决定，Session 手动标记的临时注入也忽略此字段。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/poolRef` | 该事件所属事件池的 stableId，用于归属、展示及未绑定大纲时的 pool lane调度；只要仍被任意大纲节点引用，就不参与自动 pool lane。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/position` | 同一容器内的稳定顺序位置。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/repeatCooldownMinutes` | 重复事件两次自动触发之间的 SceneTime 分钟冷却；手动标记忽略冷却，且无 SceneTime 的手动注入会解除该事件已有的事件级冷却锚点，但不影响池级冷却。 | 不要把冷却写成现实时间、turn 数或手动注入限制。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/scheduledTime` | 仅在 Scene 调度机会存在时作为自动候选最早资格门槛的 SceneTime；不是定时器。 | 不要把时间门槛解释成后台定时器或每 turn 轮询触发器。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/suitabilityHint` | 只说明自动 soft 候选何时适合开始，包括阶段、地点、在场角色、前置事实和安全边界；不重复 directive，手动标记不会执行该判断。 | 不要把它当确定性 DSL、手动注入条件或重复剧情正文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotEventSpec` | `/resources/plotSchedule/events/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/dispatchMode` | 一次 Scene 调度机会内，节点满足 SceneTime 门槛后，forced 跳过 soft judge，soft 仍需适宜性判断；手动标记事件不读取节点字段。 | 不要把 forced 节点理解成定时器；没有 Scene 调度机会时不会因此自动运行。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/enabled` | 是否允许节点参与有 Scene 调度机会的自动候选；不限制事件被手动标记。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/eventRef` | 该节点引用的剧情事件 stableId。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/position` | 同一容器内的稳定顺序位置。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/scheduledTime` | 仅在 Scene 调度机会存在时作为节点自动候选的最早资格门槛；不是定时器。注入只代表触发 directive，不代表章节完成。 | 不要把节点时间解释成章节完成时间、后台定时器或每 turn 轮询触发器。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotNodeSpec` | `/resources/plotSchedule/outlines/*/nodes/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/description` | 说明大纲线的主题、节点顺序与用途；节点仍只在 Scene 调度机会中成为自动候选。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/enabled` | 是否允许该大纲参与有 Scene 调度机会的自动候选；不限制其事件被手动标记。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/nodes` | 该大纲按 position 排列的节点。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/priority` | 一次 Scene 调度机会内，同类候选之间的相对优先级。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotOutlineSpec` | `/resources/plotSchedule/outlines/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/cooldownMinutes` | 池内任意事件最近一次以 scheduler 来源在 pool lane 成功注入后，整个池需等待的 SceneTime 分钟；0 表示关闭。手动标记、大纲注入、延期和错误都不启动、刷新或清除池级冷却。创作时可按强度分池：日常现实扰动建议半天到一天，人际/信息/工作压力建议数天，改变关系结构的戏剧性巧合建议十天到数周；这些只是调参建议，不是 schema 默认值。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/description` | 说明池的主题、用途、自动候选边界和建议冷却档位，不写单个事件指令。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/enabled` | 是否允许该池参与有 Scene 调度机会的自动候选；手动标记忽略此字段。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/priority` | 一次 Scene 调度机会内，同类候选之间的相对优先级。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/selectionMode` | 有 Scene 调度机会时，池内候选的 random 或 sequential 抽取方式。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotPoolSpec` | `/resources/plotSchedule/pools/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/events` | 剧情事件定义；每条事件只归一个池。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/outlines` | 顺序大纲定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `PlotScheduleSpec` | `/resources/plotSchedule/pools` | 剧情事件池定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `RPModuleSpec` | `/resources/rpModules/*/config` | 只填写模块公开 Schema 支持的配置；message_mode 是代码内置空配置模块。 | 不要为 message_mode 创建 Prompt、模式标签或 Workspace 配置。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |
| `RPModuleSpec` | `/resources/rpModules/*/enabled` | 是否在导入后启用该资源或模块。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |
| `RPModuleSpec` | `/resources/rpModules/*/moduleName` | 仓库内置 RP Module 的代码名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `plot.soft-event-hint-empty` | warning | soft 事件没有 suitabilityHint。 | 补充适合开始的阶段、地点、在场人物、前置事实与安全边界。 |
| `plot.forced-event-unused-hint` | warning | forced 事件填写了 suitabilityHint，但自动 forced 候选不会等待 soft 判断。 | 若条件必须被判断，改用 soft；否则把必要内容移入 directive 或管理说明。 |
| `plot.event-description-empty` | warning | 剧情事件缺少管理摘要 description。 | 用一两句话说明事件是什么及其设计用途，不重复 directive。 |
| `plot.directive-controls-player` | warning | 剧情 directive 疑似替玩家决定行动、同意或结果。 | 只控制世界与 NPC，给出有意义选择，并把后果留到玩家行动后确认。 |
| `composer.style-prompt-empty` | warning | 叙事风格没有 Prompt。 | 填写可稳定复用的写作约束，或移除无效风格。 |
