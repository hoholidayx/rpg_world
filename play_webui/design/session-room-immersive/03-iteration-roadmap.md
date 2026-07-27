# 独立沉浸式 Session 页面迭代路线图

> 原则：独立路由、共享 Session 前端领域运行时、标准页面长期可用、正文/SSE 不变、每阶段可独立验收和回滚。
>
> 2026-07-26 校准后路线：契约与原型 → 独立页面/runtime → 现有工作台接入 → 类型化状态投影 → sprite 舞台 → 可选建议与生产硬化。

## 1. 总体依赖

```text
Phase 0 设计契约与原型校准
  └─ Phase 1 独立页面与共享 Session Runtime
       └─ Phase 2 Plot / Memory / Media / 日志工作台接入
            └─ Phase 3 类型化 Status semantic
                 └─ Phase 4 Sprite 绑定与 Stage Projection
                      └─ Phase 5 可选行动建议与生产硬化
```

Phase 3 与 Phase 4 可以分别设计，但生产灰度前必须都具备明确的通用降级。动态行动建议不是上线沉浸式页面的前置条件。

## 2. Phase 0：设计契约与原型校准

### 目标

让三份文档、静态原型、当前生产能力和 Story Design 2.0 数据保持一致，消除实现人员需要自行猜测的语义。

### 交付

- 固定 Story-owned `storyCharacterId` 身份，不再使用角色挂载概念。
- 固定 HUD 与舞台菜单的信息架构：顶部保留“角色与状态”“推演日志”，菜单不重复状态入口，舞台不显示固定关系 HUD。
- 固定 Plot Story、防剧透、Plot Injection 和 mainline Status 的分工。
- 固定 Memory、Dream、Opening、派生、TTS 与 Media 的入口位置。
- 固定 Status semantic 的“服务端校验、前端渐进增强、通用回退”方向。
- 固定 VisualSpec → Asset → binding → Stage Projection 的链路。
- 用 YQ 复杂度快照更新静态原型。

### 验收

- 文档和原型不出现过时角色身份、可用环境音、固定三分支或剧情完成百分比。
- 时间显示为 `2019年…`，内部 `SceneTime` 约束说明仍准确。
- 原型覆盖 9 张可展开角色卡、8 状态表、一张 11 行关系表、3/6/15 Plot、5 VisualSpec、0 QuickReply。
- 关系卡不生成单向/双向徽标，剧情轨迹文字至少放大 1.5 倍。
- 推演日志不筛选、不折叠，完整展示原型提供的 decision 与 tool call/result。
- 无 sprite 时舞台明确降级，不把 VisualSpec 当 Asset。
- 原型不读写 YQDesignProject。

### 回滚

仅回滚设计目录，无生产影响。

## 3. Phase 1：独立页面与共享 Session Runtime

### 目标

建立独立沉浸式路由和组件树，同时让标准页面与沉浸式页面共享全部核心 Session 行为。

### 实现

- 按领域抽取 `SessionExperienceRuntime`：
  - Session/role/opening。
  - history window、消息动作和派生。
  - stream、requestId stop 与 Context 门禁。
  - Composer mode/style/model/quick replies。
  - status、plot、memory、media、TTS query/action。
- 标准 `SessionRoom` 与 `ImmersiveSessionExperience` 分别成为 runtime 消费者。
- 沉浸式页面交付 HUD、Stage、Dialogue Dock、Composer、工作台容器和纯净舞台。
- 新建 DialoguePager，只消费 reducer 组装后的 canonical content。
- 保持角色 → Opening 原子门禁。
- StoryQuickReply 按 0–N 渲染；自由行动始终存在。

### 不做

- 不修改 SSE。
- 不复制发送、停止、历史或角色绑定链路。
- 不接真实 sprite 绑定。
- 不直接解释 Status metadata。
- 不实现动态行动建议。

### 验收

- 两个页面可独立直达、刷新、返回。
- 普通发送、流式、停止、取消、Context 拒绝和角色失效行为一致。
- Opening 为 0、1、3 条时流程正确。
- 不同 SSE chunk 切分不改变最终分页。
- resize/字号变化后正文无丢失、重复或改写。
- 纯净舞台隐藏区域 inert，Esc/H 可恢复。
- Media 故障不阻断发送。

### 测试

