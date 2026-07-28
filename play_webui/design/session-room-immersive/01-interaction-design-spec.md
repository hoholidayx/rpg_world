# 沉浸式 Session Room 交互设计规范

> 状态：设计基线，2026-07-26 按 Story-owned 数据、Status v2、Plot Story、Memory/Dream、Media 和 YQ 压力样例校准。
>
> 本文描述独立沉浸式 Session 页面。标准 SessionRoom 继续存在，两者共享同一前端 Session 领域运行时；本文不改变正文、SSE、数据库或服务边界。

## 1. 产品目标

沉浸式页面把一次 Session 表现为可持续游玩的视觉舞台，同时保留标准页面已有的完整 RPG 能力：

- 背景、角色焦点、窄幅对白与自由行动构成默认舞台。
- 状态、剧情轨迹、故事记忆、图像与完整历史是按需打开的工作台，不常驻遮挡舞台。
- assistant 完整 `content` 是正文唯一真源；舞台分页只是浏览器内的临时视觉投影。
- 任何媒体、记忆、剧情调度或 TTS 故障都不能阻断基础历史、输入和正文流式返回。

本设计不把 Session 改造成固定章节游戏，不新增单值好感度，也不把静态原型中的演示状态当作后端事实。

## 2. 数据真源与身份

### 2.1 Story-owned 资源

Character、Lorebook 与 Story Status Table 直接属于 Story，不存在 Workspace 资产挂载层。稳定角色身份统一使用：

```ts
type StoryCharacterIdentity = {
  storyCharacterId: number
  displayName: string
}
```

Scene 的 `presentCharacters: string[]` 继续作为当前在场名称的展示真源。需要关联状态表、关系边或 sprite 时，必须使用 `storyCharacterId` 或服务端提供的类型化投影；不得依赖名称相等、表名或自然语言猜测。

Story Design 文档中的 `character-*` stable ref 是导入前引用，不是运行数据库的数字 `storyCharacterId`。导入器负责解析映射；静态原型不得伪造实际数据库 ID。

### 2.2 正文与 Turn

带 `<rp-narration>`、`<rp-character name="…">` 标签的 assistant `content` 是正文真源。现有 SSE parser/reducer 先组装 canonical content，沉浸式页面再做：

```text
canonical assistant content
→ parseAssistantTextSegments()
→ 容器测量
→ 临时 DialoguePage[]
```

视觉页码、字符边界和阅读位置只保存在当前页面内存，不写入 message metadata、数据库、SSE 或 localStorage。重新拼接全部视觉页必须逐字符等于原正文。

### 2.3 虚拟时间

持久化和运行时继续使用严格 `SceneTime`，例如 `2019 年 11 月 20 日 9 时`。玩家界面统一格式化为：

```text
2019年11月20日 09:00
```

界面使用上述紧凑格式。格式化逻辑应由共享前端 helper 提供，剧情轨迹、状态、日志和调度详情使用同一结果。

## 3. 页面信息架构

### 3.1 默认舞台

默认画面只保留：

- Session 标题与当前 Scene 摘要。
- “角色与状态”和“推演日志”两个一等入口。
- 舞台菜单。
- 背景与可用的角色舞台投影。
- 当前对白 Dock、AUTO、LOG、自由行动与已配置快捷回复。

不在顶部 HUD 常驻剧情轨迹、故事记忆、图像、模型选择、设置或关系摘要。关系表目前没有足够稳定的公开分类契约，舞台上不显示固定关系胶囊。

### 3.2 舞台菜单

舞台菜单按顺序提供：

1. 进入纯净舞台。
2. 剧情轨迹。
3. 故事与记忆。
4. 图像工作室。
5. 会话设置。

“角色与状态”已经是顶部一等入口，不在舞台菜单重复。会话设置继续承载字体、角色切换、RP Module、主模型、Dream 管理与删除 Session 等现有动作；推演日志首期不提供 decision/tool 隐藏开关。菜单只负责导航，不复制业务逻辑。

### 3.3 工作台互斥

