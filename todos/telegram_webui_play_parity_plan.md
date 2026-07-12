# Telegram 游玩能力对齐 WebUI：分阶段迭代计划

> 文档状态：P0 已实施，P1/P2 待实施  
> 制定日期：2026-07-12  
> 依据范围：近两日 Session Composer、主 Agent turn 链路、动态 RP Module、Context 门禁及 SessionRoom 交互重构后的当前主干  
> 实施原则：后续一次只领取一个阶段；上一阶段验收通过后再进入下一阶段

## 1. 目标与已锁定决策

Telegram 的产品定位保持为轻量游玩入口、通知入口与兜底交互，不复制 Play WebUI 的管理后台。本轮“对齐 WebUI”指玩家可以在 Telegram 内完成主要游玩闭环，而不是在 Telegram 内维护 Story、角色卡、世界书、状态表模板或 RP Module 配置。

已锁定的产品决策：

- 优先级为“游玩闭环”，依次交付生成控制、Session Composer、角色/会话和轻量只读信息。
- 交互采用按钮优先、命令兜底；Telegram 专属命令由接入层消费，不进入主 LLM。
- 快捷回复点击后先预览正文，再由玩家确认发送；误触不得创建 turn。
- 模式与叙事风格按 `chat_id + session_id` 保存在 Telegram 进程内；进程重启后丢失，切换到新 session 时使用新 session 的默认值。
- 临时偏好不会写入数据库，不跨 Telegram chat 共享，也不改变 WebUI 当前选择。
- Telegram 只能通过 `agent_service.client.AgentClient` 访问 Agent 服务，不直接访问 `rpg_data`、Play API 或 Agent 私有对象。
- 玩家角色选择和切换始终通过 Agent service 的 `/role_bind <序号>` 命令链路完成；Telegram 不直接写角色绑定。
- Telegram 不提供主动停止按钮或 `/stop` 命令；流式请求仍携带内部 `request_id`，仅用于关联和进程关闭时的安全清理。
- 本轮不新增数据库迁移，不改变现有 workspace/story/session 数据结构。

## 2. 当前基线与能力差距

当前 Telegram 已具备：

- 流式与非流式正文发送，流式内容通过编辑 Telegram 消息逐步呈现。
- Markdown/RP 输出到 Telegram HTML 的转换、4096 字符分块和常见 Telegram API 错误降级。
- Agent 命令列表同步到 Bot 菜单，并将普通 Agent 命令透传给 Agent service。
- `/sessions`、`/session_create`、`/session_switch` 及简单 Inline Keyboard 会话选择。
- `/role_bind` 文本命令链路。
- 每个 bot 固定绑定 `workspace_id + story_id`，并通过 catalog 解析或创建默认 session。

与当前 WebUI 的主要差距：

- 消息 handler 会等待整个流结束，后续输入只能在 Telegram update 队列中静默等待。
- 多个 chat 指向同一 session 时缺少渠道侧互斥，输入会继续进入 AgentMailbox FIFO。
- callback token 没有统一的 chat/session 归属校验、有效期和分页能力。
- 正在生成时可以继续收到正文或切换 session，缺少清晰的并发交互策略。
- `mode`、`narrative_style_id` 和 Story 快捷回复没有 Telegram UI，也没有透传到 send/stream。
- 角色无效时只能阅读固定编号文本，没有按钮化补选流程。
- 会话菜单只显示 session ID、固定截断前 20 条，缺少 title、分页和创建后切换入口。
- 当前场景、overall 摘要和下一轮 Context 占用没有轻量面板。

## 3. 阶段总览与依赖

| 阶段 | 主题 | 用户可感知结果 | 前置依赖 |
|---|---|---|---|
| P0 | 生成串行化与 Telegram 交互底座 | 后台生成可及时拒绝重复输入；callback 具备归属和 TTL 校验 | 当前基线 |
| P1 | Session Composer 游玩能力 | 可选择模式/风格并通过确认式快捷回复游玩 | P0 的 action registry 与 active turn 状态 |
| P2 | 角色、会话与轻量信息 | 可按钮补选角色、分页切换会话，并查看场景/摘要/Context | P0；P1 的 session 偏好与菜单框架 |

每个阶段均需同时完成接口、客户端、Telegram 行为、测试和文档验收，不把“临时硬编码接口”留给下一阶段清理。

---

## 4. P0：生成串行化、并发控制与 Callback Action Registry（已完成）

### 4.1 阶段目标

建立后续所有按钮交互复用的安全 action registry，并让 Telegram 流式/非流式生成以 Application 托管任务执行、正确互斥和收尾。

