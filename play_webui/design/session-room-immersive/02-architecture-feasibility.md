# 独立沉浸式 Session 页面架构可实现性审计

> 审计对象：当前仓库生产代码与本目录静态原型  
> 目标：逐项区分可直接实现、需要前端改造、需要新契约以及当前不应实现的内容

## 1. 结论摘要

沉浸式体验可以在不重写核心会话链路、也不扩张 `SessionRoom.tsx` 的前提下落地。第一阶段新增独立沉浸式路由与页面，并从现有 SessionRoom 抽取可共享的前端领域运行时；标准页面与沉浸式页面分别组合 UI，同时复用 Session 数据、history window、stream/stop、角色绑定、Composer actions、状态表、背景媒体、TTS、Context Preview 和模型选择。

沉浸分页不需要、也不得修改 SSE 协议。现有 parser/reducer 继续组装 canonical assistant content，沉浸式页面再根据实际视图尺寸和分页策略做纯前端视觉二次分页。

真正缺失的核心数据只有两类：

1. **角色舞台投影**：稳定的角色 mount ID、全身立绘 Asset、姿势、站位、层级和焦点。
2. **可选的动态行动建议**：如果产品需要每 turn 由模型生成 Galgame 分支，需要独立的 turn-scoped 结构化契约。

人物关系不需要被设计成新的单值实体。现有通用状态表已能保存多个数字和文本字段；缺口只是“如何显式识别并投影为关系卡”，不能靠表名猜测。

## 2. 判定等级

| 结论 | 含义 |
| --- | --- |
| 可直接实现 | 现有数据和 API 足够，主要是复用或样式调整。 |
| 前端改造 | 不需要新后端数据，但要拆组件、增加 UI 状态或展示投影。 |
| 部分实现 | 有可靠降级方案，但无法完全达到原型效果。 |
| 需要数据契约 | 当前没有稳定真源，必须先完成类型、API 和持久/临时语义设计。 |
| 当前不应实现 | 会违反现有架构、真源或安全边界，或产品语义不存在。 |

## 3. 当前生产架构基线

### 3.1 标准 SessionRoom 现状与抽取边界

- `play_webui/src/features/session/SessionRoom.tsx`
  - 当前桌面是左栏、拖拽柄、中央体验区、拖拽柄、右栏的五列网格。
  - 中央已经组合 `SessionMediaBackground`、`SessionTimeline`、`SessionComposer`。
  - 左右栏已支持折叠、移动端面板和临时 `SessionRailDrawer`。
  - 它是标准 SessionRoom 的页面组合根，也是共享业务逻辑的抽取来源；它不是沉浸式页面的 composition root，不应引入沉浸式组件或页面级状态。
- `play_webui/src/features/session/hooks/useSessionRoomLayout.ts`
  - 左栏默认 300px，范围 260–460px。
  - 右栏默认 340px，范围 280–500px。
  - 折叠后 72px。
- `play_webui/src/stores/sessionUiStore.ts`
  - 字体缩放范围 90%–200%，默认 125%。
  - 已有 thinking/tool 显隐偏好并写入 localStorage。

### 3.2 历史与流式事件

- `play_webui/src/features/session/hooks/useSessionHistoryWindow.ts`
  - 已支持按 turn 分页、前后加载、窗口缓存和跳到最新。
- `play_webui/src/features/session/SessionTimeline.tsx`
  - 已支持 user、assistant、tool、system、thinking、outcome、error。
  - 已支持复制、编辑、重试、删除、TTS 和 usage 详情。
- `play_webui/src/features/session/sessionTimelineMessages.ts`
  - 持久历史映射的角色为 system、user、assistant、tool。
  - Outcome 由 turn 的独立字段映射为时间线卡片。
  - 当前 assistant 历史说话人仍统一为“叙事者”。
- `play_webui/src/types/stream.ts` 与 `play_webui/src/features/session/hooks/useSessionStreamTurn.ts`
  - SSE 已有 `thinking_delta`、`tool_call`、`tool_result`、`text_delta`、`turn_completed`。
  - thinking/tool 可以在当前流式 turn 中显示。
  - thinking 没有稳定持久历史契约。
  - 沉浸式页面必须复用现有事件类型、payload、parser/reducer 和完成语义，不增加分页事件或字段。

### 3.3 正文结构

- `play_webui/src/features/session/assistantTextSegments.ts`
  - 已能解析 `<rp-narration>` 和 `<rp-character name="…">`。
  - 解析不完整标签时有 raw fallback。
