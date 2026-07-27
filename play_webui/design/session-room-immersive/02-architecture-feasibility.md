# 沉浸式 Session Room 架构可行性审计

> 审计基线：2026-07-26 当前仓库，以及 `../YQDesignProject/design/current.json` 的 Story Design 2.0 数据。
>
> 本文只校准设计与后续接口方向；本次设计稿更新不修改生产 API、数据库、SSE 或运行时。

## 1. 结论

独立沉浸式页面在现有架构上可行，但必须建立在共享 Session 前端领域运行时之上。当前能力可分为三类：

1. 已有能力，只需在新页面复用：发送/停止、角色与 Opening、状态、Plot Story、Memory/Dream、Media、TTS、派生与历史动作。
2. 需要前端视图改造：DialoguePager、舞台 HUD、大抽屉、纯净舞台和响应式布局。
3. 尚缺稳定契约：Status semantic 类型化投影、完整 decision/tool trace、角色 sprite 绑定与 Stage Projection、Plot Injection 精确事件定位、动态行动建议。

原设计中角色挂载身份、环境音、固定三选项、线索/待办专用卡片和完整内部日志等假设已不再成立。

## 2. 当前能力矩阵

| 能力 | 当前状态 | 沉浸式落法 |
| --- | --- | --- |
| canonical assistant content | 已具备 | 复用现有 parser/reducer，视图层二次分页 |
| stream / requestId stop | 已具备 | 两个页面共享同一 runtime action |
| 角色绑定与 0–3 Opening | 已具备 | 复用原子 `/role_bind` 门禁 |
| StoryQuickReply | 已具备 | 按 0–N 自适应；YQ 为 0 |
| 动态行动建议 | 无契约 | 独立后续能力，不解析正文 |
| Scene / normal Status | 已具备 | 复用查询，重排为渐进披露工作台 |
| Status metadata | 已传输，中立扩展 | 专用卡前先增加 Core/API 校验投影 |
| Plot Story 防剧透 | 已具备 | 复用 `SessionPlotStory` 抽屉 |
| Plot Injection 历史卡 | 已具备 | 日志按 Turn 展示，不猜 event ID |
| Summary / Story Memory | 已具备 | 复用故事与记忆面板 |
| Persistent Memory / Dream | 已具备 | 复用查询、Evidence 与管理入口 |
| 从 Turn 派生 Session | 已具备 | 保留在日志消息动作中 |
| Media Brief / 编辑重试 | 已具备 | 从舞台菜单进入图像工作室 |
| `character_sprite` 媒体类型 | 已具备 | 不能替代角色绑定和舞台投影 |
| Visual Catalog | Design archive-only | 不作为运行时图片资源 |
| TTS | 已具备 | 仅已提交 assistant `message_id` |
| 环境音 | 无业务链路 | 不展示可用控件 |
| 纯净舞台 | 需前端改造 | 临时页面状态，隐藏层 inert |

## 3. Story-owned 身份校准

Character、Lorebook、Status Table 已直接归 Story。前后端公开契约已有 `storyCharacterId`，后续设计统一依赖该 ID：

- 状态表绑定使用 `storyCharacterId`。
- 未来若新增明确的关系端点投影，双方必须使用 `storyCharacterId`。
- Stage Projection 使用 `storyCharacterId`。
- 角色改名不改变绑定。

Scene 当前仍返回 `presentCharacters: string[]`。它足以展示“在场人物”，但不足以做稳定 sprite 或关系关联。短期角色列表可沿用现有名称匹配做“在场”视觉提示；任何具有持久影响的绑定必须来自服务端 ID 投影。

YQ 当前仍是 Story Design 数据，其中 `character-*` 是设计 stable ref，不是已导入数据库的 `storyCharacterId`。未来同步/导入过程必须产生显式 ref → ID 映射；原型只展示 stable ref 和“ID 待导入”，不假装已有运行时数字 ID。

## 4. Status semantic 契约

### 4.1 现状

Status v2 已支持：

```ts
type StatusRow = {
  key: string
  value: string
  runtimeKeyLocked: boolean
  updateRule: string
  metadata: Record<string, unknown>
}

type StatusTable = {
  storyCharacterId?: number | null
  metadata: Record<string, unknown>
  rows: StatusRow[]
}
```

YQ 已使用 `metadata.category` 表达 relationship、wardrobe、physiology 和 mainline-progress，但 authoring contract 仍把 metadata 定义为中立扩展字段。WebUI 直接解释它会形成未经校验的隐式 API。

### 4.2 推荐边界

由 `rpg_core` 定义纯业务解析器和 typed contract，Play API 只序列化结果，WebUI 只消费已验证投影。数据层继续原样保存 metadata，不决定 UI 行为。

