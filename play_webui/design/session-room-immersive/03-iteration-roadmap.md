# 独立沉浸式 Session 页面后续迭代计划

> 原则：新增独立沉浸式页面，从标准 SessionRoom 抽取共享前端领域运行时；两个页面并行消费同一业务链路。沉浸分页只在前端视图层发生，不修改正文 SSE。每一阶段都能独立验收和回滚。

## 1. 目标与优先级

### P0：先解决核心游玩体验

- 舞台化背景与 HUD。
- 不遮挡立绘的窄幅分页对白。
- 2K / 4K 可读性。
- 自由行动与现有快捷回复。
- 单一“全部推演日志”。
- 大尺寸角色与世界状态工作台。
- 纯净舞台。
- 人物关系按多字段和文本状态展示。

### P1：补齐可靠的角色舞台数据

- 角色与 sprite Asset 的稳定绑定。
- 多角色站位、层级、姿势和焦点。
- 无资产或媒体故障时的完整降级。

### P2：可选增强

- 每 turn 动态行动建议。
- 更丰富的关系网络投影。
- 性能、无障碍、移动端和独立入口灰度优化。

## 2. 阶段依赖

```text
Phase 0 设计与契约冻结
   └─ Phase 1 独立沉浸式页面与共享运行时
       ├─ Phase 2 状态工作台与关系投影
       └─ Phase 3 角色立绘舞台契约
             └─ Phase 5 整体验收与双页面灰度

Phase 4 动态行动建议为独立可选项，可在 Phase 1 后单独决策。
```

## 3. Phase 0：设计与数据决策冻结

### 目标

在进入生产代码前，把不会随实现人员变化的产品语义和数据边界写清楚。

### 变更范围

- 以本目录静态稿和三份文档作为设计基线。
- 完成独立沉浸式 Session 页面的简短 ADR / 技术设计。
- 确认以下决策：
  - 没有章节和支线概念。
  - assistant 完整正文是真源，分页是临时展示投影。
  - 沉浸式体验使用独立路由与页面组件树，不嵌入 `SessionRoom.tsx`。
  - 标准与沉浸式页面通过共享前端领域 runtime/provider/hooks/service 复用业务逻辑。
  - 沉浸分页建立在现有 SSE parser/reducer 组装的 canonical content 之上，不改变 SSE event type、payload 或完成语义，也不按 chunk 分页。
  - 人物关系是通用多字段状态，不是单值好感度。
  - 纯净舞台是临时 UI 状态。
  - thinking 只代表可公开摘要/诊断，不承诺跨刷新完整恢复。
  - 第一阶段使用现有 StoryQuickReply，不承诺动态分支。
- 决定关系专用投影是否需要 typed semantic；没有决定时采用通用状态表展示。
- 为角色舞台投影和动态建议分别建立“需要 / 不需要”的产品决策记录。

### 依赖

- 产品、设计、Play WebUI 和数据/媒体边界负责人共同确认。
- 不依赖后端改动。

### 验收门槛

- 所有参与者对“章节、关系、thinking、立绘、分支”的定义一致。
- 独立页面、共享运行时和正文 SSE 不变的架构边界已写入 ADR。
- Phase 1 不需要临时猜测任何后端字段。
- 视觉稿中的假数据均标注为展示数据或已有真源。

### 测试

- 文档审计：逐条对照 `AGENTS.md`、SessionRoom 组件、类型和 API。
- 原型走查：桌面、2K、移动端、键盘和 reduced motion。

### 回滚方式

本阶段无生产变更，只需修订 ADR 和设计基线。

### 明确不做

- 不新建章节模型。
- 不新建单值 Relationship 实体。
- 不先写 sprite 名称匹配逻辑。
- 不把静态原型假数据接入生产。
- 不把独立页面误实现为 `SessionRoom.tsx` 内的条件布局。
- 不为 DialoguePager 设计新的 SSE 分页事件或字段。

## 4. Phase 1：独立沉浸式页面与共享运行时，不改后端/SSE

### 目标

