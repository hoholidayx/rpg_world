# 聊天历史 CRUD 设计计划

## 概述

构建一套由 agent 自身维护的聊天历史管理能力，让用户可以用自然语言描述历史编辑需求，先看到明确的编辑预览，再确认或取消，最后才真正修改当前 session 的聊天历史。

LLM 只负责理解意图并生成待确认的编辑计划。真正的历史修改必须通过核心 session API 执行，这样才能保证内存中的历史、`history.jsonl`、turn 元数据以及各渠道行为始终一致。

## 目标

- 支持自然语言请求，例如删除误发消息，或删除某一轮引入错误设定的对话。
- 历史状态由 agent/session 层统一维护，而不是由 Telegram、API、CLI 或 WebUI 客户端各自维护。
- 所有破坏性编辑都必须经过二次确认。
- Telegram 需要提供类似当前 session picker 的交互式确认菜单。
- 删除后的内容仍然可恢复：在 cold history 中打删除标记，而不是直接抹掉原始记录。

## 存储语义

- `history.jsonl` 是当前 session 的活动历史。
- agent 内存历史与 `history.jsonl` 必须通过 `SessionManager` 一起更新。
- `history_cold.jsonl` 继续作为长期审计数据源。
- 当活动历史中的记录被删除时，需要在 `history_cold.jsonl` 中为对应记录写入 `mark_del: true`。
- cold history 中的原始内容和原始元数据都要保留。
- 如果 cold history 中存在非 JSON 行或损坏行，重写时应原样保留。

## 核心 Manager 设计

应当给 `SessionManager` 增加正式的历史编辑 API，而不是复用通用文件工具去直接改历史文件。

建议增加的 API：

- `list_history(...)`：返回消息或 turn 的摘要，包含 `hid`、`turn_id`、`seq_in_turn`、`role` 和内容预览。
- `preview_history_edit(plan)`：校验请求的编辑操作，返回将受影响的消息或 turn。
- `apply_history_edit(plan)`：修改内存历史，并持久化到 `history.jsonl`。
- `mark_cold_history_deleted(hids)`：原子重写 cold history，为匹配的记录增加 `mark_del: true`。

每次实际执行编辑后，都需要：

- 调用 `replace_history(..., persist=True)` 或等价的集中持久化入口。
- 重建 turn 相关 bookkeeping 和 `next_turn_id`。
- 如果删除导致先前的 story cursor 越界，需要把 `last_story_turn_index` 收缩到合法范围。

## 编辑计划模型

使用一份结构化的待确认编辑计划，并由 agent 保存。

建议字段：

- `token`：短确认 token。
- `workspace`：绑定的 workspace。
- `session_id`：绑定的 session。
- `reason`：面向用户展示的编辑原因。
- `operations`：已经过校验的编辑操作。
- `preview`：面向用户展示的受影响历史摘要。
- `created_at`：用于 TTL 过期判断。

第一版支持的操作：

- `delete_messages`：删除指定 `hid` 的消息。
- `delete_turns`：先把选中的 `turn_id` 展开成具体 `hid`，再执行删除。
- `replace_message_content`：替换某个 `hid` 的内容，同时保留 `role`、`hid`、`turn_id` 和 `seq_in_turn`。

`insert_message_after` 先不做，等后续做专门的历史管理 UI 或确实有明确需求时再加，因为插入操作更容易破坏 turn 结构。

## LLM Tools

在主 agent 上注册专用的历史管理工具。

- `history_search(query, limit)`：让 LLM 查找候选消息或候选 turn。
- `history_preview_edit(operations, reason)`：创建待确认编辑计划，并返回预览和 token。
- `history_apply_edit(token)`：执行已经确认的编辑计划。
- `history_cancel_edit(token)`：取消待确认的编辑计划。

关键约束：

- 不能允许 LLM 直接通过 `write_file` 修改 `history.jsonl`。
- 历史 CRUD 必须统一走 `SessionManager`，否则内存状态和磁盘状态会漂移。