示意：

```ts
type StatusSemanticProjection =
  | RelationshipStatusProjection
  | WardrobeStatusProjection
  | PhysiologyStatusProjection
  | MainlineStatusProjection
  | { kind: 'generic' }
```

解析规则必须满足：

- 只识别明确保留的 category/version。
- 校验该 semantic 已定义的 version、range、visibility 等结构。
- 无效数据返回 generic 并附非阻断诊断。
- 不修改或补全原始 row value。
- 不把 `normally-hidden`、`objective-private-state` 当权限。
- relationship 第一期只确认“这是关系状态表”并投影原始行，不从现有 metadata 推导端点、单向或双向。

该契约属于后续生产阶段，本次只在设计和路线图中冻结。

### 4.3 YQ 压力点

- 三张关系表分别有 6、6、11 行；部分源 row key/metadata 带有方向样式，但当前没有经过 Core/Play API 类型化确认的端点契约。
- 数值采用 `N/100`，但通用 Status value 仍可为任意字符串。
- wardrobe 同时有 normally-visible 与 normally-hidden。
- physiology 是 objective-private-state。
- mainline-progress 的行会引用 Plot Pool，但只表达当前事实。

专用 UI 必须能安全处理以上数据，同时让任意其他 Story 回退为通用表。第一期关系卡只展示源表名与原始 key/value，不生成“单向/双向”徽标或方向分组；舞台也不显示关系 HUD。

## 5. Plot Story 与历史

### 5.1 已有只读投影

`SessionPlotStory` 已提供：

- outlines / pools。
- 服务端计算的 `revealed`。
- event/source 注入次数。
- last injection Turn。
- event detail、dispatch mode、scheduled/deadline、enabled 和 session disabled。

沉浸式页面应直接复用这一投影，不请求完整 Story Plot 后在浏览器自行防剧透。

### 5.2 语义边界

- `triggered` 表示事件 directive 已注入当前 Turn。
- 它不表示剧情已经写完、目标达成或章节完成。
- Plot Story 是作者轨迹；mainline Status 是当前事实。
- outline 是线性节点链，但产品界面不新增章节完成率。

### 5.3 Plot Injection

当前历史契约为：

```ts
type PlotInjection = {
  eventTitle: string
  directive: string
}
```

因此第一版只支持：

- 在 Turn 内显示注入卡。
- 从 Plot Story 的可见节点跳到 `lastSourceInjectionTurnId`。

不支持从日志卡反向精确定位事件，因为标题不是稳定键。本轮不扩展 API；若以后确认需要，应增加稳定 `eventId + sourceKind + sourceId`，而不是前端标题匹配。

## 6. Story、Memory、Dream 与派生

现有 `SessionStoryPanel` 已覆盖 Summary、Story Memory、Persistent Memory 与 Evidence；Dream 通过独立管理页工作。沉浸式页面只需复用 query/action，不新增记忆模型。

边界固定：

- Status 表示每轮可见、可更新的当前事实。
- Memory 表示按时间积累的叙事事实。
- Summary 是来源 Turn 范围的归纳。
- Dream Proposal 由用户显式管理。
- 任一记忆服务失败只影响对应面板。

SessionTimeline 已支持从指定 Turn 派生。沉浸式日志必须保留该动作及复制、编辑、重试、删除和 TTS，不能因视觉简化而丢失业务能力。

## 7. Media、VisualSpec 与 Stage Projection

### 7.1 已有能力

Media 已支持 VisualBrief、`userPrompt`、编辑后重试/重抽和 `character_sprite` Library 类型。它仍没有 Story Character 到 sprite Asset 的稳定绑定。

YQ 的 5 个 VisualSpec 是 DesignProject 归档资料，不能被 Session 直接读取或显示。

### 7.2 缺失契约

未来最小只读投影：

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

还需配套：

- Story 默认 sprite 绑定。
- 可选 Session 舞台覆盖。
- Asset 引用保护和解除绑定行为。
- 0/1/2/3+ 角色的确定性站位。
- speaker 无法映射时的安全降级。

Play WebUI 仍通过 Play API → Media Client 读取 Asset；Play API 不直接读取工作区图片文件。该契约不写入消息正文、message metadata 或 localStorage。

## 8. 共享前端领域运行时

### 8.1 目标组件边界

```text
SessionExperienceRuntime
├─ session / role / opening
├─ history window / timeline actions / derivation
├─ stream / stop / context gate
├─ composer / mode / style / model
├─ status / plot story / memory
├─ media / TTS
└─ shared typed selectors

StandardSessionExperience
└─ 当前标准布局

ImmersiveSessionExperience
├─ ImmersiveStage
├─ ImmersiveHud
├─ ActiveDialogueDock + DialoguePager
├─ WorldStateDrawer
├─ SessionTraceDrawer
├─ PlotStoryDrawer
├─ StoryMemoryDrawer
└─ CinematicModeController
```