使用现有会话 hooks、store 与 API 交付一个可独立进入的沉浸式页面，同时把两个页面都需要的业务逻辑抽入共享前端领域运行时。标准 SessionRoom 保持独立，不承载沉浸式布局和页面状态。

### 变更范围

#### 4.1 页面与共享运行时

- 新建独立沉浸式 route/page，拥有自己的 composition root 和组件树。
- 从现有 SessionRoom 组合中抽取共享 `SessionExperienceRuntime` 概念边界，按领域组织 provider、hooks、controller 和 service，而不是建立单一 God hook。
- 共享运行时统一负责 Session 数据与 history window、stream/stop、角色绑定、Composer actions、主模型、Context Preview、status/media/TTS 等能力。
- 标准 SessionRoom 与沉浸式页面分别消费同一类型化 runtime；`SessionRoom.tsx` 不引入沉浸式组件、布局分支或 DialoguePager/HUD/抽屉/纯净舞台状态。
- “共享中间层”是前端领域层，不是 Next.js `middleware.ts`。
- 沉浸式页面内部新建 `ImmersiveSessionExperience`、`ImmersiveStage`、`ImmersiveHud`、`ActiveDialogueDock`、`SessionTraceDrawer`、`WorldStateDrawer` 和 `CinematicModeController`。
- 复用 Composer、Timeline 与 Status Rail 的 controller、消息映射、动作和可共享内容层；两个页面可保留各自的视觉组件。

#### 4.2 对白与纯前端二次分页

分页流水线固定为：

```text
现有 SSE 事件
→ 现有 parser/reducer 组装 canonical assistant content
→ parseAssistantTextSegments()
→ 前端视图测量 + 沉浸分页策略
→ 临时视觉页面
```

- 不新增或修改 SSE event type、payload、顺序、完成语义和 chunk 方式。
- 为已提交历史和当前流式 assistant 使用同一 canonical content 展示投影；流式期间输入是 reducer 已组装的正文前缀，不直接消费 chunk 边界。
- 按对白容器实际宽高、字体、字号、行高、段落类型、中文标点和最大行数进行视觉二次分页。
- 视口、字体缩放、浏览器缩放或屏幕方向变化时重新测量；阅读位置用字符偏移锚定，不依赖旧页码。
- 流式增长时保持已展示和已读页面稳定，只重算未读尾部，避免当前页抖动。
- `pageIndex`、`pageCount`、字符页边界和测量缓存只驻留当前页面内存，不写 SSE、API、message metadata、数据库或 localStorage。
- `history-page` 继续只负责服务端 turn 历史窗口，不能与 DialoguePager 的视觉页状态混用。
- 对话 Dock 设响应式宽度和像素上限：
  - 普通桌面约 58%–62%。
  - 2K 约 48%–54%。
  - 4K 继续使用像素上限。
- 默认仅遮挡人物下肢；允许多次“继续阅读”。点击正在显示的页面先补全，再翻页。
- 支持 AUTO 和 reduced motion。

#### 4.3 操作

- 保留现有 IC/OOC/GM、命令、叙事风格、主模型和 Context Preview。
- 沉浸式 Composer 视图通过共享 runtime 调用既有 actions，并嵌入 Dialogue Dock。
- 使用现有 StoryQuickReply 绘制选项卡。
- 保留 requestId stop、编辑、重试、删除、复制和 TTS。

#### 4.4 工作台

- 沉浸式页面把状态和日志设计为大抽屉；标准 SessionRoom 的现有栏位不受影响。
- 桌面抽屉目标宽度约 66vw，并设置约 1200–1320px 上限。
- 移动端使用近全屏 bottom sheet。
- 日志只保留“全部”，复用 `history-page` 的 turn 加载和共享消息动作。

#### 4.5 纯净舞台

- 菜单进入纯净舞台。
- 隐藏层同时 `aria-hidden` + `inert`。
- 保留按钮、H 和 Esc 三种恢复方式。
- 不写 localStorage。

### 依赖