本阶段完成后，玩家发送正文时立即看到“正在生成”占位；同一 chat 或同一 session 生成期间的新输入立即被拒绝，不进入 AgentMailbox 排队。本阶段不提供用户主动打断生成。

### 4.2 本阶段不做

- 不增加模式、叙事风格或快捷回复。
- 不增加摘要、场景、Context 面板。
- 不更改 Agent turn、transaction、commit 或取消语义。
- 不增加停止按钮、`/stop` 命令或 `/chat/stop` 调用。
- 不持久化 Telegram 交互状态。
- 不将通用 callback/action 机制放入 `rpg_core`。

### 4.3 P0.1：统一 callback action registry

新增 Telegram 接入层内部的 action registry，用它替换会话 flow 当前各自维护的不透明 token 字典。建议放在 `channels/telegram/` 内的独立模块，由 session、turn、composer、role flow 共同依赖。

每个 action 至少记录：

```text
token
kind
chat_id
session_id
payload
created_at
expires_at
consume_policy
```

行为约束：

- `callback_data` 只传短前缀和随机 token，不直接携带 session ID、角色 ID、快捷回复正文或其它可信业务参数。
- token 使用密码学安全随机值；完整 `callback_data` 必须稳定低于 Telegram 的 64-byte 限制。
- 普通菜单 action 默认 10 分钟过期。
- 一次性 action 首次成功解析后消费；分页、返回等导航 action 可在有效期内重复使用。
- 解析时必须校验 callback 来源的 `chat_id`，需要绑定 session 的 action 还必须校验当前 chat 仍指向相同 `session_id`。
- token 不存在、过期、已消费、跨 chat 或跨 session 时不执行业务操作，只回答“菜单已失效，请重新打开”。
- registry 每次注册或解析时顺带清理过期项，避免常驻 bot 无限增长；无需后台清理任务。
- action payload 只存在进程内存中，不写日志全文；快捷回复只记录 ID，调试日志最多记录 action kind、chat/session 和 token 前缀。

迁移现有会话选择 callback 后，删除 `TelegramSessionFlow` 内重复的 `_picker_actions` 管理逻辑。

### 4.4 P0.2：活动 turn 状态与非阻塞执行

Telegram 为每次流式正文生成 `uuid4().hex` 形式的 `request_id`，并维护：

```text
ActiveTelegramTurn
- chat_id / session_id / request_id
- phase / streaming / task
- placeholder_message_id
- accumulated_text / rendered_sent_text
- last_edit_at
```

同时维护 `active_by_chat` 与 `active_by_session`。同一 chat 或同一 session 只允许一个 Telegram 活动 turn；不同 chat 且不同 session 可以并行。

为了让新 update 能在生成期间立即得到忙碌反馈，正文 handler 不再占用整个更新处理周期等待 SSE：

- handler 完成权限、session 和活动 turn 检查后，通过 Telegram Application 管理的 task 调度生成流程并立即返回。
- task 必须由 Application 生命周期托管；adapter 停止时等待或取消这些 task，不创建无法追踪的裸 `asyncio.create_task`。
- task 内部异常统一进入 Telegram turn flow 收尾，并继续交给现有日志/error handler 记录。
- 不通过开启无限制 `concurrent_updates` 解决问题；共享状态仍由单 chat 活动记录和必要的短临界区保护。

流式和非流式配置都通过相同托管任务与双索引互斥执行；只有流式请求把内部 `request_id` 传给 Agent service。

### 4.5 P0.3：生成展示与终止状态机

发送正文后的正常流程：

1. 解析当前 `session_id`，确认该 chat 没有活动 turn。
2. 流式请求生成内部 `request_id`。
3. 立即发送无按钮的“正在生成…”占位消息，取得 `message_id`。
4. 建立 active turn 记录，再调用 `AgentClient.stream(session_id, text, request_id=...)`。
5. `TEXT` 事件累积并节流编辑同一条消息。
6. `DONE` 到达后，以完整 assistant content 完成最终渲染，再清理 active turn。
7. `ERROR`、SSE 提前结束或本地异常均不得伪装为成功；清理 active turn，并给出稳定错误提示。
8. 进程关闭只取消本地托管 task，不提供玩家侧主动中断入口，也不调用 `/chat/stop`。

### 4.6 长消息与 Telegram API 降级

- 流式编辑只在渲染后内容仍可放入单条 Telegram 消息时进行。
- 超过编辑上限后停止继续编辑正文，但保留活动状态；收到 `DONE` 后用现有分块器输出完整内容。
- 最终分块不得同时保留一条重复的完整/半完整占位消息：优先把占位消息编辑成第一块，其余块依次发送。
- 最终 HTML 编辑失败时回退为纯发送分块，并把旧占位消息改成简短状态或删除；不得留下永久“正在生成”。
- Telegram `RetryAfter`、`TimedOut` 或 `BadRequest` 不改变 Agent commit 结果。若 Agent 已 `DONE` 但 Telegram 最终发送失败，记录“已提交但渠道投递失败”的 warning，不能调用 stop 或回滚 turn。