- 带标签全文仍是 assistant `content` 真源；沉浸式分页必须建立在 parser/reducer 已组装的 canonical content 及其解析结果之上，不能改变正文或按 SSE chunk 分页。

分页链路固定为：

```text
现有 SSE 事件
→ 现有 parser/reducer 组装 canonical assistant content
→ parseAssistantTextSegments()
→ 前端视图测量 + 沉浸分页策略
→ 临时视觉页面
```

`history-page` 是服务端按 turn 加载历史窗口；沉浸对白分页是前端对已加载正文的视觉二次分页。二者名称相近但不共享协议、参数或持久状态。

### 3.4 Composer 与业务控制

- `play_webui/src/features/session/SessionComposer.tsx`
  - 已有 IC、OOC、GM、命令、叙事风格、主模型、Context Preview、发送和停止。
  - `StoryQuickReply` 已存在，但属于 story 配置，并通过长按发送按钮打开。
- `play_webui/src/features/session/hooks/useSessionStreamTurn.ts`
  - 停止生成已按 requestId 调用 stop API，并以服务端结果决定 cancelled 状态。

### 3.5 状态表与角色

- `play_webui/src/types/statusTables.ts`
  - 状态表是通用 `rows[].key/value`，value 为字符串。
  - 支持 `scene | normal`。
  - 字段更新频率支持 `realtime | event_driven | deferred | manual`。
- `play_webui/src/features/session/SessionStatusRail.tsx`
  - 已支持多张 scene 表和 normal 表。
  - 已支持角色绑定状态表、玩家角色标识、在场角色和 normal 表 pin。
- `play_webui/src/features/session/hooks/usePinnedStatusTables.ts`
  - pin 偏好按 session 存在当前浏览器。
- `play_webui/src/types/scene.ts`
  - scene 只有 attrs、time、location、presentCharacters 名称数组和 mood。
  - `presentCharacters` 不是稳定角色 mount ID。

### 3.6 背景与媒体

- `play_webui/src/features/session/SessionMediaBackground.tsx`
  - 已支持 Session 背景、预加载和交叉淡入。
  - 当前固定叠加 `bg-slate-950/55`。
- `play_webui/src/features/session/hooks/useSessionMedia.ts`
  - 已有 Gallery、手动/自动背景和后台评估。
- `play_webui/src/types/media.ts`
  - 媒体类型中已有 `character_sprite`。
  - 目前没有角色与 sprite 的稳定绑定，也没有 pose、placement 或 focus 数据。

## 4. 能力逐项审计

