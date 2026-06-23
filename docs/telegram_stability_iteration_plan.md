# Telegram 渠道稳定性迭代开发方案

> 范围限定：本方案只覆盖 `rpg_world` 工作区内的 Telegram 渠道稳定性建设，不调整其他工作区代码，也不改动运行数据。

## 目标与优先级

本轮迭代优先保障真实 Telegram 长轮询入口稳定可用。产品路线已调整为 WebUI 承载沉浸式 RP 主体验，Telegram 承载轻量入口、App 推送、快速回复和兜底交互；因此 Telegram 稳定性建设的目标是不因会话、流式输出、异常分支或配置问题中断辅助触达体验。

优先级从高到低如下：

1. **真实 Telegram 长轮询可靠**：启动、退出、重连边界、SDK 异常日志和请求超时必须可诊断。
2. **会话管理可靠**：默认会话、显式切换、会话菜单、二段式创建和取消流程必须一致。
3. **stream / non-stream 可靠**：流式编辑、最终回复、长文本分块、限流和非流式完整回复都要有明确兜底。
4. **异常回复可靠**：用户可见错误要友好，日志要保留足够上下文，不能静默失败。
5. **命令菜单可靠**：Telegram 菜单命令与后端命令列表同步，命令别名和 bot mention 规范化稳定。
6. **运行配置可靠**：`channels.json` 与 `ChannelsSettings` 的默认值、类型转换和无效配置处理可预测。

## 当前基线

当前实现已经具备以下基础能力：

- `TelegramAdapter.start()` 使用 `python-telegram-bot` 的 `Application` 和 `updater.start_polling()` 启动长轮询。
- `TelegramAdapter.send_delta()` 支持流式首条发送、后续编辑和最终编辑。
- `TelegramAdapter.send_text()` 支持非流式完整回复与 Telegram HTML 渲染分块。
- `TelegramSessionFlow` 承担 `/sessions`、无参数 `/session_switch`、无参数 `/session_create`、`/cancel` 和 callback 会话切换。
- `ChannelsSettings` 已暴露 Telegram token、streaming、proxy、编辑节流、请求超时和 workspace 配置。
- `channels/tests/test_telegram.py` 已覆盖普通消息、命令规范化、会话菜单、二段式创建、长文本分块、stream 编辑和菜单配置等核心路径。

## 迭代拆分

### P0：稳定性护栏与可观测性

**目的**：先补齐真实长轮询运行时的异常边界，让问题能被定位且不会造成无回复。

- 在 Telegram 请求封装层统一处理超时、限流、`BadRequest`、网络异常和未知异常。
- 为 `send_text()`、`send_delta()`、`_send_session_picker()`、`_configure_bot_commands()` 增加一致的日志字段：`chat_id`、`action`、`message_id`、文本预览、配置参数。
- 明确用户可见错误策略：
  - agent 普通消息异常：回复“处理消息失败，请稍后重试。”
  - 命令异常：回复“命令执行失败: <command>”
  - 会话流程异常：回复“会话操作失败，请重试或发送 /cancel。”
  - Telegram API 发送失败：记录日志，不再递归发送错误提示，避免错误风暴。
- 增加启动配置摘要日志，启动失败时明确 token 缺失、代理配置或 SDK 初始化失败。

**验收标准**：

- 单元测试覆盖 `send_text()` 请求失败不抛出到消息处理主链路。
- 单元测试覆盖 agent 消息异常时用户收到友好错误。
- 单元测试覆盖 session flow 异常时用户收到友好错误或可取消提示。
- `MODULES=telegram uv run python -m rpg_world.run` 在缺 token 时给出明确错误日志并退出或跳过启动。

### P1：会话管理闭环

**目的**：保障 Telegram chat 与 RPG session 的映射稳定，避免切换后串会话或创建流程卡死。

- 梳理并固化 chat 绑定规则：
  - 默认会话：`telegram_<chat_id>`。
  - 成功 `/session_switch <id>` 后 pin 到该 chat。
  - callback 菜单切换成功后 pin 到该 chat。
  - `/session_create <id>` 成功后是否自动 pin，需要产品决策并写入测试；建议自动 pin 到新会话。
- 为二段式创建增加超时提示和清理策略，避免 pending 状态长期占用普通消息。
- session id 校验失败时回复具体规则：仅字母、数字、下划线，长度不超过 64。
- 会话菜单展示当前会话、空列表、过长列表分页或截断策略。
- 避免渠道层直接依赖过多 agent 私有字段；如需 workspace/current session，优先补公开只读属性。

**验收标准**：

- 单元测试覆盖 callback 切换后后续普通消息使用新 session。
- 单元测试覆盖 `/session_create <id>` 成功后 pin 行为。
- 单元测试覆盖二段式 pending 超时后的普通消息不再被消费。
- 单元测试覆盖空会话列表和超长会话列表展示。

### P2：stream / non-stream 输出可靠性

**目的**：让 Telegram 输出在 Markdown、长文本、限流和最终回复场景下稳定。

- 完整校验 `send_delta()` 的状态机：首包发送、节流跳过、中间编辑、最终编辑、最终 fallback、发送失败清理。
- 对 Telegram 4096 限制建立策略：
  - 非流式继续按 HTML 渲染后分块。
  - 流式内容超过单条限制时，停止编辑旧消息并追加新消息，或最终 fallback 到分块发送。