## 确认状态设计

二次确认不能依赖持久化的 tool records。

当前聊天历史只会持久化最终的 user/assistant 消息。tool call 记录只保留在当前 turn 的结果对象或 UI 元数据里，不会落到 `history.jsonl`。因此，完整的待确认编辑计划必须保存在 agent 管理的状态里，而不能只依赖 LLM 可见历史。

待确认计划的规则：

- token 绑定 `workspace + session_id`。
- token 有较短 TTL，默认 10 分钟。
- 如果在 `switch_session()` 之后去确认另一个 session 的 token，必须失败。
- 同一个 token 第一次成功执行后，再次确认必须失败。
- 进程重启后，待确认计划视为失效，用户需要重新发起编辑请求。

## 用户流程

自然语言编辑流程：

1. 用户提出删除或修改历史的请求。
2. LLM 调用 `history_search` 找出候选内容。
3. LLM 调用 `history_preview_edit` 生成具体编辑计划。
4. agent 回复受影响消息的预览和确认选项。
5. 用户确认或取消。
6. 核心 manager 执行编辑，并返回结果摘要。

CLI/API 确认方式：

- `/history_confirm <token>`：执行待确认的编辑计划。
- `/history_cancel <token>`：取消待确认的编辑计划。

Telegram 确认方式：

- 当 assistant 回复中包含待确认的历史编辑 token 时，Telegram 发送 inline keyboard：
  - 确认删除/编辑
  - 取消
- Telegram 的 callback data 应使用短 callback token，并映射到核心 pending token，复用现有 session picker 的设计思路。
- Telegram 侧只调用 agent 命令路径，例如 `/history_confirm <token>` 或 `/history_cancel <token>`。
- Telegram 侧不能直接修改历史。

## 命令设计

在命令分发器中增加以下命令：

- `/history`：展示当前 session 最近历史摘要。
- `/history_search <query>`：搜索当前活动历史，返回候选 `hid` 或 `turn_id`。
- `/history_confirm <token>`：执行待确认编辑。
- `/history_cancel <token>`：取消待确认编辑。

## 对 Memory 和 Summary 的影响

第一版不要自动修改 summary、story memory 或向量索引。

历史编辑执行完成后，返回文本中应明确提示：派生出来的 memory 数据可能仍然保留旧内容，如需刷新可显式执行 `/memory_reindex`，或者后续再增加专门的历史修复命令。

## 测试计划

核心 session 测试：

- 删除一条消息，验证活动历史和 `history.jsonl` 同步更新。
- 删除一个 turn，验证 turn 元数据被正确重建。
- 验证被删除的 cold history 记录被写入 `mark_del: true`。
- 验证未删除的 cold history 记录保持不变。
- 替换消息内容时，`hid`、`role`、`turn_id`、`seq_in_turn` 保持稳定。
- 当当前 turn 数变少时，story-memory cursor 会被收缩到合法范围。

历史工具测试：

- preview 能创建 pending token，但不会实际修改历史。
- confirm 能执行 pending plan。
- cancel 能移除 pending plan。
- 过期 token、重复 token、错误 session 的 token 都会失败。
- 即使 tool records 没有持久化，确认流程依然可用。

Telegram 测试：

- 待确认历史编辑会触发 inline 的确认/取消菜单。
- 点击确认会分发 agent 的 confirm 命令。
- 点击取消会分发 agent 的 cancel 命令。
- 过期或未知 callback token 会返回清晰提示。

API/CLI 测试：

- `/chat/command` 可以执行 `/history_confirm` 和 `/history_cancel`。
- `/chat/commands` 会返回新增的历史管理命令。

## 实现顺序

1. 给 `SessionManager` 增加历史编辑原语，并补测试。
2. 在主 agent 上增加 pending plan store 和历史管理 tools。
3. 增加命令分发器入口。
4. 增加 Telegram inline 二次确认流程。
5. 增加 API/CLI 契约测试。
6. 增加面向用户的 prompt/tool 描述，支持自然语言历史编辑。