- Phase 0 语义与页面边界冻结。
- 现有 `SessionRoom`、`SessionComposer`、`SessionTimeline`、`SessionStatusRail` 中的领域逻辑和内容层可被安全抽取。
- 不依赖新后端接口，也不依赖 SSE 协议改动。

### 验收门槛

- 标准 SessionRoom 和沉浸式页面可分别直接进入、刷新、离开，且拥有独立组件树。
- 两个页面对普通发送、流式、停止、角色绑定、Context 门禁和模型切换使用同一共享 runtime 契约，行为一致。
- `SessionRoom.tsx` 不包含沉浸式 UI 分支和页面状态。
- assistant 原始 `content`、SSE event type/payload/顺序/完成语义和数据库写入完全不变。
- 改变同一正文的 SSE chunk 切法不会改变最终视觉分页结果。
- 同一份完整正文在不同视口可以产生不同页数，但所有页面重组后与原正文逐字符一致，没有丢失、重复或改写。
- 视口或字体变化后可以重分页；流式增长时已读页保持稳定。
- 2K 下双角色面部和大部分上半身可见。
- 4K 下对白不横跨整屏，字号清晰但不无限放大。
- 长段落能稳定显示 `1/N`、`2/N`。
- 日志能加载更早/更新记录并跳到最新。
- 纯净舞台没有隐藏焦点。
- 媒体背景失败仍能发送消息。

### 测试

- 共享 runtime 契约测试：两个页面复用 history、stream/stop、role、Composer actions、模型与 Context Preview。
- DialoguePager 单元测试：容器 resize、字体/行高、标点、长文本、emoji、方向变化和字符偏移锚定。
- 分页不变量测试：多种 viewport 页数可不同，页内容重组必须与 canonical content 逐字符一致。
- SSE chunk 独立性测试：对同一正文使用不同 `text_delta` 切分，最终分页结果一致且协议 fixture 不增加字段。
- Active Dialogue 与现有流式 reducer 集成测试。
- 两条页面路由的直达、刷新、返回和 UI 状态隔离测试。
- Composer 发送/停止回归。
- `history-page` 前后分页回归，并验证其状态不影响 DialoguePager。
- role-required、Context 门禁、TTS message ID 回归。
- Playwright 视觉回归：1440×900、1920×1080、2560×1440、3840×2160、390×844。
- 键盘、焦点、reduced motion、200% 字体缩放。
- `cd play_webui && npm run build`。

### 回滚方式

- 隐藏或关闭沉浸式入口/路由即可停止灰度。
- 标准 SessionRoom 始终保持可用，无需切换其布局、回滚其组件树或迁移数据。
- 共享 runtime 的变更必须保持标准页面契约测试通过；如需回退，按领域回退抽取，不引入双实现。
- 不迁移或重写历史数据。

### 明确不做

- 不把沉浸式页面实现为 `SessionRoom.tsx` 中的条件分支。
- 不复制 stream、stop、history、role binding 或 Composer 业务链路。
- 不为视觉分页新增 SSE 事件、payload 字段或后端分页参数，也不按 chunk 分页。
- 不做真实多立绘 Asset 绑定。
- 不做动态 turn 分支。
- 不做跨刷新 thinking 补写。
- 不做专用关系网络图。
- 不删除标准 Timeline 具备的消息操作能力。

## 5. Phase 2：状态工作台与多关系投影

### 目标

让多角色、多状态表、多组关系、线索和待办在沉浸式 UI 中可浏览，并确保关系语义不退化为单一数字。

### 变更范围

#### 5.1 通用状态工作台

- 当前 scene 独立展示，不与 normal 表混合。
- 角色卡按玩家、在场、相关离场角色分组。
- 每个角色展示 0–多张绑定 normal 状态表。
- 未绑定表继续出现在“其他状态表”。
- 保留按 session 的 pin 能力。

#### 5.2 人物关系

- 首先支持一张关系表中的任意 KV：数字、枚举、长文本、未知值。
- 支持同一关系更新多个字段，例如：
  - 信任 64 → 68。
  - 亲密 58 → 60。
  - 依赖 42 → 44。
  - 阶段“默契期”→“信赖加深”。
  - 关系描述和最近变化同步更新。