### 4.7 命令与并发规则

- 活动 turn 期间：
  - 普通正文、快捷回复（后续阶段）和全部命令被拒绝。
  - 有效 callback 返回忙碌提示但不 claim，生成完成后仍可重试。
- 同 chat 重复正文提示当前消息正在生成；同 session 的其它 chat 提示会话正忙；两者都不会调用 AgentClient。
- adapter 停止时取消 Application 托管 task、清理双索引和 registry，随后关闭 AgentClient，不调用 `/chat/stop`。

### 4.8 P0 测试

主要补充 `channels/tests/test_telegram.py`，必要时扩充 `test_telegram_runner.py` 和 `test_base.py`：

- 每个流式 turn 生成唯一内部 request ID，并原样传给 stream；不调用 stop。
- 正文 handler 调度受管 task 后立即返回。
- 占位消息立即出现，TEXT 节流更新，DONE 完成最终投递并清理状态。
- ERROR、无 DONE、Application task 取消和 Telegram API 失败均清理双索引。
- 同 chat 或同 session 的重复正文被拒绝；不同 chat 且不同 session 可以并行。
- 活动 turn 期间禁止切换/创建 session，结束后恢复。
- token 过期、重复、跨 chat、跨 session和伪造 token 均不执行动作。
- 超长最终回复不重复、不遗留“正在生成”，分块均满足 Telegram 长度限制。
- adapter stop 会清理活动 task；Telegram API 失败不会泄漏 active turn。
- 流式和非流式均不展示停止按钮，并遵守相同互斥。

阶段回归命令：

```bash
uv run python -m pytest channels/tests/test_base.py channels/tests/test_telegram.py channels/tests/test_telegram_runner.py -q
uv run python -m pytest agent_service/tests -q
```

### 4.9 P0 完成条件

- 生成期间的新 update 会立即收到忙碌反馈，不会静默排入 Telegram 或 AgentMailbox 队列。
- 任一终止路径都不残留 active turn 或永久“正在生成”消息。
- Telegram 中不存在停止按钮、`/stop` 命令或 `/chat/stop` 调用。
- 现有会话选择 callback 已迁入统一 action registry。
- P0 测试和既有 Telegram 回归全部通过。

---

## 5. P1：Session Composer 游玩能力

### 5.1 阶段目标

把 WebUI 已落地的 turn mode、Story 叙事风格和启用中的快捷回复带到 Telegram。玩家可以从 `/play` 主面板查看并调整当前临时偏好，普通正文与确认后的快捷回复使用同一条 send/stream 业务链路。

### 5.2 本阶段不做

- 不在 Telegram 创建、编辑、排序或挂载叙事风格与快捷回复。
- 不更改 workspace turn mode 的 prompt。
- 不把模式/风格偏好写入 session 数据库。
- 不增加 Story/Session RP Module 或主 LLM 配置入口。
- 不实现自由文本快捷回复编辑器；预览确认只发送 Story 已配置的原文。

### 5.3 P1.1：Agent service 只读 Composer 契约

新增接口：

```http
GET /agent/v1/chat/session/composer?session_id={session_id}
```

响应使用 Agent service 一贯的 snake_case，并与 Play API 的 Session Composer 数据语义一致：

```json
{
  "session_id": "abc123",
  "workspace_id": "demo_workspace",
  "story_id": 1,
  "modes": [
    {
      "mode": "ic",
      "short_name": "IC",
      "prompt": "...",
      "sort_order": 0,
      "version": 1
    }
  ],
  "narrative_styles": [
    {
      "mount_id": 10,
      "narrative_style_id": 3,
      "name": "电影化",
      "prompt": "...",
      "is_base": true,
      "sort_order": 0,
      "version": 1
    }
  ],
  "base_narrative_style_id": 3,
  "quick_replies": [
    {
      "id": 20,
      "title": "观察四周",
      "message": "我先观察四周。",
      "sort_order": 0,
      "enabled": true,
      "version": 1
    }
  ]
}
```

契约要求：

- session 不存在返回 404。
- `modes` 使用 `normalize_turn_mode()` 后的 `ic | ooc | gm`。
- `narrative_styles` 只返回当前 Story 已挂载风格，保持既有排序。
- `quick_replies` 只返回 `enabled=true` 的当前 Story 快捷回复。
- 没有基础风格时 `base_narrative_style_id=null`；调用方使用 `narrative_style_id=null` 表示 Story 默认。
- Agent service 可复用 `rpg_data.services.session_composer`，但不依赖 `play_api` router/schema/backend。
- 在 `agent_service/schemas.py` 增加 response model 与 TypedDict，在 `AgentClient` 增加 `get_session_composer(session_id)`。
- 该接口只读，不增加 PATCH/POST/DELETE Composer 接口。