状态、日志、剧情轨迹和故事记忆使用大抽屉；图像工作室可复用现有 Gallery 模态。任一时刻只打开一个主要工作台：

- 打开新工作台时关闭旧工作台和舞台菜单。
- 抽屉打开时 Dialogue Dock 不接受键盘推进。
- Esc 优先关闭最上层浮层，再退出纯净舞台。
- 关闭后焦点回到触发按钮。

## 4. 角色与 Opening 门禁

空 Session 或角色绑定失效时，沉浸式舞台不得绕过现有门禁。

1. 用户选择 Story 角色。
2. Story 有 0–3 个 Opening：
   - 0 个：仅确认角色。
   - 1 个：展示唯一 Opening 摘要并作为默认。
   - 2–3 个：继续选择故事起点。
3. 最终通过既有 `/role_bind <角色序号> [开局序号]` 原子提交。
4. 绑定成功且主历史为空时才写入 Opening。

门禁未完成时不允许普通正文写历史或调用 LLM。Opening 选择只决定第一条故事消息，不代表固定路线。

## 5. 舞台与视觉资源

### 5.1 VisualSpec 不等于 Asset

Story Design 的 Visual Catalog 只归档可生图规格，运行时不能直接把 VisualSpec 当图片。完整链路为：

```text
VisualSpec
→ 用户生成或上传
→ Media Library Asset
→ 显式绑定 Story Character / Stage
→ Stage Projection
```

沉浸式页面只消费 Play API 提供的运行时投影，不读取 DesignProject 文件，也不直接访问工作区图片。

### 5.2 舞台投影

未来稳定舞台契约使用 Story Character ID：

```ts
type StageCharacterProjection = {
  storyCharacterId: number
  displayName: string
  spriteAssetId: string | null
  poseKey: string | null
  placement: 'far-left' | 'left' | 'center' | 'right' | 'far-right'
  zIndex: number
  focused: boolean
}
```

投影来源优先级固定为 Session 舞台覆盖、Story 默认绑定、无 sprite 降级。该优先级是未来契约要求，当前原型只演示无 sprite 降级。

### 5.3 降级

- 有背景、无 sprite：使用半透明剪影、头像或首字母铭牌。
- sprite 加载失败：保持人物位置与姓名，不闪烁或随机换图。
- Media Service 不可用：隐藏媒体错误细节，保留 Scene、历史、Composer 和 Turn。
- speaker 无法稳定映射：不随机聚焦，回退到旁白焦点。

环境音不属于当前能力。第一版不显示可操作的环境音按钮；TTS 只播放已提交 assistant message，与环境音无关。

## 6. Dialogue Dock 与输入

### 6.1 对白分页

- Dock 在桌面只遮挡人物下肢，2K/4K 使用像素宽度上限。
- 点击当前页：逐字动画尚未完成时先补全；完成后再翻到下一视觉页。
- 视口、字号或方向变化后重新测量，以字符偏移恢复阅读位置。
- 流式期间只重算未读尾部，避免已读页面跳动。
- AUTO 遵循 reduced motion，并在需要用户输入、打开工作台或发生错误时停止。

### 6.2 自由行动与 QuickReply

自由行动始终是一等入口。StoryQuickReply 按实际数量 `0..N` 自适应：

- 0 个：只显示自由行动。
- 1–N 个：显示配置快捷输入，同时保留自由行动。
- 不固定三选项，不从 assistant 正文解析选项。

快捷回复和自由输入最终都走标准 Composer action、Context 门禁、角色门禁、stream/stop 与 commit 链路。当前历史没有可靠的“快捷回复来源”字段，因此日志统一显示为玩家输入。

### 6.3 已提交消息动作

完整日志中的消息继续支持复制、编辑、重试、删除、TTS 和“从此 Turn 派生”。TTS 仅在 assistant message 已提交并取得正数 `message_id` 后可用。

## 7. 角色与状态工作台

### 7.1 渐进披露顺序

工作台按以下层级组织：

