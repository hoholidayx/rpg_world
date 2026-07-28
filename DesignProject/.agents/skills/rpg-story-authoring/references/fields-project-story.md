# 项目、Story 与 Opening 字段

> authoringRulesVersion=1.2 · catalogDigest=2b31edf08c2ba281ceb1a8a6fa90937c42b3774f9162a82818d86ebdbc59af52

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### Story 直属资源

Character、Lorebook 与 Status 都直接归 Story 所有；不得设计 Workspace 资产库或 mount 层。

运行时影响：运行时 CRUD 和稳定绑定都以 workspaceId + storyId 校验归属。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `StoryPackApplyPolicy` | `/applyPolicy/deleteMissing` | Story Pack v2 固定为 false；遗漏资源不代表删除。 | 不要把小包遗漏解释成删除授权。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPackApplyPolicy` | `/applyPolicy/mode` | Story Pack v2 固定为 merge。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/applyPolicy` | 固定的 merge-only、deleteMissing=false 导入策略。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/contractVersion` | 固定的 MCP/Story Pack 合约版本；只接受 2.0。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/generatedAt` | 包构建时沿用的确定性 UTC 时间。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/includedSections` | 本包实际携带的 merge-only sections。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/packId` | 由 revision、目标和 sections 确定的不可变 Story Pack ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/projectId` | DesignProject 的稳定 ID；不是 Workspace ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/resources` | 当前 Story 的可导入资源集合。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/schemaVersion` | 固定的文档 Schema 版本；只接受当前 v2 值。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/sourceDigest` | 构建时源 Story Design 的 SHA-256 摘要。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/sourceRevision` | 构建本包的不可变 DesignProject revision。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/story` | 当前唯一 Story 的核心设定。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/storyStableId` | Story 的稳定 ID，必须与 story.stableId 相同。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryPack` | `/target` | 构建或同步时的 Workspace/Story 目标；不是 Story 内容。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 控制 Story Pack 身份、范围和 merge-only 导入行为。 |
| `StoryDesignDocument` | `/decisions` | 结构化设计决策历史；不保存原始聊天记录。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/notes` | 简短工作备忘；不要用作正式字段或聊天记录的替代品。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/openQuestions` | 仍待决策、已解决或延期的结构化问题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/project` | DesignProject 的便携身份、语言和当前设计阶段。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/resources` | 当前 Story 的可导入资源集合。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 承载可进入 Story Pack 的 Story 直属资源；各子字段按其资源类型影响运行时。 |
| `StoryDesignDocument` | `/schemaVersion` | 固定的文档 Schema 版本；只接受当前 v2 值。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/sources` | 参考来源定位；来源存在不等于获准导入其全部内容。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryDesignDocument` | `/story` | 当前唯一 Story 的核心设定。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryDesignDocument` | `/target` | 构建或同步时的 Workspace/Story 目标；不是 Story 内容。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `ProjectIdentity` | `/project/language` | 主要创作语言的 BCP 47 风格标记。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `ProjectIdentity` | `/project/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `ProjectIdentity` | `/project/phase` | 当前设计成熟阶段，用于恢复工作而非运行时剧情状态。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `ProjectIdentity` | `/project/projectId` | DesignProject 的稳定 ID；不是 Workspace ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `StoryResources` | `/resources/characters` | 直接归当前 Story 所有的角色卡。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。 |
| `StoryResources` | `/resources/lorebook` | 直接归当前 Story 所有的世界书条目。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 作为 Story 世界知识进入运行时检索与 Context。 |
| `StoryResources` | `/resources/narrativeStyles` | 需在 Workspace 创建并绑定到 Story 的叙事风格。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `StoryResources` | `/resources/openings` | 最多三条按 sortOrder 排序的 Opening。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story Opening 定义；首次有效绑定角色且历史为空时可追加所选开场。 |
| `StoryResources` | `/resources/plotSchedule` | Story 级事件池、大纲和事件调度配置；自动 selector 只在已提交 Scene 净变化留下机会后运行。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC turn 的候选、判断和 directive 注入。 |
| `StoryResources` | `/resources/quickReplies` | Story Composer 的快捷玩家输入。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 影响 Story 叙事风格绑定或玩家快捷输入。 |
| `StoryResources` | `/resources/rpModules` | Story 允许启用的内置 RP Module。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。 |
| `StoryResources` | `/resources/statusTables` | 直接归当前 Story 所有的状态定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StoryResources` | `/resources/visualCatalog` | 只归档、不自动创建媒体任务的独立视觉 brief。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `RuntimeTarget` | `/target/allowCreateWorkspace` | 目标 Workspace 不存在时是否允许导入流程创建它。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `RuntimeTarget` | `/target/storyId` | 已存在目标 Story 的运行时数字 ID；新建时留空。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `RuntimeTarget` | `/target/workspaceId` | 目标 RPG World Workspace 的稳定文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `RuntimeTarget` | `/target/workspaceName` | 仅在允许创建 Workspace 时使用的显示名。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `RuntimeTarget` | `/target/workspaceRoot` | 目标 Workspace 的安全相对运行目录。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响 DesignProject 恢复、构建目标和作者工作流。 |
| `OpeningSpec` | `/resources/openings/*/message` | 实际提交给玩家或 Agent 的正文文本。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `OpeningSpec` | `/resources/openings/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `OpeningSpec` | `/resources/openings/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `OpeningSpec` | `/resources/openings/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/boundaries` | 内容安全边界与明确不可发生的叙事行为。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/logline` | 一句话核心冲突：主角、目标、阻力和主要代价。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要写 _rpgStoryDesign；该键由运行时适配器保留。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/storyPrompt` | 每个 Agent 正文 turn 使用的固定 Story 规则与叙事约束。 | 不要写易变 Scene、当前状态值或 message_mode 提示。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/summary` | Story 的短管理摘要，说明体验与前提，不写执行指令。 | 不要写固定 Prompt、逐场景正文或当前 Session 状态。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/themes` | 需要持续回响的主题关键词或短语。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/timeSetting` | 故事虚拟年代、历法与时间锚点的文字说明。 | 不要用“1 年”代替已确定的 2019、2020 等虚拟年份。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |
| `StoryCore` | `/story/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 进入 Story 固定层或 Story 管理数据，并影响后续 Session。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `package.story-title-required` | error | 构建 Story Pack 前必须填写 story.title。 | 填写面向玩家和管理界面的 Story 标题。 |
| `package.workspace-required` | error | 构建 Story Pack 前必须确定 target.workspaceId。 | 在设计目标或 build override 中提供 Workspace ID。 |
| `package.workspace-name-required` | error | 允许创建 Workspace 时必须填写 workspaceName。 | 填写新 Workspace 的显示名，或关闭 allowCreateWorkspace。 |
| `package.workspace-root-required` | error | 允许创建 Workspace 时必须填写安全相对 workspaceRoot。 | 例如填写 data/my_world，或关闭 allowCreateWorkspace。 |
| `quality.story-title-empty` | warning | Story 标题仍为空，当前适合脑暴但尚不可构建。 | 在核心前提稳定后补充简短标题。 |
| `quality.target-unset` | warning | 尚未设置运行时 Workspace 目标。 | 可以继续设计；准备构建时再填写 target 或 build override。 |
| `quality.opening-missing` | warning | 当前没有 Opening。 | 若希望新 Session 有作者编写的开场，请添加 1–3 条 Opening。 |
| `quality.story-prompt-empty` | warning | Story Prompt 为空，运行时只能依赖系统通用规则。 | 补充本故事固定且跨 turn 稳定的叙事约束。 |
| `quality.story-summary-too-long` | warning | story.summary 过长，可能混入了 Prompt 或场景正文。 | 压缩为约 240 字以内的管理摘要，细节移到对应资源。 |