| 原型能力 | 结论 | 当前证据 | 缺口与修改建议 |
| --- | --- | --- | --- |
| 独立沉浸式页面 | 前端改造 | 会话能力已有 hooks、store、API client 和组件实现。 | 新增独立路由/page；把领域能力从标准 SessionRoom 组合中抽为共享 runtime，两个页面各自组合 UI。 |
| 全屏 Session 背景 | 可直接实现 | `SessionMediaBackground` 已读取当前背景并交叉淡入。 | 将背景置于独立沉浸式页面的舞台最底层；保留媒体故障隔离。 |
| 更轻的舞台遮罩 | 前端改造 | 当前遮罩固定为 `bg-slate-950/55`。 | 增加由舞台状态控制的遮罩强度；纯净舞台使用更轻遮罩，但保证文字模式对比度。 |
| 双立绘 / 多立绘 | 部分实现 | 只有角色头像 `avatarUrl`；媒体 catalog 虽有 `character_sprite`，却无绑定。 | 第一阶段可用头像卡或剪影降级；完整全身立绘需要舞台投影契约。 |
| 当前说话人焦点 | 部分实现 | `parseAssistantTextSegments()` 可得到角色名称。 | 名称不能稳定关联角色或 sprite；需 mount ID 映射。匹配失败必须显示通用说话人，不猜 ID。 |
| 立绘站位、层级、姿势 | 需要数据契约 | 当前没有 placement、zIndex、pose。 | 定义只读舞台投影；不能写进消息 metadata。 |
| 当前场景 HUD | 可直接实现 | 已有 `scene` API 与 Scene 类型。 | 从 time、location、mood、attrs 派生；空值有降级，scene 仍保持专用实时状态。 |
| 无章节、自由推演标题 | 可直接实现 | Session 本身以 title、turn 和 scene 运行，没有章节字段。 | 移除 UI 中 story ID/章节/支线视觉语义，使用“自由推演”“当前场景”“Turn”。 |
| 窄幅对白框 | 前端改造 | 当前 Timeline 为长滚动列；完整正文和解析器已存在。 | 新建 Active Dialogue 投影，设置 2K/4K 宽度上限，不能删除 Timeline 数据。 |
| 对白自然换行 | 可直接实现 | 文本本身完整，CSS 可换行。 | 使用可测量容器与 `white-space: pre-wrap`/正常中文断行；无标点长文本强制断行。 |
| 多次“继续阅读” | 前端改造 | `assistantTextSegments` 提供段落真源。 | 在前端按容器宽高、字体、行高、段落与策略二次分页；页状态只驻留内存；不得改 SSE、正文或 metadata。 |
| 逐字显示 / AUTO | 前端改造 | SSE 已逐步提供文本；原型已验证逐字和 AUTO。 | 现有 reducer 先组装 canonical 前缀，再做视图投影；不按 chunk 分页，已读页稳定、只重算未读尾部；支持 reduced motion。 |
| 自由行动 | 可直接实现 | `SessionComposer` 已完整覆盖输入、mode、命令、发送。 | 将 Composer 视觉嵌入 Dialogue Dock，保留原 hooks 和 API。 |
| Story 快捷回复 | 可直接实现 | `StoryQuickReply` 已由 Composer 使用。 | 可改为 Galgame 式选项外观，但必须标明其是配置快捷输入。 |
| 每 turn 动态三分支 | 需要数据契约 | 当前无 suggestions 字段；quick reply 不是动态结果。 | 需要结构化 turn-scoped suggestion；不能从 assistant 正文猜选项。 |
| 全部推演日志单 tab | 前端改造 | Timeline 已有多类型消息和 history-page。 | 建立 `SessionTraceDrawer`，固定一个“全部”视图，复用分页和现有消息动作。 |
| 历史对白 | 可直接实现 | system/user/assistant/tool 持久历史已映射。 | 使用完整历史；舞台分页不改变日志正文。 |
| 历史 Narrative Outcome | 可直接实现 | turn outcome 已映射独立卡片。 | 继续按 turn 排序，不把 Outcome 拼进 assistant 正文。 |
| 当前 turn thinking | 可直接实现 | `thinking_delta` 已生成运行期 thinking item。 | 文案使用“思考摘要/诊断”，遵循 showThinking 开关。 |
| 跨刷新完整 thinking | 当前不应实现 | history 角色无 thinking 持久契约。 | 若产品确有审计需求，另行定义可公开摘要与保留策略；不得把内部 CoT 当产品日志。 |
| tool call / result | 可直接实现 | SSE 和历史映射支持 tool。 | 默认摘要，详情可展开；敏感或内部字段继续由后端公开边界决定。 |
| 预设决策与自由输入的历史区分 | 部分实现 | 两者最终都是 user message；当前没有来源字段。 | 第一阶段统一显示“玩家输入”；若要区分，需要新的明确来源契约。 |
| 大尺寸状态工作台 | 前端改造 | `SessionRailDrawer` 现为 `max-w-[520px]`。 | 桌面改为约 66vw、设 1200px 左右上限；移动端保留近全屏 bottom sheet；复用焦点管理。 |
| 多角色卡 | 可直接实现 | `SessionStatusRail` 已迭代角色并区分玩家/在场状态。 | 重新编排为工作台网格；不要假定只有一个 NPC。 |
| 每角色多张状态表 | 可直接实现 | normal 表可绑定角色，角色卡会列出绑定表。 | 工作台按角色分组，保留通用表回退和 pin。 |
| 多组人物关系 | 部分实现 | 通用 KV 状态表可表达多个字段，但没有 Relationship 实体或关系表标识。 | 无标识时按普通表显示；专用关系网络需要类型化投影标识。 |
| 关系的多个数字字段 | 可直接实现 | `StatusRow.value` 是字符串，行数量不限于一个。 | 一张关系表使用多行展示信任、亲密、依赖等；不得压缩为单一总分。 |
| 关系的阶段与文本描述 | 可直接实现 | `StatusRow.value` 可保存任意字符串。 | 阶段、描述、最近变化都作为普通字段原样展示；不由数值自动推导。 |
| 关系进度条 | 当前不应默认实现 | value 无单位、范围或数值类型。 | 只有明确投影配置声明数值范围时才画 meter；否则显示文本值。 |
| 关系网络图 | 需要数据契约 | 当前表与角色只有可选绑定，不存在稳定关系边模型。 | 需要关系对象的稳定 mount ID 与显式表语义；禁止表名/角色名猜测。 |
| 线索、目标、待办 | 部分实现 | 通用状态表可承载，当前无专用实体。 | 第一阶段使用通用表和可选手工 pin；专用卡片需要显式语义配置。 |
| 纯净舞台 | 前端改造 | 当前没有该 UI 状态。 | 增加临时 `cinematicMode`，关闭抽屉/输入，隐藏层 inert，保留恢复入口；不写 localStorage。 |
| 2K / 4K 可读性 | 前端改造 | 已有 90%–200% 字体缩放，默认 125%。 | 扩展 CSS 变量覆盖 HUD、抽屉和对白；设置宽度/字号上限并做视觉回归。 |
| Context 圆环 | 可直接实现 | Composer 已同时接收 `contextPreviewUsage` 与 `lastTurnUsage`。 | 圆环只使用下一轮 context-preview；本轮 usage 只放回复或详情，不能覆盖圆环。 |
| 主模型切换 | 可直接实现 | Composer 已有 catalog 和 session override。 | 迁移到舞台设置菜单；切换不取消当前 turn，从下一 turn 生效。 |
| 停止生成 | 可直接实现 | `useSessionStreamTurn` 已按 requestId 调用 stop。 | 保留现有 hook；只有服务端确认 cancelled 才显示已停止。 |
| 编辑、重试、删除、复制 | 可直接实现 | Timeline 已暴露对应动作。 | 放入日志工作台消息菜单；不要在简化对白 Dock 丢失这些能力。 |
| TTS | 可直接实现 | Timeline 已按持久 assistant message ID 调用 TTS。 | 舞台仅在消息提交并取得 message ID 后显示播放，不进入 SSE 或 metadata。 |
| 玩家角色绑定 | 可直接实现 | Session Room 已有 required role dialog。 | 保持 `/role_bind` 链路和不可取消 invalid 模态；沉浸式页面通过共享 runtime 调用，不得直接写数据。 |
| 移动端 | 前端改造 | 已有 mobile panel 和响应式 Composer。 | 采用单焦点角色、底部对白和近全屏 sheet，不照搬桌面多立绘。 |
| 媒体故障隔离 | 可直接实现 | `useSessionMedia` 与聊天状态分离。 | 新舞台继续把媒体错误作为非阻断状态。 |
| 环境音 | 当前仅视觉占位 | 当前仓库没有 Session 环境音业务链路证据。 | 第一阶段按钮可隐藏或明确为未实现；不得伪装真实音频状态。 |