### 5.4 P1.2：Telegram Composer 临时状态

新增按 `(chat_id, session_id)` 建键的临时状态：

```text
TelegramComposerSelection
- mode: ic | ooc | gm
- narrative_style_id: int | None
- composer_version_fingerprint
```

默认和生命周期：

- 首次进入一个 session：`mode=ic`、`narrative_style_id=None`。
- 玩家选择后，偏好作用于该 chat 中这个 session 的后续普通正文和快捷回复，直到再次修改、进程重启或数据失效。
- 从 session A 切到 B 时加载 B 自己的临时选择；B 尚无记录则使用默认值。
- 切回 A 时，只要进程未重启，恢复 A 的临时选择。
- `None` 永远表示“故事默认”，不把 `base_narrative_style_id` 作为显式 override 发送。
- Composer 刷新后若当前 mode 已不存在，回退 `ic`；若风格不再挂载，回退 `None` 并提示一次。
- fingerprint 可由 mode/style/quick reply 的 ID+version 组成，只用于判断菜单是否过期，不写持久层。

### 5.5 P1.3：`/play` 主面板与命令入口

新增 Telegram 本地命令：

- `/play`：打开主面板。
- `/mode`：打开模式选择；可选支持 `/mode ic|ooc|gm` 作为命令兜底。
- `/style`：打开叙事风格选择；不带参数，避免要求用户记数据库 ID。
- `/quick`：打开快捷回复列表。

`/play` 文案至少展示：

```text
当前会话：{title 或 session_id}
模式：{short_name}
叙事风格：故事默认 / {name}
状态：空闲 / 正在生成
```

按钮布局：

```text
[模式：IC] [风格：故事默认]
[快捷回复]
[会话] [角色]
```

其中“会话”和“角色”在 P1 可先链接现有 `/sessions`、`/role_bind` 交互，P2 再升级展示。若正在生成，相关命令和按钮统一返回忙碌提示，不允许切换 Composer 选择。

模式菜单：

- 按后端 `sort_order` 展示所有 modes。
- 当前选择用 `✓` 标记。
- 点击后只更新本地 selection，编辑菜单回到 `/play`，不调用 Agent、不创建 turn。

风格菜单：

- 第一项固定为“故事默认”；当前选择为 `None` 时标记选中。
- 其后按后端顺序展示 Story 已挂载风格。
- callback payload 只保存风格 ID 和打开菜单时的 fingerprint；执行前重新验证该风格仍存在。
- 点击后只更新本地 selection，不写 Story/Session 配置。

列表超过 Telegram 单页适宜数量时每页 8 项，并提供“上一页 / 下一页 / 返回”；页码和查询上下文放在 action registry payload，不放入可信 callback 参数。

### 5.6 P1.4：发送链路透传

普通正文和快捷回复最终必须共用一个 Telegram turn 提交入口。该入口在创建 active turn 前冻结：

```text
TelegramTurnSelectionSnapshot
- session_id
- mode
- narrative_style_id
- composer_fingerprint
```

调用规则：

- 流式：`AgentClient.stream(session_id, text, request_id, mode=..., narrative_style_id=...)`。
- 非流式：`AgentClient.send(session_id, text, mode=..., narrative_style_id=...)`。
- 当前 turn 开始后再切换偏好不影响该 turn；但 P0 已规定活动 turn 期间禁止切换，因此正常不会出现此竞态。
- Agent 斜杠命令不套用 Composer 行为；Telegram 本地命令先消费，其余命令继续走 `execute_command()`。
- 不把 mode/style 拼进用户正文，不修改 `TurnRequest.text` 真源。
- Context 门禁、StatusSubAgent、RP Module snapshot 和 transaction 继续由 Agent turn pipeline 统一处理。

可以给 `ChannelAdapter` 的受保护 send/stream helper 增加可选 execution 参数并保持 CLI 默认行为；不得在 Telegram 复制 Agent preflight 或 commit 分支。

### 5.7 P1.5：快捷回复预览确认

快捷回复流程：

1. `/quick` 或 `/play` 的“快捷回复”查询/刷新 Composer。
2. 每页展示 8 个启用项，按钮使用 `title`。
3. 点击某项后，从当前 Composer 数据按 `reply_id` 取原文，发送预览消息。
4. 预览包含当前模式、叙事风格和完整待发送正文，并提供“确认发送 / 取消 / 返回列表”。
5. “确认发送”是一次性 action；首次点击立即消费并进入与普通正文相同的 turn 提交入口。
6. “取消”只关闭这次待确认状态，不调用 AgentClient、不写历史。

