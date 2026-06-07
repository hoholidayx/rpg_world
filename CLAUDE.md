# rpg_world

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。

## 启动

```bash
# 统一启动（读取 channels.json，按配置启动模块）
uv run python -m rpg_world.run

# 仅启动 API（开发，自动重载）
MODULES=api uv run python -m rpg_world.run

# 或直接 uvicorn
uv run uvicorn rpg_world.api.main:app --reload --reload-dir rpg_world --host 127.0.0.1 --port 8000

# WebUI 开发服务器（端口 5173，代理 /api → 后端）
cd rpg_world/webui && npx vite

# 独立 CLI（无 API / Telegram，直接 LLM 对话）
uv run python -m rpg_world.channels.cli.repl [--model gpt-4o] [--session-id mygame]

# 验证导入
uv run python3 -c "from rpg_world.rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── run.py                        # 统一启动入口（Launcher）
├── channels.json                 # 模块配置（各渠道开关/参数）
├── channels/                     # 多渠道适配器
│   ├── base.py                   #   ChannelAdapter 抽象基类
│   ├── config.py                 #   ChannelsSettings 配置加载
│   ├── runner.py                 #   ChannelRunner（生命周期管理）
│   ├── cli/                      #   CLI 渠道（Rich + prompt_toolkit）
│   │   ├── adapter.py            #     CLIAdapter
│   │   └── repl.py               #     独立入口
│   ├── telegram/                 #   Telegram 渠道（python-telegram-bot）
│   │   ├── __init__.py
│   │   └── adapter.py            #     TelegramAdapter（支持 stream/non-stream）
│   └── tests/                    #   渠道测试（mock LLM，无需 API key）
│       ├── conftest.py           #    共享 fixture（FakeAgent, FakeBot）
│       ├── test_base.py          #    基类测试 12 项
│       ├── test_cli.py           #    CLIAdapter 测试 11 项
│       ├── test_manager.py       #    AgentManager 测试 9 项
│       └── test_telegram.py      #    Telegram 测试 16 项
├── rpg_core/                     # 核心逻辑（无框架依赖）
│   ├── agent/                    #   LLM Agent 引擎
│   │   ├── agent.py              #     RPGGameAgent — 主入口（send/send_stream/single_turn）
│   │   ├── agent_types.py        #     结构化类型 + QueueItem 队列类型
│   │   ├── manager.py            #     AgentManager 单例（统一 agent 缓存）
│   │   ├── base_provider.py      #     LLMProvider 抽象基类
│   │   ├── command.py            #     CommandDispatcher — 斜杠命令分发器
│   │   ├── loop.py               #     chat loop（LLM 往返 + tool calling）
│   │   ├── openai_provider.py    #     OpenAI/DeepSeek LLM 调用封装
│   │   ├── prompt.py             #     PromptManager — 系统提示词
│   │   ├── stats_formatter.py    #     LLM 统计格式化
│   │   ├── tokenizer.py          #     TokenCounter 抽象
│   │   ├── sub_agents/           #     子 Agent 系统
│   │   └── tools/                #     工具系统
│   ├── scene/                    # 场景状态（时间/地点/属性）
│   ├── context/                  # 5 层 RPG 上下文构建
│   ├── jinja/                    # Jinja2 模板
│   ├── character/                # 角色卡（JSON）
│   ├── lorebook/                 # 世界书（JSON）
│   ├── status/                   # 状态表（CSV）
│   ├── memory/                   # 记忆存储
│   ├── summary/                  # 对话摘要
│   ├── models/                   # Pydantic 数据模型
│   ├── settings.py               # Settings 单例
│   └── utils/
│       ├── manager_base.py       #   BaseManager（注册 FileWatcher）
│       ├── watcher.py            #   FileWatcher（watchdog 文件监控）
│       └── path_utils.py         #   路径解析
├── api/                          # FastAPI 应用
│   ├── main.py                   #   入口 + CORS + lifespan（条件启动渠道）
│   ├── deps.py                   #   管理器单例
│   ├── logger.py                 #   API 日志配置
│   ├── settings.json             #   API 级配置
│   ├── settings.py               #   ApiSettings 单例
│   └── routers/
│       ├── character.py          #   CRUD /api/v1/characters
│       ├── lorebook.py           #   CRUD /api/v1/lorebook
│       ├── status.py             #   CRUD /api/v1/status
│       ├── chat.py               #   send/stream(SSE)/command/history
│       ├── sessions.py           #   list/create/delete/clone
│       └── workspace.py          #   list/get_active/switch
├── webui/                        # Vue 3 SPA（Ant Design Vue + Pinia）
│   ├── settings.json
│   ├── vite.config.js            # 代理 /api → 后端
│   ├── run_dev.sh
│   └── src/
│       ├── main.js
│       ├── App.vue               # 根组件（主题配置）
│       ├── router/index.js
│       ├── layouts/              # DashboardLayout（侧边栏 + 工作区选择器）
│       ├── stores/               # session / theme / workspace
│       ├── composables/          # useCRUD / useCommands
│       ├── api/                  # Axios 客户端
│       └── views/                # Chat, Character, Lorebook, Status, Overview
└── data/                         # 数据文件
    └── {workspace}/
        ├── character/
        ├── lorebook/
        └── sessions/{id}/
            ├── history.jsonl
            ├── history_cold.jsonl
            ├── story_memory.json
            └── rpg_summaries.json
```