## 5. 人物关系的安全落地方案

### 5.1 无后端改动的第一阶段

每个关系对象可以使用一张绑定到对应 NPC 的 normal 状态表，例如：

| key | value |
| --- | --- |
| 信任 | `68` |
| 亲密 | `60` |
| 依赖 | `44` |
| 阶段 | `信赖加深` |
| 关系描述 | `信任正在变得明确，重要的决定已经愿意交给彼此。` |
| 最近变化 | `夏澄主动提出交付备用钥匙。` |

该方案完全符合现有 `StatusRow.key/value`。生产 UI 在不知道表语义时，只按通用表展示所有字段。

### 5.2 专用关系卡需要的最小契约

如果要稳定显示“关系网络”而不是普通状态表，至少需要：

- 明确且类型化的 UI semantic，例如 relationship，而不是匹配表名。
- 稳定的关系对象 character mount ID。
- 明确字段展示顺序；可选的数值单位与范围。
- 角色删除、解除挂载、绑定失效时的降级规则。
- API 与数据层的校验，不只在前端读取任意 metadata。

不建议新建一个只能保存单值的 Relationship 实体。即使未来增加专用关系投影，底层仍应允许任意 KV 和文本描述。

## 6. 角色舞台投影契约缺口

当前 `character_sprite` 只是媒体类型，不能回答“这张图属于哪个角色、当前用哪张、放在哪里”。完整舞台至少需要只读投影中的以下信息：

```ts
type StageCharacterProjection = {
  characterMountId: number
  displayName: string
  spriteAssetId: string | null
  poseKey: string | null
  placement: 'far-left' | 'left' | 'center' | 'right' | 'far-right'
  zIndex: number
  focused: boolean
}
```

这只是前端消费形状示意，最终契约需架构评审。约束如下：