共享运行时不是单一 God hook，也不是 Next.js middleware。按业务 owner 拆 provider/controller/hook，两个页面消费相同 typed actions。

### 8.2 不变量

- 不复制 stream、stop、history、role binding、Composer 或 commit 逻辑。
- 不修改正文 SSE event、payload、顺序或 DONE 语义。
- 不把 DialoguePager 状态混入 history-page。
- 标准 SessionRoom 不出现沉浸式布局条件分支。
- 两个页面的角色门禁、Context 门禁和错误码行为一致。

## 9. DialoguePager 可行性

浏览器可通过隐藏测量容器或 Range 测量完成前端分页。实现需覆盖：

- 中文标点、引号、换行、emoji 和无标点长串。
- narration / character 段落边界。
- 字体加载、字号、行高、容器 resize 和方向变化。
- 流式 canonical 前缀增长。
- 200% 字号与 reduced motion。

分页缓存只在内存中，以 message identity、canonical content hash、容器尺寸和字体参数为键。重新测量时以字符偏移而非旧页码恢复位置。

## 10. 日志公开边界

可展示的数据必须来自真实 history/SSE 映射：

- user / assistant。
- Narrative Outcome。
- Plot Injection。
- 当前公开 thinking 摘要。
- 允许公开的 tool 摘要。
- 实际错误、取消与通知。

目标交互不做客户端筛选或折叠：服务端提供的 Plot/Status/Outcome decision、tool call 与 tool result 全部按顺序展示。现有 history/SSE 未必能在刷新后完整恢复每一类记录，因此生产接入前需要补齐只读 trace 投影或明确“仅本轮可见”的生命周期；WebUI 不从正文、标题或状态差异反推日志。

静态原型中的 decision/tool 条目是目标契约样例，不宣称来自 YQ `current.json` 的真实运行账本。不得模拟“上下文同步事件”、未公开诊断或内部推理链；内部随机 sample、权重、密钥和来源诊断仍不进入玩家界面。

## 11. 故障与安全边界

| 故障 | 页面行为 |
| --- | --- |
| Media / sprite 失败 | 降级头像或剪影，聊天继续 |
| Plot Story 失败 | 工作台局部错误，聊天继续 |
| Memory / Dream 失败 | 对应 tab 局部错误，聊天继续 |
| TTS 失败 | 消息播放动作显示重试，不影响正文 |
| Context 门禁拒绝 | Composer 展示既有错误，命令仍按原规则 |
| stream 取消 | 只有收到 `cancelled` 才显示已停止 |
| Status semantic 无效 | 通用 key/value 回退 |

“详细状态折叠”不是安全边界。真正需要权限或脱敏时，必须由服务端决定字段是否出现在响应中。

## 12. 原型约束

静态原型内嵌 YQ `r000028` 摘录快照，不读取 `../YQDesignProject`，也不回写任何数据。它只验证：

- 9 角色的检索与分组。
- 9 张角色摘要卡的点击展开。
- 3 组关系和一张 11 行关系表，不推导单向/双向。
- wardrobe / physiology 折叠。
- mainline Status 与 Plot Story 分区。
- 3 outline、6 pool、15 event 的浏览密度。
- 防剧透占位。
- 至少放大 1.5 倍的剧情轨迹文字密度。
- 默认完整展开的 decision/tool trace 示例。
- 0 QuickReply。
- VisualSpec 存在但 sprite 未绑定的降级舞台。

原型不模拟真实 API、LLM、状态写入、关系数值变更、生图任务或 Dream apply。

## 13. 风险与验证

主要风险：

- 共享 runtime 抽取不完整导致两个页面行为分叉。
- 前端直接解释 metadata 形成隐式协议。
- Scene 名称匹配被误用为持久角色身份。
- VisualSpec 与 Asset 概念混淆。
- DialoguePager 在流式或 resize 时丢字/重复。
- 大工作台在移动端遮挡输入或产生隐藏焦点。

验证重点：

- 两个页面的发送、stop、角色门禁和 history 契约测试。
- Status semantic 有效、无效、未知和通用回退。
- 11 行关系表与任意字符串 value，不依赖方向推导。
- Plot 防剧透由服务端投影控制。
- 不同 SSE chunk 切分得到相同最终分页。
- 1440×900、2560×1440、3840×2160、390×844。
- 200% 字号、键盘、焦点陷阱和 reduced motion。