- 共享 runtime 双消费者契约测试。
- DialoguePager 单元与属性测试。
- role/opening、Composer、stop、history-page 回归。
- 1440×900、2560×1440、3840×2160、390×844 视觉测试。
- 键盘、200% 字号和 reduced motion。
- Play WebUI build。

### 回滚

隐藏独立路由入口；标准 SessionRoom 保持可用。按领域回退 runtime 抽取，禁止复制第二套链路作为临时补丁。

## 4. Phase 2：现有工作台接入

### 目标

把已经存在的 Session 能力完整带入沉浸式体验，不新增后端模型。

### 实现

- 顶部只保留“角色与状态”“推演日志”。
- 舞台菜单接入：
  - 剧情轨迹。
  - 故事与记忆。
  - 图像工作室。
  - 会话设置。
- 剧情轨迹复用 `SessionPlotStory`：
  - 服务端防剧透。
  - outlines/pools。
  - 调度/截止、禁用、注入次数和 Turn。
- 日志复用 history-page，并加入现有 Narrative Outcome、Plot Injection，以及服务端实际公开的 decision/tool trace；第一期不提供筛选、隐藏或默认折叠。
- 故事与记忆复用 Summary、Story Memory、Persistent Memory、Evidence 和 Dream 管理入口。
- 图像工作室复用 VisualBrief、userPrompt、编辑重试/重抽和 Library。
- 日志消息菜单保留复制、编辑、重试、删除、TTS 和派生。
- 增加共享玩家友好 SceneTime formatter。

### 明确语义

- Plot 注入不等于剧情完成。
- mainline Status 是当前事实，Plot Story 是作者轨迹。
- Plot Injection 第一版只按 Turn 定位，不按标题反向匹配事件。
- TTS 只使用已提交 assistant message ID。
- Memory/Dream/Media/Plot 故障局部展示。

### 验收

- 防剧透开启时，浏览器从响应中拿不到应隐藏的事件详情。
- 可见 Plot 节点能跳到已有 last injection Turn。
- 日志中 Outcome 与 Plot Injection 各自独立，不污染正文。
- 2019/2020 时间显示不带序数“第”。
- Memory/Dream/Media 任一失败，历史与 Composer 仍可用。
- 从历史 Turn 派生、编辑、重试、删除和 TTS 不丢失。

### 测试

- SessionPlotStory 查询与防剧透合约。
- history Plot Injection 映射。
- SceneTime formatter。
- 各工作台 loading/empty/error。
- history 分页与 Turn 跳转。
- Media/TTS/Memory 故障隔离。
- Play WebUI build。

### 回滚

逐个隐藏菜单入口，标准页面对应能力继续可用。共享 API 和数据不迁移。

## 5. Phase 3：类型化 Status semantic

### 目标

在不破坏通用 Status v2 的前提下，为常见语义提供可靠的渐进增强。

### 实现

- 在 `rpg_core` 定义保留 semantic parser 与 typed contracts：
  - relationship。
  - wardrobe。
  - physiology。
  - mainline-progress。
- Play API 输出解析后的只读投影和可选非阻断诊断。
- `rpg_data` 继续保存原始 metadata/document，不决定展示。
- WebUI 根据投影选择专用卡，任何缺失或错误退回通用 key/value。
- 状态工作台按 Scene、角色、常用状态、关系、项目事实、详细状态、其他表渐进披露。
- normally-hidden / objective-private-state 默认折叠并显示说明，不当作权限。
- 关系第一期只确认表类型并保留任意多维度、文本摘要与独立 scale；现有契约不足以生成端点或方向视图。

### 不做

- 不创建单值 Relationship 表。
- 不计算总好感度或自动关系阶段。
- 不按表名猜 semantic。
- 不通过 CSS 实现权限。
- 不让 WebUI 直接修改运行时状态。

### 验收

- YQ 三张关系表均正确投影，其中一张完整显示 11 行原始语义，不显示单向/双向徽标。
- 非数值、缺失范围、未知 category 和未知版本均安全回退。
- wardrobe 可见层与详细层分组正确。
- physiology 默认折叠但可浏览。
- mainline Status 不与 Plot Story 重复命名或重复表示完成度。
- 任意旧 Story 无迁移即可继续显示通用表。

### 测试