安全与一致性规则：

- action payload 保存 `reply_id + version + session_id`，不保存或信任 callback 内正文。
- 确认时重新读取当前缓存/服务数据并校验 reply 仍启用且 version 一致。
- 已删除、禁用或修改的快捷回复提示“内容已变化，请重新选择”，不得发送旧正文。
- 预览后的模式/风格取“打开预览时冻结的选择”。如果玩家先返回修改选择，旧确认按钮视为过期，要求重新预览。
- 连点确认、Telegram 重放 callback 或两个设备同时点击只允许创建一个 turn。
- 预览正文超长时按现有分块显示；确认按钮附在最后一块。

### 5.8 Composer 错误与缓存策略

- Composer 首次打开或当前缓存超过 60 秒时从 Agent service 拉取；菜单中的“刷新”强制重新拉取。
- 发送前不为每条普通正文强制请求 Composer；使用已验证的临时 selection，服务端仍是 mode/style 合法性的最终门禁。
- Agent 返回 style 失效类 422 时，Telegram 强制刷新 Composer、将 selection 回退为 `None`，保留玩家原正文，并提示重新发送；不得自动用另一风格重试从而创建不可预期 turn。
- Composer 服务不可用时，普通正文仍可以 `mode=ic, narrative_style_id=None` 继续游玩；`/play` 明确提示高级选项暂不可用。
- 不在日志记录 mode/style prompt 或快捷回复完整正文；只记录 ID、version 和选择结果。

### 5.9 P1 测试

Agent service 与 client：

- Composer payload 字段、排序、基础风格、enabled-only 快捷回复及空列表契约。
- session 不存在为 404，非法数据不会生成非标准 mode。
- `AgentClient.get_session_composer()` 路径、query 和反序列化正确。
- send、stream 与 context preview 既有 optional Composer 字段契约不回归。

Telegram：

- `/play` 正确展示当前 mode/style，选择按钮只改本地状态、不调用 Agent。
- `(chat_id, session_id)` 隔离、切换后默认、切回恢复和进程内生命周期符合约定。
- 普通流式/非流式正文均透传冻结的 mode/style。
- “故事默认”发送 `narrative_style_id=None`。
- 风格删除、version/fingerprint 变化会使旧菜单失效并安全回退。
- 快捷回复选择只预览，确认才发送，取消不发送，重复确认只发送一次。
- 快捷回复在确认前被修改/禁用时不发送旧内容。
- 菜单分页、返回、刷新和过期 token 正确。
- Composer 获取失败时 IC + Story 默认的基础对话仍可用。

阶段回归命令：

```bash
uv run python -m pytest agent_service/tests -q
uv run python -m pytest channels/tests/test_base.py channels/tests/test_telegram.py channels/tests/test_telegram_runner.py -q
uv run python -m pytest rpg_data/tests/test_session_composer.py -q
```

### 5.10 P1 完成条件

- 玩家可以只用按钮完成模式和叙事风格选择，并在后续正文中稳定生效。
- 快捷回复永远先预览确认，且与普通正文共用 request ID 和 send/stream 链路。
- Telegram 没有直接读取 `rpg_data` 或调用 Play API。
- Composer 管理能力仍只存在于 WebUI；Agent service 新接口全部只读。
- P1 新增契约、client 和 Telegram 测试全部通过。

---

## 6. P2：角色、会话与轻量信息

### 6.1 阶段目标

补齐移动端进入故事后的导航和恢复能力：按钮化补选/切换角色，能按 title 分页管理当前 Story 的会话，并查看当前场景、overall 摘要和下一轮 Context 占用。

### 6.2 本阶段不做

- 不在 Telegram 编辑角色卡、Story、世界书、场景或普通状态表。
- 不展示或修改 RP Module 配置和 Narrative Outcome 权重。
- 不切换主 Agent LLM。
- 不做历史分页、retry、edit、truncate 或单条删除。
- 不增加 summary 生成命令；仅查看已经存在的 summary。
- 不新增独立 usage 获取接口、usage 持久化或 Telegram 本地 usage 历史。

### 6.3 P2.1：Agent service Session Overview 契约

新增只读接口：

```http
GET /agent/v1/chat/session/overview?session_id={session_id}
```

建议响应：

