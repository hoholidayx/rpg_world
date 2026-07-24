# 视觉目录、来源与设计工作流字段

> authoringRulesVersion=1.0 · catalogDigest=527f14f1bdb07acefe4cc182cea18f3379fb220f4f8b81a8992381f805d4625f

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### 只有当前 revision 可发布

本地 revision 不等于发布；只从 current revision 构建 Story Pack。

运行时影响：历史 revision 和 source 文件不会因存在而进入运行时。

### 来源不自动获得导入授权

历史导出和 sources 只作为参考；内容必须重新选择、编写并确认后进入当前 revision。

运行时影响：导入只消费 Story Pack，不扫描 sources。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `VisualSpec` | `/resources/visualCatalog/*/assetType` | 视觉资产用途类别，例如角色立绘、场景或地图。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/negativePrompt` | 明确需要排除的视觉元素、瑕疵或风格。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/prompt` | 可直接生图的正向 brief，写主体、场景、构图、光线和风格。 | 不要把排除项混入正向 prompt；排除项写 negativePrompt。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/subjectRefs` | 该视觉 brief 涉及的 Story 资源 stableId。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `VisualSpec` | `/resources/visualCatalog/*/visualAnchors` | 只放跨变体必须稳定的身份或物件特征，不放姿势和光线。 | 不要写可变服装、姿势、镜头或照明，除非它们是身份锚点。 | 仅归档可生图规格，不创建媒体资产、任务或消息。 |
| `DecisionRecord` | `/decisions/*/decidedAt` | 决策落入 revision 时的 UTC 时间。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `DecisionRecord` | `/decisions/*/decision` | 实际确认或暂定的设计结论。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `DecisionRecord` | `/decisions/*/id` | 该决策、问题或来源在项目内保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `DecisionRecord` | `/decisions/*/rationale` | 选择该方案的简短理由和关键权衡。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `DecisionRecord` | `/decisions/*/status` | 该记录当前的工作流状态。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `DecisionRecord` | `/decisions/*/topic` | 本次决策处理的简短主题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `OpenQuestion` | `/openQuestions/*/context` | 理解该问题所需的背景和影响。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `OpenQuestion` | `/openQuestions/*/id` | 该决策、问题或来源在项目内保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `OpenQuestion` | `/openQuestions/*/options` | 可供比较的具体选项，不代替用户确认。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `OpenQuestion` | `/openQuestions/*/question` | 需要用户回答的单一、可决策问题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `OpenQuestion` | `/openQuestions/*/status` | 该记录当前的工作流状态。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `SourceRecord` | `/sources/*/id` | 该决策、问题或来源在项目内保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `SourceRecord` | `/sources/*/locator` | 只定位参考资料；不得使用绝对路径、file: URL 或 .. 逃逸项目根目录。 | 不要因来源已登记就自动导入其全部内容。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `SourceRecord` | `/sources/*/notes` | 简短工作备忘；不要用作正式字段或聊天记录的替代品。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `SourceRecord` | `/sources/*/sourceType` | 来源类别，例如本地文档、导出会话或外部网址。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |
| `SourceRecord` | `/sources/*/title` | 面向作者、玩家或管理界面的短标题。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 只影响设计恢复与决策追踪，不直接进入运行时 Story。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `workflow.open-question-unresolved` | warning | 设计中仍有未解决的开放问题。 | 决策后更新设计字段，并把问题标记为 resolved。 |
| `visual.anchors-empty` | warning | 视觉规格没有稳定 visualAnchors。 | 列出跨立绘/场景变体应保持不变的身份、形制或辨识特征。 |
| `visual.subject-ref-unresolved` | warning | visual subjectRef 在当前 Story 中找不到对应 stableId。 | 修正 stableId，或在 metadata 中记录非资源概念而不要伪造引用。 |