- 使用稳定 mount ID，不依靠 `presentCharacters: string[]` 名称匹配。
- Asset 必须由 Media service / Play API 正常授权读取。
- 投影不写入消息正文或 message metadata。
- 没有 sprite 时允许 `avatarUrl`、剪影或首字母降级。
- Media service 不可用时不影响 turn、history、scene 和 Composer。

契约可以在现有 scene 读取结果旁扩展，也可以通过经过评审的独立只读资源提供；不得由 Play WebUI 直接读取工作区图片文件。

## 7. 动态行动建议契约缺口

如果 Phase 4 决定支持动态分支，建议采用明确结构，而不是解析 assistant 正文：

```ts
type TurnSuggestion = {
  id: string
  label: string
  prompt: string
  mode: 'ic' | 'ooc' | 'gm'
}
```

还必须决定：

- 建议由哪个服务生成，是否计入主 turn。
- 建议是临时数据还是需要刷新后恢复。
- 点击建议后最终发送的是 `prompt` 还是允许用户先编辑。
- 建议失败时如何回退到自由行动。
- 是否允许在 Context 门禁状态下出现，以及斜杠命令如何处理。

无论采用哪种方式，assistant `content` 仍是正文真源，建议不能写成显示专用 message metadata，也不能通过自然语言正则猜测。

## 8. 推荐前端组件边界

沉浸式页面不作为 `SessionRoom.tsx` 的视觉变体，也不挂在它的组件树下。推荐架构为两个独立页面消费同一前端领域运行时：

```text
Standard SessionRoom Page ─┐
                           ├─ Shared Session Experience Runtime
Immersive Session Page ────┘
```

页面组合可以按下列边界实现；具体路由和类型名可在 ADR 中确定：

```text
StandardSessionRoomPage
└─ SessionExperienceRuntimeProvider
   └─ StandardSessionRoomExperience

ImmersiveSessionPage
└─ SessionExperienceRuntimeProvider
   └─ ImmersiveSessionExperience
      ├─ ImmersiveStage
      │  ├─ SessionMediaBackground
      │  └─ StageCharacterLayer
      ├─ ImmersiveHud
      ├─ ActiveDialogueDock
      │  ├─ SpeakerPlate
      │  ├─ DialoguePager
      │  └─ ImmersiveComposerView
      ├─ SessionTraceDrawer
      ├─ WorldStateDrawer
      └─ CinematicModeController
```

边界要求：

- `SessionRoom.tsx` 只保留标准页面的 composition root 职责；沉浸式页面拥有独立的 route/page 和 composition root。
- `SessionExperienceRuntime` 是概念边界，可由按领域拆分的 provider、hooks、controller 和 service 组成；它不是 Next.js `middleware.ts`，也不应演变成囊括所有状态的单一 God hook。
- 共享运行时负责 Session 数据与 history window、stream/stop、角色绑定与 Composer actions、主模型、Context Preview、status/media/TTS 等领域能力。
- 两个页面只消费共享 runtime 的类型化状态与动作；标准页面保留原有视觉，沉浸式页面独立管理 DialoguePager、焦点角色、HUD、抽屉和纯净舞台状态。
- `DialoguePager` 只消费 parser/reducer 组装后的 canonical content、解析段落和字体/容器测量信息；不得读取 SSE chunk 边界或改变 stream reducer。
- `CinematicModeController` 只管理临时 UI 状态和焦点，不拥有业务数据。
- Composer、日志和状态工作台优先复用共享 controller、消息映射、动作与内容组件；允许两个页面分别实现视图，避免为了复用视觉组件再次耦合页面结构。

## 9. 实现时必须保持的现有约束

- 沉浸式体验必须使用独立路由/page，不把舞台组件和页面状态放入 `SessionRoom.tsx`。
- 标准与沉浸式页面通过共享前端领域 runtime/provider/hooks/service 复用业务能力，不复制两套 stream、history、stop 或 role binding 实现。
- 沉浸分页不得新增或修改 SSE event type、payload、顺序、完成语义或 parser/reducer 的 canonical content 结果。
- `pageIndex`、`pageCount`、字符页边界和测量缓存只属于沉浸式页面内存，不进入 SSE、API、消息 metadata、数据库或 localStorage。
- `history-page` 只表示服务端 turn 历史分页，不得与沉浸对白的前端视觉分页混用。
- 会话内 API 只使用全局短 `session_id`。
- 玩家角色选择和切换统一走 Agent `/role_bind` 命令链路。
- scene 仍是 story 挂载的专用实时状态，不进入普通 normal 表展示逻辑。
- Context 圆环只使用下一轮 `context-preview`。
- stop 必须使用 requestId 的既有 Play API → Agent service 链路。
- 主模型选择继续遵循 config default < story override < session override。
- 切换模型不取消当前 turn。
- TTS 只从已提交 assistant `message_id` 派生。
- 背景、Gallery 和立绘引用不进入正文、metadata 或 localStorage。
- 媒体服务故障不影响聊天。
- thinking 只作为可公开摘要/诊断展示，不承诺完整内部推理。
- assistant 带标签全文原样进入 SSE、历史和数据库。