- 明确 `BadRequest: Message is not modified`、`RetryAfter`、超时和网络错误的差异处理。
- 增加 stream 关闭配置验证：`streaming=false` 时普通消息只走 `send_text()`，不创建 `_stream_buf`。
- 对 Markdown 渲染增加回归样例：表格、列表、标题、链接、代码、HTML 特殊字符、未闭合 Markdown。

**验收标准**：

- 单元测试覆盖 `streaming=false` 的完整消息链路。
- 单元测试覆盖 stream 最终回复超过 Telegram 单条限制的兜底。
- 单元测试覆盖 `RetryAfter` 不破坏后续消息。
- 单元测试覆盖 HTML 特殊字符不会破坏 parse mode。

### P3：命令菜单与命令管线可靠性

**目的**：保证 Telegram 菜单命令、用户输入命令和后端命令行为一致。

- 给 Telegram 菜单命令建立过滤规则：去掉前导 `/`、移除 bot mention、只保留 Telegram 允许的命令名字符。
- 菜单命令描述过长时截断并记录日志。
- 后端命令列表同步失败不影响长轮询启动。
- 将 Telegram 专属交互命令和 agent 命令分界写入注释和测试：
  - Telegram 专属：`/start`、`/sessions`、无参数 `/session_switch`、无参数 `/session_create`、`/cancel`。
  - 交给 agent：带参数的 session 命令、其他后端命令。
- 覆盖未知命令、空命令、带 bot mention 命令和大小写命令。

**验收标准**：

- 单元测试覆盖非法后端命令名不会导致 `set_my_commands` 失败。
- 单元测试覆盖菜单同步失败后 adapter 仍继续启动。
- 单元测试覆盖 Telegram 专属命令不会误进 agent。

### P4：运行配置与启动体验

**目的**：让 `channels.json` 配置错误可预测、可诊断，便于真实部署。

- 为 `ChannelsSettings` 增加健壮类型转换：非法 int/bool 时回退默认值并记录警告。
- token 为空或仍为 `YOUR_BOT_TOKEN` 时拒绝启动 Telegram，并给出清晰提示。
- 给 `proxy`、`request_timeout_ms`、`stream_edit_interval_ms`、`stream_edit_min_chars` 写明推荐值与边界。
- 增加配置文档：真实 Telegram 启动步骤、仅 Telegram 启动、API+Telegram 共享 AgentManager 启动、常见故障排查。
- 保持 `workspace` 只来自 `channels.json`，不写回 `settings.json`。

**验收标准**：

- 单元测试覆盖非法配置回退默认值。
- 单元测试覆盖 token 缺失时 runner 不进入长轮询。
- README 或专门运行手册包含 Telegram 部署检查清单。

## 建议开发顺序

1. **第一轮 PR：P0 + 最小 P1**
   - 只改异常边界、用户可见错误、启动 token 校验、会话 pin 的显式测试。
   - 目标是降低真实 Telegram 运行中“无回复、卡死、难定位”的风险。
2. **第二轮 PR：P2 stream/non-stream**
   - 聚焦输出状态机、长文本和 Telegram API 限制。
   - 不同时改命令和配置，降低回归面。
3. **第三轮 PR：P3 命令菜单**
   - 聚焦菜单命令过滤、描述截断、专属命令边界。
4. **第四轮 PR：P4 配置与文档**
   - 聚焦 `channels.json` 健壮性、部署手册和运维检查清单。

## 测试矩阵

每轮至少运行：

```bash
uv run python -m pytest rpg_world/channels/tests/test_telegram.py -q
uv run python -m pytest rpg_world/channels/tests rpg_world/rpg_core/tests rpg_world/api/tests -q
```

真实 Telegram smoke test（需要有效 bot token，不能纳入 CI 强制项）：

```bash
MODULES=telegram uv run python -m rpg_world.run
```

手工验证清单：

- 发送普通中文消息，确认收到回复。
- 发送 `/start`，确认欢迎语。
- 发送 `/sessions`，确认展示当前会话和按钮。
- 点击会话按钮，确认后续普通消息进入新会话。
- 发送 `/session_create` 后输入非法 session id，确认提示规则。
- 发送 `/cancel`，确认 pending 流程结束。
- 发送一条会触发长回复的消息，确认 stream 编辑不报错。
- 将 `streaming` 改为 `false`，确认完整回复一次性发送并可分块。
- 临时配置错误代理或极短 timeout，确认日志可诊断。

## 风险与约束

- 不引入真实 Telegram 网络依赖到自动化测试；所有外部调用继续使用 mock。
- 不改动 `data/` 下运行数据，不把会话历史、向量库、WAL/SHM 纳入提交。
- 不破坏 `run.py` 统一启动和 `AgentManager` 单例边界。
- Telegram 是轻量触达和兜底入口；沉浸式聊天与复杂 RP UI 优先进入 Play WebUI。
- 本方案只保障 Telegram 作为可靠渠道，不把复杂 dashboard、状态编辑、战斗面板、地图/时间线等能力塞入 Telegram。