- 不默认计算总分，不默认画 0–100 进度条。
- 没有关系 semantic 时按通用状态表显示。

#### 5.3 可选 typed semantic

如果产品确认需要专用关系卡：

- 在 API / 数据层定义并校验关系表 semantic。
- 使用 character mount ID 标识关系对象。
- 明确字段排序、数值范围、单位和失效降级。
- 为旧表提供“仍按普通表展示”的零迁移回退。

线索和待办同理：只有显式 semantic 才绘制专用卡片；不匹配表名。

### 依赖

- Phase 1 独立沉浸式页面中的 `WorldStateDrawer` 与共享状态领域 runtime。
- 现有状态表 API 和角色绑定信息。
- 专用关系卡依赖 typed semantic ADR；通用表版本不依赖后端。

### 验收门槛

- 4 名及以上角色时仍能找到每个角色的状态表。
- 同一玩家可以有至少 3 组同时进行的关系。
- 关系卡能显示多个数值、枚举和长文本字段。
- value 为“未知”“不可见”或任意文本时不报错、不显示错误进度条。
- 关系字段缺失时不补 0。
- 自定义普通表不会因名字相似而被误判为关系、线索或任务。

### 测试

- 关系投影单元测试：多字段、文本、缺失、非数值、长值、排序。
- 多角色、多绑定表、无绑定表、失效角色绑定测试。
- scene 与 normal 表分离测试。
- 角色改名、同名角色、无 mount ID 降级测试。
- 状态表 API 契约测试；若引入 typed semantic，补 `play_api/tests/`。
- `cd play_webui && npm run build`。

### 回滚方式

- 专用投影可退回通用状态表卡片。
- 不改变原状态表 `rows[].key/value` 真源。
- 不删除或迁移已有用户状态表。

### 明确不做

- 不将关系压成一个“好感度”。
- 不从数值自动生成阶段或关系文案。
- 不用角色名称替代稳定 ID。
- 不让 WebUI 绕过 Agent 工具直接修改运行时状态。

## 6. Phase 3：角色立绘资产与舞台投影

### 目标

提供与静态稿相当的可靠多立绘舞台，而不是把头像强行放大。

### 变更范围

#### 6.1 数据契约

- 定义角色舞台只读投影：
  - character mount ID。
  - sprite Asset ID。
  - pose key。
  - placement。
  - z-index。
  - focus。
- 决定投影由 scene 返回旁路信息还是经过评审的新只读资源提供。
- 明确 sprite 选择来源和优先级，例如 session override、story default、角色默认。

#### 6.2 媒体边界

- 复用 `character_sprite` 媒体类型。
- Play WebUI 仍只通过 Play API → MediaClient 获取资源。
- 不直接读取工作区图片文件。
- 不把 sprite 引用写入消息正文、metadata 或 localStorage。
- 删除被舞台引用的 Asset 时遵循媒体引用保护。

#### 6.3 前端舞台

- `StageCharacterLayer` 使用稳定 mount ID 渲染。
- 根据当前结构化说话人切换 focus。
- 支持 0/1/2/3+ 角色的确定性布局。
- 资源加载使用预加载、占位和淡入，避免角色闪烁。
- 缺少 sprite 时降级到头像卡、剪影或首字母。

### 依赖

- 媒体、Play API、数据和 WebUI 对舞台投影契约达成一致。
- Phase 1 独立沉浸式页面中的 `ImmersiveStage`。
- 稳定 character mount ID 可从 scene/投影中获得。

### 验收门槛

- 同名角色不会拿错立绘。
- 角色改名后绑定仍然稳定。
- 2–5 名角色站位不覆盖关键面部和对白主要区域。
- speaker 无法匹配时安全降级，不随机聚焦。
- sprite 缺失、加载失败、媒体服务不可用时聊天仍可用。
- 纯净舞台只展示可用背景和立绘，不显示加载错误面板。

### 测试