- Core parser：有效、缺字段、未知版本、非法范围、非法角色引用。
- Play API typed contract 与 generic fallback。
- WebUI 专用卡与通用卡。
- 11 行、多字段、长文本和任意字符串 value。
- 角色删除/改名/绑定失效。
- Play WebUI build。

### 回滚

关闭专用投影后全部退回通用 Status 卡；不改原始 document，不做数据回滚。

## 6. Phase 4：Sprite 绑定与 Stage Projection

### 目标

让多角色立绘舞台建立在真实 Media Asset 和稳定 Story Character 身份上。

### 实现

- 为 Story Character 建立默认 sprite Asset 绑定。
- 可选增加 Session 舞台覆盖。
- 提供只读 `StageCharacterProjection`：
  - storyCharacterId。
  - displayName。
  - spriteAssetId。
  - poseKey。
  - placement。
  - zIndex。
  - focused。
- 明确优先级：Session override > Story default > 降级。
- Media Application Service 负责绑定引用保护、Asset 删除门禁和缺失处理。
- Play WebUI 通过 Play API/Media Client 获取授权资源。
- 支持 0/1/2/3+ 角色的确定性布局与 speaker focus。

### 不做

- 不从 VisualSpec 直接显示图片。
- 不按角色名匹配 sprite。
- 不把 sprite/pose/placement 写进正文或消息 metadata。
- 不让 Play API 直接读工作区文件。

### 验收

- 同名角色、角色改名不会拿错立绘。
- 删除被绑定 Asset 时被正确阻止或先解除引用。
- 无 sprite、加载失败和 Media Service 故障时使用降级舞台。
- 2–5 名角色不遮挡关键面部与主要对白区域。
- speaker 无 ID 映射时不随机聚焦。
- 聊天链路不依赖 sprite 成功。

### 测试

- 绑定 CRUD、归属校验和引用保护。
- Stage Projection API 合约。
- 同名、改名、删除、失效 Asset。
- 多角色站位视觉回归。
- 背景/sprite 预加载、闪烁和内存上限。
- Play WebUI build。

### 回滚

关闭 sprite layer，继续使用背景、头像或剪影。绑定和投影是附加能力，不迁移历史。

## 7. Phase 5：可选行动建议与生产硬化

### 目标

在核心体验稳定后，决定是否增加 turn-scoped 动态行动建议，并完成性能、无障碍、移动端和双页面灰度。

### 动态建议启动条件

- 产品明确区分 StoryQuickReply 与动态建议。
- 明确生成服务、成本、延迟和故障预算。
- 明确是否持久化及刷新恢复语义。
- 自由行动始终可用。
- 不泄露内部 reasoning。

建议最小结构：

```ts
type TurnSuggestion = {
  id: string
  label: string
  prompt: string
  mode: 'ic' | 'ooc' | 'gm'
}
```

建议失败、为空或超时直接隐藏；点击后仍走标准 Composer 和门禁。不得把建议写进 assistant 正文再解析。

### 生产硬化

- 大历史继续使用 turn 分页和窗口缓存。
- DialoguePager 只重算未读尾部。
- 背景与 sprite 做尺寸适配、预加载和内存上限。
- 移动端单焦点角色、bottom sheet 和软键盘适配。
- 完整键盘、焦点、颜色对比、200% 字号与 reduced motion。
- 内部环境先开放独立路由，再灰度入口。
- 对比两页面发送成功率、stop 成功率、首屏稳定时间和局部服务错误率。

### 验收

- 两个页面核心行为通过同一契约测试。
- 标准页面无需布局切换即可继续使用。
- 动态建议关闭后回到 QuickReply + 自由行动。
- 媒体和工作台错误不影响正文成功率。
- 390×844 与 4K 均无关键操作不可达。

### 回滚

关闭建议能力和沉浸式入口；不迁移或改写历史，标准页面继续服务。

## 8. 全程架构红线

- 不修改正文 SSE 来服务视觉分页。
- 不把沉浸式页面做成 `SessionRoom.tsx` 的条件布局。
- 不复制 Agent/Session/Composer 业务链路。
- 不让 Play WebUI 直接解释未校验 metadata。
- 不把 Scene 人名数组当持久身份。
- 不把 VisualSpec 当 runtime Asset。
- 不把详细状态折叠当权限。
- 不恢复环境音假能力。
- 不把 Plot 注入解释为剧情完成。