```json
{
  "session_id": "abc123",
  "workspace_id": "demo_workspace",
  "story_id": 1,
  "title": "城堡入口",
  "player_character_status": "invalid",
  "player_character": null,
  "player_character_options": [
    {
      "index": 1,
      "character_id": 8,
      "mount_id": 12,
      "name": "艾琳",
      "avatar_url": "",
      "role_label": "玩家角色",
      "summary": "..."
    }
  ],
  "scene": {
    "attrs": {},
    "time": "深夜",
    "location": "旧城门",
    "present_characters": ["艾琳"],
    "mood": "紧张"
  },
  "overall_summary": {
    "kind": "overall",
    "title": "目前剧情",
    "excerpt": "...",
    "markdown": "...",
    "updated_at": "2026-07-12T12:00:00+00:00"
  }
}
```

契约要求：

- `player_character_status` 只允许 `bound | invalid`，沿用 `SessionRoleService.get_state()` 真源。
- `player_character_options.index` 与 `/role_bind <序号>` 当次列表完全一致；排序继续由 Story character mount 排序决定。
- `scene` 沿用 Play API 当前场景的规范化语义；没有 scene 时返回空结构，不将其视为 404。
- `overall_summary` 沿用 `SummaryReader` 的 overall 文档语义；不存在时为 `null`。
- response schema/TypedDict 和 `AgentClient.get_session_overview()` 一并增加。
- Agent service 可以组合既有 catalog、session role、status 和 summary reader，但不依赖 Play API backend，不将 HTTP 模型放进 `rpg_core`。
- 该接口严格只读，不触发 Agent initialize、summary 生成、状态表复制或角色自动绑定。

同时增强既有 `GET /chat/sessions`，在保留 `sessions: list[str]` 兼容字段的基础上新增：