- 舞台投影 API 契约测试。
- Asset 权限、引用保护、缺失和媒体故障测试。
- 同名、改名、解除挂载、角色删除测试。
- 不同角色数量与站位的视觉回归。
- 背景和 sprite 同时切换时的性能与闪烁测试。
- `cd play_webui && npm run build`。

### 回滚方式

- 关闭 sprite 层后继续使用背景 + 头像/说话人铭牌。
- 舞台投影是只读附加数据，不修改历史和状态表。
- Media service 故障自动进入降级模式。

### 明确不做

- 不用 `presentCharacters` 名称数组当永久绑定键。
- 不在 Play API 直接读本地图片。
- 不让 Media service 导入 Agent runtime。
- 不把姿势或站位写进 assistant 正文。

## 7. Phase 4：可选的动态行动建议

### 目标

在确认确有产品价值后，为每 turn 提供结构化、可失败、可回退的行动建议，增强 Galgame 感，但不削弱自由行动。

### 启动条件

只有同时满足以下条件才进入实施：

- 产品明确区分 StoryQuickReply 与动态建议。
- 已定义建议生成成本和延迟预算。
- 已定义是否持久化、刷新恢复和来源展示。
- 已确定不会泄露内部 reasoning。
- 自由行动仍是始终可用的第一等入口。

### 变更范围

- 定义 turn-scoped suggestion 结构：id、label、prompt、mode。
- 明确建议通过独立受控资源/API 还是既有完成结果的旁路数据交付；无论选哪种方式，都不把 DialoguePager 的视觉页信息加入正文 SSE。
- 点击建议前允许预览或编辑最终 prompt。
- 建议失败、为空或超时直接隐藏建议区，保留自由行动。
- 日志只有在后端有明确来源字段时才标记“预设决策”。

### 依赖

- 独立的 suggestion 数据、服务和前端 client 类型契约。
- 建议 transport 的单独架构决策；正文 SSE 和沉浸分页不依赖该决策。
- 生成成本、并发和故障隔离评审。

### 验收门槛

- 建议不从 assistant 自然语言解析。
- 建议失败不影响正文交付。
- 正文 SSE 不增加视觉分页事件或字段。
- 点击建议最终仍走标准 turn 发送与 stop 链路。
- Context 门禁、角色 invalid 和命令规则不被绕开。
- assistant `content`、message metadata 和历史正文保持既有真源。

### 测试

- 建议成功、为空、超时、服务失败、重复点击。
- 建议出现后切换自由行动。
- 发送后 stop、retry、edit、truncate。
- 刷新后的既定恢复语义。
- 成本和延迟监控。

### 回滚方式

- 关闭建议能力后回到 StoryQuickReply + 自由行动。
- 不迁移历史正文。
- 不影响 Phase 1–3 的沉浸式舞台。

### 明确不做

- 不把选项嵌进 assistant 正文再用正则提取。
- 不把模型内部推理直接展示成选项依据。
- 不因为建议不可用而禁用自由行动。

## 8. Phase 5：性能、无障碍、移动端与双页面灰度

### 目标

完成生产硬化与独立入口灰度，验证标准 SessionRoom 和沉浸式页面长期并存时共享业务逻辑不会分叉。不把“下线标准页面”作为本阶段目标。

### 变更范围

#### 8.1 性能

- 大历史继续使用 turn 分页和窗口缓存。
- 对立绘与背景做尺寸适配、预加载和内存上限。
- 避免流式每个字符触发全舞台重排。
- DialoguePager 缓存稳定消息的测量结果，但缓存只在内存中；流式期间只重算未读尾部。
- 视口、字体和方向变化时使相关测量缓存失效，并用字符偏移恢复阅读位置。

#### 8.2 无障碍

- 完整键盘导航、焦点圈、模态焦点管理。
- 逐字显示与 `aria-live` 分离。
- 纯净舞台 inert 验证。
- 颜色对比、200% 字号和 reduced motion。

#### 8.3 移动端

- 单焦点角色。
- 底部 Dialogue Dock。
- 接近全屏的日志/状态 sheet。
- 软键盘弹起后输入与停止按钮仍可见。
- 不照搬桌面超大抽屉与多角色横向站位。