1. 当前 Scene。
2. 在场角色与其他 Story 角色。
3. 常用当前状态。
4. 人物关系。
5. 项目/主线当前事实。
6. 默认折叠的详细状态。
7. 无法识别 semantic 的通用状态表。

Scene 独立于 normal 状态表；未绑定角色的 normal 表不得丢失，放入全局或其他状态。

角色摘要卡整卡可点击并原位展开。折叠态显示姓名、Story 身份、客观角色摘要、在场状态和稳定引用；展开态显示角色卡 `description`、别名、`storyCharacterId` 与其它服务端已返回的客观详情。不得在前端补写性格或根据在场名称猜数据库 ID。

### 7.2 类型化 semantic 与回退

当前 Status v2 的 `metadata` 是中立扩展字段。专用 UI 必须等待 Core/Play API 对以下保留 semantic 进行解析、校验和类型化投影：

- `relationship`
- `wardrobe`
- `physiology`
- `mainline-progress`

WebUI 不直接把任意 `metadata.category` 当稳定协议。semantic 缺失、未知或验证失败时，完整回退到通用 `key/value` 表，不隐藏数据、不报错。

### 7.3 人物关系

关系卡按状态表原始行展示任意数量的数值、枚举和文本字段，并保留“当前状态”等非数值摘要。当前公开契约不足以可靠生成关系端点或方向，因此第一期：

- 不显示“单向”“双向”徽标。
- 不按 row metadata 自动拆分方向分组。
- 不把表名、`pairKey` 或自然语言箭头解释为稳定关系图。
- 源 key 本身包含人物名或箭头时可以原样展示，但不据此生成额外语义。

不得自动计算总好感度、用一个数字替代全部字段、从数值推导关系阶段，或在缺失值时补零。舞台不显示固定关系 HUD；未来只有在 Core/Play API 提供明确、稳定的关系表分类与端点投影后再单独设计紧凑视图。

### 7.4 详细与私密状态

`normally-hidden` 和 `objective-private-state` 只决定默认折叠、说明文案和视觉层级，不是授权或数据脱敏规则：

- 服装的正常可见层可在常用状态中显示。
- normally-hidden 衣物进入“详细状态”折叠区。
- physiology 进入“详细状态”折叠区并标注为客观状态。
- 展开后按服务端返回值原样显示。

如果未来需要真正的玩家可见性控制，必须新增服务端权限投影，不能仅靠 CSS 隐藏。

### 7.5 Plot 与主线状态去重

- `mainline-progress` 状态表展示已成立的当前事实、项目阶段和结果。
- Plot Story 展示作者定义的轨迹、事件池和已发生注入。
- 状态工作台使用“项目与当前事实”，剧情工作台使用“剧情轨迹”，避免两个区域都命名为“主线进度”。

## 8. 剧情轨迹工作台

剧情轨迹直接复用 `SessionPlotStory`，不建立第二套剧情模型。

- 一级分为大纲和事件池。
- 默认开启服务端防剧透。
- 防剧透时只显示每条线首节点和已经注入的事件；隐藏内容不在前端获取后自行遮盖。
- 可见节点展示标题、描述、directive、suitabilityHint、调度时间、截止时间、启用状态、注入次数和 Turn。
- `triggered`/“已注入”只表示该 directive 已进入某一 Turn，不表示剧情完成或被语义验收。
- 不显示完成百分比，不把 outline 称为固定章节。
- 剧情轨迹是高密度阅读工作台，标题、说明、状态、时间、详情和防剧透占位文字的字号至少为原型上一版的 1.5 倍；移动端允许增加纵向滚动，不通过缩小文字维持同屏密度。

当前 `PlotInjection` 只有 `eventTitle` 和 `directive`。第一版日志只定位到对应 Turn，不通过标题匹配 Plot Story 节点。未来若需要精确跳转，必须先增加稳定 event/source ID。

## 9. 故事与记忆工作台

工作台复用现有查询与管理能力：