## 10. 风险与测试清单

### 10.1 主要风险

- **页面逻辑分叉**：两个页面若各自实现 stream、stop、role 或 history，会很快产生行为差异。必须先抽共享领域 runtime，并用同一契约测试覆盖两个消费者。
- **反向污染标准页面**：把沉浸式 UI 状态塞进 `SessionRoom.tsx` 会重新造成组件膨胀。独立路由与独立 composition root 是架构门槛。
- **双时间线风险**：舞台当前对白和日志 Timeline 可能指向不同消息。必须共用消息 ID / turn ID 和同一 history window 真源。
- **流式分页抖动**：canonical 正文前缀增长会改变分页边界。不得按 SSE chunk 切页；需要“已读页稳定、未读尾部重算”的策略，并用字符偏移锚定重排后的位置。
- **角色误匹配**：名称重复、改名或多语言会让 sprite 焦点错误。完整实现必须使用 mount ID。
- **关系语义误判**：按表名猜“人物关系”会在用户自定义表中误判。没有 typed semantic 就通用渲染。
- **历史性能**：大日志抽屉不能一次渲染全部历史；继续使用 turn 分页和窗口缓存。
- **焦点泄漏**：纯净舞台只做 opacity 隐藏会保留 Tab 焦点。必须同时 inert。
- **4K 无限拉伸**：单纯使用 vw 会让对话和抽屉过长。所有关键容器都需要像素上限。

### 10.2 前端单元测试

- 共享 runtime：标准与沉浸式两个页面对 history、stream/stop、role、Composer actions、模型与 Context Preview 使用同一状态和动作契约。
- `DialoguePager`：中文标点、引号、无标点长串、换行、emoji、200% 字号、raw fallback、容器 resize、方向变化和字符偏移锚定。
- 分页不变量：同一份 canonical content 在不同视口可以产生不同页数，但所有页面重组后与输入逐字符一致。
- SSE 边界：改变同一正文的 `text_delta` chunk 切法不应改变最终分页结果；测试中不需要新增任何分页事件或字段。
- `ActiveDialogueDock`：补全当前页、下一页、下一段、AUTO、reduced motion。
- 关系投影：多个数字、文本、缺失值、非数值、长描述、字段顺序。
- Cinematic：隐藏层 inert、Esc/H 恢复、焦点返回。
- 日志映射：持久消息、运行期 thinking、tool、outcome、error 的显示边界。

### 10.3 集成与视觉测试

- 路由隔离：标准 SessionRoom 与独立沉浸式页面可分别直接进入、刷新和返回；关闭沉浸式入口不影响标准页面。
- 视口：1440×900、1920×1080、2560×1440、3840×2160、390×844、低高度横屏。
- 场景：0/1/2/5 名角色、无背景、无立绘、媒体服务失败。
- 历史：空历史、超长历史、前后分页失败、跳到最新。
- 流式：thinking → tool → text → completed、provider error、stop cancelled、stop 已完成。
- 业务：角色 invalid、Context 门禁、斜杠命令、模型切换、TTS message ID 未就绪。
- 每次生产前端改造至少运行 `cd play_webui && npm run build`。

## 11. 最终判定

可以先做“新增独立页面、抽共享运行时、不改后端与正文 SSE”的高价值版本：沉浸背景、窄幅分页对白、现有快捷回复、自由行动、单一全部日志、大状态工作台、纯净舞台和 2K/4K 可读性都能落地。标准 SessionRoom 可继续独立演进，关闭沉浸式入口即可回退，不需要在同一组件树中切换布局。

不要在这一阶段假装已有完整多立绘数据、跨刷新 thinking、动态分支或专用关系图。它们分别需要舞台投影、公开诊断、建议和关系语义契约。