```json
{
  "session_items": [
    {
      "session_id": "abc123",
      "title": "城堡入口",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

Telegram 使用 `session_items`；旧 CLI、测试或调用方仍可继续读取 `sessions`。不要把原字段直接从字符串数组改成对象数组。

### 6.4 P2.2：按钮化角色补选与切换

角色入口：

- `/role_bind` 无参数时由 Telegram 打开角色菜单，不再只显示纯文本编号。
- `/play` 主面板的“角色”按钮进入同一菜单。
- Session Overview 显示 `invalid` 时，玩家下一次发送普通正文前先拦截并展示不可取消的角色选择菜单；原正文不进入 Agent，也不在 Telegram 自动缓存后重放。

角色按钮显示 `name`，可附简短 `role_label`；详情/summary 过长时只在单独预览中展示，不塞入按钮。

绑定流程：

1. 菜单 action 保存 `session_id + option index + character_id + mount_id`。
2. 点击时重新获取 Overview，确认该 option 的 index、character ID 和 mount ID 仍一致。
3. 调用 Agent service 的 `bind_player_character(session_id, character_id)`。
4. Agent service 内部继续把 character ID 映射为当前 `/role_bind <序号>` 并执行命令，不新增 DataManager 直写路径。
5. 绑定成功后展示 Agent 返回的 reply；若 main history 原为空，reply 中的 Story `first_message` 只出现一次。
6. 刷新 Overview，只有状态确认为 `bound` 才返回 `/play` 主面板。

异常规则：

- 没有可选角色时提示“当前 Story 未挂载可扮演角色”，引导到 WebUI 管理，普通正文继续被 Agent 门禁拒绝。
- mount 在点击前变化时旧 token 失效并刷新列表。
- 绑定失败不更新 Telegram 本地角色状态，不猜测成功。
- 已 bound 时仍允许主动打开菜单切换角色；切换不重放 `first_message`。

### 6.5 P2.3：会话列表分页与创建后切换

会话菜单升级：

- 使用 `session_items` 展示 title；title 为空时回退 session ID。
- 每项辅助展示短 session ID，当前 session 使用 `✓` 标记。
- 每页 8 个 session，提供“上一页 / 下一页 / 新建会话 / 返回”。
- 服务返回顺序作为唯一排序真源；Telegram 不按本地访问时间重排。
- 页码 action 绑定打开菜单时的列表 fingerprint；列表变化时自动回到有效页并刷新。

创建流程保持系统生成 session ID：

- `/session_create [title]` 继续支持直接创建。
- 按钮“新建会话”进入 title 输入状态，5 分钟超时；`/cancel` 只取消这个输入状态。
- 未提供 title 时使用 bot 的 `session_title` 默认值，不允许用户指定 session ID。
- 创建成功后显示“立即切换 / 留在当前会话”按钮，不依赖 `auto_pin_created_session` 才能让用户选择。
- “立即切换”先通过 Agent `/session_switch {id}` 校验加载成功，再 pin 当前 chat。

切换规则：

- 活动 turn 期间禁止切换。
- 切换成功后关闭旧 session 菜单和待确认快捷回复；active turn 理论上为空，否则视为实现错误。
- Composer 临时状态按 session 分桶，因此不删除旧 session 的选择；新 session 使用自己的记录或默认。
- 切换后立即获取 Overview：若角色 invalid，展示角色选择；否则返回 `/play`。
- 切换失败时保持旧 pin，不能先更新 `_session_overrides` 再调用 Agent。

### 6.6 P2.4：场景、摘要和 Context 只读面板

新增 Telegram 本地命令并加入 `/play` 的“信息”子菜单：

- `/scene`：读取 Overview 中的当前场景。
- `/summary`：读取 Overview 中的 overall summary。
- `/context`：调用既有 `AgentClient.get_context_preview()`。

`/scene` 展示顺序：

1. 时间
2. 地点
3. 在场角色
4. 氛围
5. 其它 `attrs`，保持服务返回顺序

没有场景属性时提示“当前尚未记录场景”，不展示空字段，不允许在 Telegram 编辑。

`/summary`：

- 有 overall 时展示 title、覆盖 turn 范围（若可得）、更新时间和 markdown 正文。
- 正文使用现有 Telegram HTML renderer 和分块器。
- 没有 overall 时提示“当前尚未生成整体摘要”，给出 `/compact` 的纯说明，但不自动执行或填入命令。
- 本阶段不展示 batch 列表，避免引入摘要分页和文件选择状态。

`/context`：

- 使用当前 `(chat_id, session_id)` 的 mode/style 调用 context preview，确保展示的是下一轮实际主 Agent Context 估算。
- 优先读取 `usageEstimate.usedTokens` 和 `contextLimit`，缺失时以 `totals.tokenCount` 作为 used token；窗口未知时显示“上限未知”。
- Telegram 自行计算 `used / limit` 和 K/M 简写；达到 70% 标记提醒，达到 90% 标记高风险，但真正正文拒绝仍以 Core 门禁为准。
- 只展示下一轮 preview，不用上一轮 provider usage 覆盖，不持久化 usage，也不增加新 usage API。
- preview 失败不会阻止正文，提示暂不可用即可。

### 6.7 P2.5：`/start` 首次使用向导

`/start` 不再只有固定欢迎语。它需要：

1. 解析当前 chat 的 session。
2. 获取 Session Overview。
3. 展示当前 Story 绑定下的 session title、玩家角色状态和轻量说明。
4. `invalid` 时只提供“选择角色 / 会话”入口。
5. `bound` 时提供“开始游玩 / 快捷回复 / 会话 / 信息”入口。
6. 明确说明角色卡、Story、世界书、状态表和玩法模块配置需在 Play WebUI 完成，但不硬编码部署 URL；只有未来配置提供 WebUI URL 时才展示链接按钮。

Overview 或 Composer 暂不可用时仍保留“发送消息开始冒险”和 `/sessions` 兜底，不能让 `/start` 成为单点阻塞。

### 6.8 P2 测试

Agent service 与 client：

- Overview 对 bound/invalid、无角色、无 scene、无 summary 和完整数据返回正确 typed payload。
- 角色 option index 与 `/role_bind` 列表排序一致。
- Overview 保持只读，不 initialize Agent、不追加 first message、不创建状态副本。
- sessions 同时返回兼容 `sessions` 与新增 `session_items`，title/时间字段正确。
- `AgentClient.get_session_overview()` 与增强后的 list sessions 契约正确。

Telegram：

- invalid 角色发送正文时先展示角色按钮，正文不调用 send/stream。
- 角色 callback 仍走 `bind_player_character()` → `/role_bind`，成功后刷新状态并只展示一次 first message。
- 角色 mount 变化、无角色和绑定失败安全处理。
- 会话 title/短 ID、8 项分页、当前标记、刷新及过期页 token 正确。
- 创建后“立即切换/留在当前”均符合选择；失败切换不改变当前 pin。
- session 切换清理旧菜单/确认状态并按目标 session 恢复 Composer 临时选择。
- `/scene`、`/summary`、`/context` 的有数据、空数据、长文本和服务错误场景。
- `/context` 携带当前 mode/style，比例计算正确且不使用上一轮 usage。
- `/start` 对 invalid/bound/服务降级展示正确入口。
- 所有新增菜单遵守 chat/session token 绑定和 active turn 并发限制。

阶段回归命令：

```bash
uv run python -m pytest agent_service/tests -q
uv run python -m pytest channels/tests/test_telegram.py channels/tests/test_telegram_runner.py -q
uv run python -m pytest channels/tests rpg_core/tests agent_service/tests rpg_data/tests -q
```

如实现触及主 Agent、Context 或 session manager，再补跑：

```bash
INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q
```

### 6.9 P2 完成条件

- 新用户只通过 Telegram 可以选择 session、完成角色绑定并开始首轮游玩。
- 已有用户可以按 title 分页切换 session，并在创建后明确决定是否切换。
- 场景、overall 摘要和下一轮 Context 占用均可只读查看，且不引入第二套业务真源。
- Telegram 中不存在管理 Story、角色卡、状态表、RP Module 或主模型的写入口。
- P2 契约、client、Telegram 和完整相关回归全部通过。

---

## 7. 全阶段通用实现约束

### 7.1 分层

- `channels/telegram/` 只负责 Telegram update、菜单、临时状态和渲染。
- `agent_service/client.py` 是 Telegram 访问业务能力的唯一客户端入口。
- Agent service 可以组装只读数据，但不得把 FastAPI、Telegram 或 callback 概念放入 `rpg_core`/`rpg_data`。
- `RPGGameAgent` 继续只作 composition root/public facade；本计划不向 `agent.py` 回填渠道行为。
- send/send_stream 继续复用现有 Turn pipeline；Telegram 不复制角色校验、Context 门禁、transaction、commit 或 discard。

### 7.2 数据与隐私

- 不记录 Telegram token、callback 完整 token、快捷回复正文、Composer prompt、角色详情全文或 assistant 私有推理。
- `verbose_logging` 规则不因 Telegram 改变；内部随机 sample/权重不进入 UI。
- Telegram 临时状态随进程销毁，不落 SQLite、文件或运行目录。
- assistant 带 `<rp-narration>` / `<rp-character>` 标签的 content 仍是真源；Telegram renderer 只做展示转换，不回写 message metadata。

### 7.3 错误语义

- SSE 业务错误使用 `error_code`；Telegram 根据已知 code 给友好提示，未知 code 使用稳定通用提示。
- 不把 `error_code` 拼进玩家正文，不把 HTTP `status_code` 当业务错误码。
- `MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED` 提示玩家查看 `/context`、使用 `/compact` 或回到 WebUI 切换模型；不自动压缩。
- 渠道发送失败与 Agent turn 失败分开记录：Agent 已 commit 后不得因 Telegram 投递失败回滚。

### 7.4 Bot 菜单

最终 Telegram 本地一级命令建议为：

```text
/start    首次使用与主入口
/play     打开游玩面板
/quick    快捷回复
/mode     选择对话模式
/style    选择叙事风格
/sessions 会话选择
/role_bind 角色选择
/scene    当前场景
/summary  剧情摘要
/context  Context 占用
```

Agent 动态命令继续追加并去重。若本地命令与 Agent 命令同名，以 Telegram 本地交互入口优先，但最终业务动作仍按本计划调用 AgentClient。

## 8. 明确延期项

以下能力不属于本轮三个阶段，后续若需要应单独立项：

- Telegram 历史分页、retry、edit、truncate、单条删除和分支回滚。
- 主 Agent LLM 选择与 session override。
- 普通状态表查看/编辑、scene 编辑和状态 pin。
- RP Module 启停、稀疏配置及 Narrative Outcome 权重管理。
- Story、角色卡、世界书、叙事风格和快捷回复的创建/编辑/挂载。
- summary batch 浏览、调试 Context 全层内容和工具调用详情。
- Telegram/WebUI 之间同步 Composer UI 临时偏好。
- Telegram webhook、横向多实例共享 callback/active turn 状态。

如果未来部署多个 Telegram 进程共同消费同一 bot，当前内存 action/active turn 设计必须另行升级为有 TTL 的共享状态；本轮单 bot 单进程模型不提前引入该复杂度。

## 9. 最终验收场景

三个阶段全部完成后，以下端到端路径必须成立：

1. 玩家发送 `/start`，看到当前 session 和角色状态。
2. 未绑定角色时通过按钮选择，绑定动作沿 Agent `/role_bind` 链路完成并收到一次性 first message。
3. 玩家在 `/play` 选择 OOC/GM/IC 模式与 Story 已挂载叙事风格。
4. 玩家可直接发送正文，或选择快捷回复、预览并确认发送。
5. 生成开始后立即看到占位消息；重复输入和并发 session 输入收到忙碌提示，不进入 AgentMailbox 排队。
6. 正常 DONE 后回复写入历史，Telegram 最终消息无重复、无残留按钮。
7. 玩家可查看当前场景、overall 摘要和下一轮 Context 占用。
8. 玩家可按 title 分页选择 session，创建新 session 并决定是否立即切换。
9. 切换 session 后角色和 Composer 状态按目标 session 重新解析，不串用旧 callback 或活动 turn。
10. Telegram/Agent/网络任一层失败时，不产生误提交、重复提交、错误 pin 或虚假的“已停止”。