- 故事归纳：按来源 Turn 范围浏览 Summary。
- Story Memory：浏览剧情事实及 Evidence。
- Persistent Memory：浏览主 Agent 长期事实与 Evidence。
- Dream：查看状态并跳转管理 proposal。

Memory 是叙事历史和长期事实，不与当前状态表混用。Dream 或 Memory Service 失败时显示局部错误和重试，Dialogue Dock、历史和发送保持可用。

## 10. 推演日志

日志只有一个“全部记录”范围，按 Turn 使用现有 history-page 分页。第一期不提供类型筛选、隐藏开关或默认折叠；服务端实际公开的记录全部按发生顺序展开。允许出现的公开类型为：

- 玩家输入。
- assistant canonical 正文。
- Narrative Outcome。
- Plot Injection。
- 当前流式期间实际公开的 thinking 摘要。
- 后端允许公开的 tool call/result 摘要。
- 真实存在的错误、取消和系统通知。
- Plot Scheduler 各 lane 的公开决策记录。
- Status/Outcome 等公开决策记录。
- 每次公开 tool call 及其 result。

“全部显示”不等于绕过服务端边界。不得伪造未公开记录或完整内部推理链，也不得展示内部随机 sample、权重、密钥或来源诊断。thinking 不承诺跨刷新恢复；如果某类 decision/tool 尚未持久化，页面应明确标记为仅本轮可见，而不是静默补造。Plot Injection 与 Narrative Outcome 是独立卡片，不拼进 assistant 正文。

## 11. 纯净舞台、响应式与无障碍

### 11.1 纯净舞台

- 隐藏 HUD、Dock、菜单、工作台和通知。
- 隐藏层同时设置 `aria-hidden` 与 `inert`。
- 保留可发现的恢复按钮，并支持 H、Esc。
- 状态只驻留当前页面，不写 localStorage。

### 11.2 视口

- 1440×900：完整双栏舞台和窄幅 Dock。
- 2560×1440、3840×2160：限制内容最大宽度，角色与文字不无限放大。
- 390×844：单焦点角色、底部 Dock、近全屏 bottom sheet。
- 软键盘打开后输入和 stop 仍可见。

### 11.3 无障碍

- 工作台有正确 dialog、标题、焦点陷阱与关闭恢复。
- 逐字动画容器不直接充当频繁 `aria-live`；完整文本使用独立礼貌播报。
- 200% 字体下不裁切关键动作。
- reduced motion 关闭逐字、漂浮和大幅过渡。

## 12. YQ 压力样例

静态原型使用 `../YQDesignProject/design/current.json`（`currentRevision=r000028`）的人工摘录快照，但不建立运行时依赖。快照校准规模：

- 9 个 Story 角色。
- 8 张状态表。
- 3 组关系，其中一张关系表有 11 行。
- wardrobe、physiology 与 mainline-progress 详细状态。
- 3 条大纲、6 个池、15 个事件。
- 5 个 VisualSpec、0 个 runtime sprite 绑定。
- 0 个 QuickReply。
- 1 个 Opening，开场为 2019年11月6日。

原型必须清楚标注“VisualSpec 已归档，舞台 Asset 尚未绑定”，默认使用剪影/首字母降级。原型中的数值和注入历史只用于压力走查，不回写 YQ 项目。

## 13. 设计验收

- 页面不出现过时的角色挂载身份术语。
- 不出现可操作环境音、固定三分支或剧情完成百分比。
- 2019/2020 时间均以玩家友好格式显示。
- 零 QuickReply 时自由行动仍完整可用。
- 11 行关系原始数据、详细状态折叠和通用回退均可浏览，界面不生成单向/双向徽标。
- 9 张角色卡均可点击展开。
- 剧情轨迹正文与辅助文字至少比上一版放大 1.5 倍。
- 推演日志默认完整展开 decision、tool call/result 与其它公开记录。
- Plot 防剧透、已注入标记和 Turn 定位语义准确。
- 无 sprite、Media/Memory 局部失败时仍可继续正文。
- 标准和沉浸式页面最终共享相同的发送、停止、历史、门禁和提交行为。
