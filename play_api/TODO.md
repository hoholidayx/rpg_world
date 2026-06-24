# Play API 后续实现 TODO

Play API 当前仍有部分面向 Play WebUI 的脚手架端点，后续需要接入真实后端能力：

- `routers/workspace.py`：工作区列表仍返回固定示例数据。
- `routers/scene.py`：当前场景仍返回默认占位内容。

已接入 Agent Service 的路由：

- `routers/chat.py`：通过 `agent_service.client.AgentClient` 发送和流式接收对话。
- `routers/commands.py`：通过 Agent Service 获取命令列表。
- `routers/sessions.py`：通过 Agent Service 获取会话列表和历史。