## 统一进程架构

rpg_world 采用 **单进程 CS 架构**：所有模块（API / Telegram / CLI）运行在同一个
进程中，共享同一 `AgentManager` 实例池，避免多进程文件冲突。

```
进程 (uvicorn / run.py)
├── AgentManager 单例
│   ├── RPGGameAgent 实例池（按 session_id + api_key 缓存）
│   ├── FileWatcher（watchdog 文件监听）
│   └── BaseManager 缓存（character/lorebook/status）
├── FastAPI 路由（webui + REST API）
├── Telegram 长轮询（channels/telegram/）
└── CLI REPL（channels/cli/）— 可选
```

### 配置（`channels.json`）

与 `settings.json`（agent 配置/数据路径）分离，`channels.json` 专门控制模块启停：

```json
{
  "modules": {
    "api": { "enabled": true, "port": 8000, "host": "127.0.0.1", "reload": false },
    "telegram": { "enabled": true, "bot_token": "xxx", "streaming": true },
    "cli": { "enabled": false }
  }
}
```

通过 `MODULES=api,telegram uv run python -m rpg_world.run` 或
`channels.json` 中 `modules.{name}.enabled` 控制。

### AgentManager（`rpg_core/agent/manager.py`）

进程内单例，统一管理 `RPGGameAgent` 的创建与缓存：

```python
from rpg_world.rpg_core.agent.manager import AgentManager

agent = AgentManager.get_or_create(session_id="mygame")
```

所有模块通过同一个 `AgentManager` 获取 agent，确保 FileWatcher 只初始化一次、
BaseManager 缓存一致。

### ChannelAdapter 基类（`channels/base.py`）

多渠道抽象基类，所有渠道（CLI / Telegram / Future）遵循同一接口：

| 方法 | 职责 |
|---|---|
| `start()` | 启动长连接 |
| `stop()` | 优雅关闭 |
| `send_text()` | 发送完整文本 |
| `send_delta()` | 可选流式增量 |
| `_handle_message()` | 统一消息管线（session 切换 → agent.send → 发送回复） |

命令分发统一由 agent 的 `_send_impl()` / `_send_stream_impl()` 处理，
不放在渠道层，确保所有渠道行为一致。

### 消息队列（`agent.py` 内部）

`RPGGameAgent` 使用 `asyncio.Queue` 串行化所有入口：

```
send(A)     → put QueueItem → [consumer] → _send_impl(A)    → future.set_result → send(A) 返回
send(B)     → put QueueItem → [queue]     → ...等待...
/compact    → put QueueItem → [queue]     → ...等待...
                                   → _send_impl(B)    → future.set_result → send(B) 返回
                                   → execute_command  → future.set_result → 命令返回
```

三种工作类型常量：`QueueKind.SEND` / `QueueKind.SEND_STREAM` / `QueueKind.COMMAND`。

## 关键设计

### 5 层 RPG 上下文（`context/builder.py` → `rpg_context.py`）

LLM 调用时的消息构建顺序，按变更频率排列以优化 prefix cache：

| 层 | role | 内容 | 变更频率 |
|---|---|---|---|
| [0] Fixed | system | 系统提示 + 世界书 + 角色卡 | ★ 几乎不变 |
| [1] Persistent Memory | system | 常驻记忆 | ★ 离线更新 |
| [2] Summary | system | 历史摘要（条件触发） | ★☆ 少量 |
| [3..N] Hot History | mixed | 最近 N 轮对话 | ★★☆ 每轮追加 |
| [N+1] Story Memory | system | 剧情细节 | ★★☆ 累积 |
| [N+2] Recalled Memory | system | 动态召回 | ★★★ 动态注入 |
| [N+3] Status Tables | system | 游戏状态 CSV 表 | ★★★★ 高频变化 |
| [N+4] User Message | user | `[scene]` + 用户输入 + 前后缀 | 总是新的 |

上下文基于 Jinja2 模板（`rpg_core/jinja/`），通过 `RPGContext.to_messages()`
展平为 OpenAI-compatible 消息列表。

### Agent 数据流