#### 8.4 独立入口灰度

- 先在内部 / 开发环境开放独立沉浸式路由。
- 再对可控范围用户展示沉浸式入口；标准 SessionRoom 入口持续可用。
- 对比发送成功率、stop 成功率、首屏稳定时间、历史加载错误和媒体错误。
- 对共享 runtime 建立双消费者契约测试和依赖边界检查，防止任一页面复制业务链路。
- 根据产品反馈决定两个入口的默认优先级，但不把标准页面组件并入或迁移到沉浸式页面。

### 依赖

- Phase 1–3 稳定；Phase 4 可选。
- 有独立路由入口开关或等价灰度机制。

### 验收门槛

- 两个页面的核心发送、停止、历史和角色绑定行为通过同一契约测试，线上指标无显著差异。
- 隐藏沉浸式入口后，标准 SessionRoom 不需要切换布局即可继续工作。
- 正文 SSE 在灰度前后保持同一协议，DialoguePager 结果不受 chunk 切分方式影响。
- 2K、4K、移动端和低高度横屏均通过视觉回归。
- 键盘与读屏关键路径通过。
- 媒体服务不可用时核心聊天 SLA 不受影响。
- `npm run build` 与相关 Play API 契约测试通过。

### 测试

- 完整回归矩阵和真实长 Session 压力测试。
- 浏览器缩放、系统字体、触摸和键盘测试。
- 网络慢速、SSE 中断、Media/TTS 故障注入。
- 多窗口或快速切换 Session 的 UI 状态隔离。

### 回滚方式

- 关闭或隐藏独立沉浸式入口；标准 SessionRoom 始终保持可用。
- 保留所有数据和 API 兼容性。
- 优先关闭有问题的 sprite、动态建议或纯净舞台子能力，不回滚核心聊天。

### 明确不做

- 不以“视觉已经接近原型”为由删除故障降级。
- 不在没有监控证据时一次性全量切换。
- 不让 UI 状态污染 Session 业务数据。
- 不以沉浸式页面完成为由下线标准 SessionRoom，也不把两个页面重新合并成条件布局。

## 9. 建议交付批次

| 批次 | 内容 | 预计风险 | 可见价值 |
| --- | --- | --- | --- |
| A | 独立路由、共享 runtime、舞台、HUD、背景、窄幅前端分页对白 | 中 | 高 |
| B | Composer 嵌入、全部日志、大抽屉、纯净舞台 | 中 | 高 |
| C | 通用多角色状态工作台、多字段关系展示 | 中 | 高 |
| D | typed relationship semantic（若需要） | 中 | 中 |
| E | sprite 绑定与舞台投影 | 高 | 高 |
| F | 动态行动建议（可选） | 高 | 中 |
| G | 移动端、无障碍、性能与灰度收尾 | 中 | 高 |

## 10. Definition of Done

独立沉浸式 Session 页面只有同时满足以下条件才算完成：

- 架构上拥有独立路由和 composition root；`SessionRoom.tsx` 不包含沉浸式 UI 分支或页面状态。
- 标准与沉浸式页面通过共享领域 runtime 复用 Session、history、stream/stop、角色绑定、Composer、模型、Context Preview、status/media/TTS 等能力，不存在两套业务实现。
- 视觉上以背景、角色和当前对白为中心。
- 功能上没有丢失标准 SessionRoom 已有的发送、停止、历史、状态、模型、TTS 和管理能力。
- 分页只发生在现有 parser/reducer 组装 canonical content 之后；不修改 SSE、不按 chunk 分页、不持久化页状态。
- 同一正文在不同视口允许得到不同页数，但视觉页重组后必须与原文逐字符一致。
- 数据上不引入章节假设，不改写 assistant 真源，不简化关系，不绕过既有服务边界。
- 2K / 4K 清晰，移动端可用，键盘和 reduced motion 完整。
- 所有新增媒体与高级投影都可以失败并降级，核心聊天仍可继续。
- 生产构建、双页面契约测试和视觉回归通过；关闭沉浸式入口即可回滚，标准页面无需改版或迁移。
