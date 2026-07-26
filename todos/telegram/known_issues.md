# Telegram 已知问题

更新时间：2026-07-26

本文件登记 Telegram 渠道审查中已经确认、但不在本批修复范围内的问题。以下两项
仅作为已知风险记录，不得因本批其它 Telegram 稳定性整改而被视为已修复。

## TG-KI-001：DEBUG 持久日志泄露 Bot token 与完整消息

- 严重度：P0
- 状态：已确认，待修复
- 本批处理：不修

### 现象与证据

`channels/settings.yaml` 默认把渠道进程日志级别设为 `DEBUG`，
`commons/process_logging.py` 又把标准库 root logger 全量桥接到滚动文件。
Telegram 进程构建 `python-telegram-bot` Application 后，依赖库的 DEBUG/INFO 日志会包含：

- 带完整 Bot token 的 Bot API/base file URL；
- Bot API 调用参数和返回值，其中可能包含完整玩家输入、回复和 callback 数据；
- `httpx` 请求 URL，其中同样包含 Bot token。

渠道自身还会记录输入/输出预览，并原样记录可能带用户名和密码的 proxy URL。日志默认写入
`logs/telegram.log`，按 20 MB 滚动并保留压缩归档，因此泄露不是短暂的控制台可见性问题。

### 风险

获得日志或归档读取权限的人可接管 Bot；完整 RP/OOC 内容、用户 ID、chat ID 和会话操作也可能
被长期保留。若 token 已在该日志配置下运行过，应按已暴露凭据处理。

### 后续修复要求

1. 在 Telegram Application 构建前，将 `telegram`、`httpx`、`httpcore` 等第三方 logger
   收紧到安全级别，并增加 Bot API URL 的兜底脱敏。
2. 业务日志不得记录消息正文、命令参数或含凭据的 proxy URL。
3. 日志目录和文件使用仅进程用户可读的权限，并清理历史滚动/压缩归档。
4. 增加自动化测试，断言日志中不出现 token、消息正文和 proxy credential。
5. 轮换所有可能在旧日志链路下使用过的 Bot token。

## TG-KI-002：`allow_from` 已解析但没有执行访问控制

- 严重度：P0
- 状态：已确认，待修复
- 本批处理：不修

### 现象与证据

`channels/config.py` 会把单 Bot 的 `allow_from` 解析进 `TelegramBotSettings`，配置文件也宣称支持
全局和单 Bot 访问控制；但当前运行链路存在完整断点：

- Telegram runner 没有把 `allow_from` 传给 Adapter；
- Adapter 没有访问控制参数或统一鉴权门禁；
- message、command 和 callback query handler 都会直接处理 Update；
- callback action 只绑定 chat/session，不绑定触发它的 Telegram user。

此外，顶层全局 `allow_from` 没有参与单 Bot 配置解析，缺失或类型错误会回退为 `["*"]`，属于
fail-open 行为。

### 风险

任何能找到 Bot 的 Telegram 用户都可消耗 LLM 配额，并操作 Bot 绑定的共享会话，包括查看/切换
会话、创建会话、绑定角色和执行 `/clear` 等命令。群聊中的其他成员也可点击不属于自己的按钮，
造成隐私泄露、剧情数据污染或清空。

### 后续修复要求

1. 明确 ACL 只接受稳定的数值 Telegram `user_id`，非法配置必须启动失败。
2. 明确全局和单 Bot ACL 的继承/覆盖规则；生产环境不得隐式回退为 wildcard。
3. 在 message、command、callback 的最早公共入口统一鉴权，拒绝后不得调用 Agent service。
4. Callback action 同时绑定 chat、session 和 user，避免群聊按钮被其他成员复用。
5. 增加私聊、群聊、callback、配置错误和 wildcard 策略测试。