```
agent.send(user_input)
  → CommandDispatcher 拦截斜杠命令（是则旁路 LLM，不入历史）
  → StatusSubAgent.update() 预更新状态表（~1-2K tokens 避免主 loop round-trip）
  → SceneTracker.get_context() → [scene] 嵌入 user message
  → _build_transformed_context() → builder.build() → RPGContext.to_messages()
  → run_chat_loop(provider, tool_registry, messages)
    → LLM 可能调工具（scene.set_time / set_attr / file tools）
    → 每轮记录 TurnStats + CallRecord
  → 回复写入 _history + history.jsonl + history_cold.jsonl
  → 返回 AgentReply（含 text + tool_records + stats）
```

### 子 Agent 系统（`agent/sub_agents/`）

| 子 Agent | 职责 | 执行时机 |
|---|---|---|
| **StatusSubAgent** | 状态表预更新 | 主 LLM 调用之前，避免 tool calling round-trip |
| **MemorySubAgent** | 记忆总结/召回/剧情持久化 | `process()` 由 CommandDispatcher 或自动触发 |

支持独立 LLM 模型（如 gpt-4o-mini 处理状态表），通过 `SubAgentContext` 获取世界书 + 角色卡上下文。

### 斜杠命令系统（`agent/command.py`）

| 命令 | 来源 | 功能 |
|---|---|---|
| `/clear` | 内置 | 清空对话历史 |
| `/reload` | 内置 | 重新加载 RPG 数据 |
| `/context` | 内置 | 查看上下文结构和 token 用量 |
| `/compact [N] [K]` | MemorySubAgent | 压缩最老的 N 轮对话为摘要 |
| `/sessions` | 内置 | 列出所有会话 |
| `/session-create <id>` | 内置 | 创建新会话 |
| `/session-switch <id>` | 内置 | 切换到指定会话 |

命令统一由 agent 内部的 `CommandDispatcher` 处理，不经过 LLM，不入对话历史。
所有渠道（CLI / API / Telegram）共享同一逻辑。

### REST API

```
GET    /api/v1/{resource}           — 列表
POST   /api/v1/{resource}           — 创建
GET    /api/v1/{resource}/{name}     — 详情
PUT    /api/v1/{resource}/{name}     — 更新
DELETE /api/v1/{resource}/{name}     — 删除
```

Chat API：

```
GET    /api/v1/chat/history          — 获取历史会话
POST   /api/v1/chat/send             — 发送消息（缓冲回复）
POST   /api/v1/chat/stream           — 发送消息（SSE 流式回复）
POST   /api/v1/chat/command          — 执行斜杠命令
```

- Agent 实例通过 `AgentManager` 统一管理
- API Key 通过 `X-OpenAI-Api-Key` header 传递
- SSE 流式格式：`data: {json}\n\n`

### 对话历史持久化

- `history.jsonl` — 主文件，compact 时截断
- `history_cold.jsonl` — 冷备份，只追加永不截断
- `story_memory.json` — 剧情记忆（FileWatcher）
- `rpg_summaries.json` — 对话摘要（FileWatcher）

所有会话数据文件集中在 `{workspace_root}/sessions/{session_id}/` 下。

### Loader + Manager + BaseManager 模式

每个数据域（character/lorebook/status）遵循：

1. **Loader** — 纯文件 I/O
2. **Manager** — 继承 `BaseManager`，持有 `self.data` 缓存
3. **BaseManager** — 向 `FileWatcher` 注册数据目录
4. **FileWatcher** — watchdog Observer，500ms 防抖

### 结构化类型系统（`agent/agent_types.py`）

| 类型 | 用途 |
|---|---|
| `LLMUsage` | token 消耗（含 cache hit/miss） |
| `LLMResponse` | content + tool_calls + usage + model + reasoning |
| `CallRecord` | 单次 LLM 调用快照 |
| `TurnStats` | 一次 send() 的 LLM 调用聚合 |
| `AgentStreamEvent` | 流式事件（TEXT/THINKING/TOOL_CALL/DONE/ERROR） |
| `QueueItem` | 消息队列工作项 |
| `QueueKind` | 工作项类型常量（SEND / SEND_STREAM / COMMAND） |

### 前端注意事项

- **DashboardLayout** 侧边栏含工作区选择器 + 会话选择器
- `useCRUD` composable 适用于 character/lorebook CRUD 页面
- `ChatView` 使用 SSE 流式渲染（`streamMessage()` 基于 fetch + ReadableStream）
- 中文路径在前端 axios 层用 `encodeURIComponent()` 编码
- 暗色模式：`data-theme` 属性控制，Pinia store 持久化
- Vite 开发代理：`/api` → `http://127.0.0.1:8000`

### 数据格式

- **Character/Lorebook**: JSON（name, enable, content, tags, 自定义字段）
- **Status**: CSV，UTF-8 BOM（`utf-8-sig`），Excel 兼容
- **会话历史**: JSONL（每行一个 message 对象）
- **摘要**: JSON 数组
- **剧情记忆**: JSON 数组（含 metadata）
