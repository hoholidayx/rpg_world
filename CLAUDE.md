# rpg_world

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。

## 启动

```bash
# API 开发服务器（端口 8000，自动重载）
cd rpg_world/api && bash run_dev.sh

# WebUI 开发服务器（端口 5173，代理 /api → 后端）
cd rpg_world/webui && npx vite

# 独立 Agent CLI（无 API，直接 LLM 对话）
uv run python -m rpg_world.rpg_core.agent.cli [--model gpt-4o] [--session-id mygame]

# 单次对话模式（不维持对话历史）
uv run python -m rpg_world.rpg_core.agent.cli --single-turn "环顾四周"

# 验证导入
uv run python3 -c "from rpg_world.rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── rpg_core/                    # 核心逻辑（无框架依赖）
│   ├── agent/                   # LLM Agent 引擎
│   │   ├── agent.py             #   RPGGameAgent — 主入口（send/send_stream/single_turn）
│   │   ├── agent_types.py       #   结构化类型（LLMUsage, LLMResponse, TurnStats, Streaming Events）
│   │   ├── base_provider.py     #   LLMProvider 抽象基类
│   │   ├── cli.py               #   REPL 命令行（支持流式输出）
│   │   ├── command.py           #   CommandDispatcher — 斜杠命令分发器
│   │   ├── loop.py              #   chat loop（LLM 往返 + tool calling，含流式变体）
│   │   ├── openai_provider.py   #   OpenAI/DeepSeek LLM 调用封装（非流式 + 流式）
│   │   ├── prompt.py            #   PromptManager — 系统提示词
│   │   ├── stats_formatter.py   #   LLM 统计格式化（CLI 与 API 共享）
│   │   ├── tokenizer.py         #   TokenCounter 抽象（tiktoken / DeepSeek）
│   │   ├── sub_agents/          #   子 Agent 系统
│   │   │   ├── __init__.py      #     public API 导出
│   │   │   ├── base.py          #     BaseSubAgent 抽象基类
│   │   │   ├── context.py       #     SubAgentContext（世界书 + 角色卡容器）
│   │   │   ├── memory_sub_agent.py  #  记忆子 Agent（总结/召回/剧情）
│   │   │   └── status_sub_agent.py  #  状态表预更新子 Agent
│   │   └── tools/               #   工具系统
│   │       ├── base.py          #     BaseTool 抽象
│   │       ├── registry.py      #     工具注册中心
│   │       └── file_tools.py    #     文件读写/搜索工具
│   ├── scene/                   # 场景状态（当前时间/地点/属性）
│   │   ├── tracker.py           #   SceneTracker — 纯内存状态 + CSV 持久化
│   │   └── tools.py             #   set_time / set_attr / delete_attr
│   ├── context/                 # 5 层 RPG 上下文构建
│   │   ├── builder.py           #   RPGContextBuilder（Jinja2 模板渲染）
│   │   ├── rpg_context.py       #   RPGContext 容器 + LayerType
│   │   ├── factory.py           #   build_rpg_context() 组装全栈
│   │   └── config.py            #   上下文配置
│   ├── jinja/                   # Jinja2 模板
│   │   ├── layers/              #   层级模板
│   │   │   ├── fixed_layer.jinja
│   │   │   └── summary_layer.jinja
│   │   └── modules/             #   模块模板
│   │       ├── character_card.jinja
│   │       ├── lorebook.jinja
│   │       ├── persistent_memory.jinja
│   │       ├── recalled_memory.jinja
│   │       ├── status_tables.jinja
│   │       ├── story_memory.jinja
│   │       ├── summary.jinja
│   │       ├── system_prompt.jinja
│   │       ├── user_reply_prefix.jinja
│   │       └── user_reply_suffix.jinja
│   ├── character/               # 角色卡（JSON）
│   │   ├── loader.py
│   │   └── manager.py
│   ├── lorebook/                # 世界书（JSON）
│   │   ├── loader.py
│   │   └── manager.py
│   ├── status/                  # 状态表（CSV）
│   │   ├── loader.py
│   │   └── manager.py
│   ├── memory/                  # 记忆存储
│   │   ├── persist_memory.py    #   PersistentMemoryStore（常驻记忆）
│   │   ├── story_memory.py      #   StoryMemoryStore（剧情记忆，FileWatcher）
│   │   └── recalled_memory.py   #   RecalledMemoryStore（召回记忆，运行时注入）
│   ├── summary/                 # 对话摘要
│   │   ├── store.py             #   SummaryStore（持久化 + FileWatcher）
│   │   └── compressor.py        #   SummaryCompressor（自动压缩策略）
│   ├── models/                  # Pydantic 数据模型
│   │   └── models.py            #   CharacterData, LorebookEntry 等
│   ├── settings.py              # Settings 单例（读取 settings.json）
│   └── utils/
│       ├── manager_base.py      #   BaseManager（注册 FileWatcher）
│       ├── watcher.py           #   FileWatcher（watchdog 文件监控）
│       └── path_utils.py        #   路径解析
├── api/                         # FastAPI 应用
│   ├── main.py                  #   入口 + CORS + 路由注册
│   ├── deps.py                  #   管理器单例（含 per-session 缓存 + watcher）
│   ├── logger.py                #   API 日志配置（文件 + stderr）
│   ├── settings.json            #   API 级配置（port/log_level 等）
│   ├── settings.py              #   ApiSettings 单例
│   ├── run_dev.sh
│   └── routers/                 #   CRUD + Chat + 会话 + 工作区路由
│       ├── character.py
│       ├── lorebook.py
│       ├── status.py
│       ├── chat.py              #   send/stream(SSE)/command/history
│       ├── sessions.py          #   list/create/delete/clone
│       └── workspace.py         #   list/get_active/switch
├── webui/                       # Vue 3 SPA（Ant Design Vue + Pinia）
│   ├── settings.json            #   API 连接配置
│   ├── vite.config.js           #   Vite 配置（proxy 代理 /api）
│   ├── run_dev.sh
│   └── src/
│       ├── main.js              #   入口（Pinia + Router + Antd）
│       ├── App.vue              #   根组件（主题配置）
│       ├── router/index.js      #   路由（DashboardLayout 嵌套）
│       ├── layouts/
│       │   └── DashboardLayout.vue  # 侧边栏 + 工作区/会话选择器
│       ├── stores/              #   Pinia 状态管理
│       │   ├── session.js
│       │   ├── theme.js         #   暗色模式（data-theme 属性）
│       │   └── workspace.js
│       ├── composables/
│       │   ├── useCRUD.js       #   通用 CRUD（character/lorebook/milestone）
│       │   └── useCommands.js   #   斜杠命令前端逻辑
│       ├── components/
│       │   ├── ThemeToggle.vue
│       │   └── MarkdownContent.vue
│       ├── api/                 #   Axios 客户端（per-resource 模块）
│       │   ├── index.js         #   axios 实例 + 拦截器
│       │   ├── chat.js          #   SSE 流式 fetch
│       │   ├── session.js       #   会话 API
│       │   ├── workspace.js     #   工作区 API
│       │   ├── character.js
│       │   ├── lorebook.js
│       │   └── status.js
│       └── views/
│           ├── Overview.vue
│           ├── ChatView.vue     #   全功能聊天界面（SSE 流式渲染）
│           ├── CharacterManagement.vue
│           ├── LorebookManagement.vue
│           └── StatusManagement.vue  # 自定义 CSV 表格编辑器
└── data/                        # 数据文件（git 跟踪）
    └── 非公开行程/              #   工作区
        ├── character/           #   角色卡 JSON
        ├── lorebook/            #   世界书 JSON
        └── sessions/            #   会话数据
            └── default/
                ├── history.jsonl          # 主对话历史（compact 时截断）
                ├── history_cold.jsonl     # 冷备份（只追加，永不截断）
                ├── persistent_memory.json # 常驻记忆
                ├── rpg_summaries.json     # 对话摘要
                ├── story_memory.json      # 剧情记忆
                └── status/               # 状态表 CSV
```

## 关键设计

### 5 层 RPG 上下文（`context/builder.py` → `rpg_context.py`）

LLM 调用时的消息构建顺序，按变更频率排列以优化 prefix cache：

| 层 | role | 内容 | 变更频率 |
|---|---|---|---|
| [0] Fixed | system | 系统提示 + 世界书 + 角色卡 | ★ 几乎不变 |
| [1] Persistent Memory | system | 常驻记忆（persistent_memory.md） | ★ 离线更新 |
| [2] Summary | system | 历史摘要（条件触发） | ★☆ 少量 |
| [3..N] Hot History | mixed | 最近 N 轮对话 | ★★☆ 每轮追加 |
| [N+1] Milestones | system | 活跃里程碑 | ★★☆ 剧情驱动 |
| [N+2] Story Memory | system | 剧情细节 | ★★☆ 累积 |
| [N+3] Recalled Memory | system | 动态召回 | ★★★ 动态注入 |
| [N+4] Status Tables | system | 游戏状态 CSV 表 | ★★★★ 高频变化 |
| [N+5] User Message | user | `[scene]` + 用户输入 + 前后缀 | 总是新的 |

上下文构建基于 Jinja2 模板（`rpg_core/jinja/`），每个层级有独立模块模板。渲染结果通过 `RPGContext.to_messages()` 展平为 OpenAI-compatible 消息列表。

### 结构化类型系统（`agent/agent_types.py`）

所有 LLM 调用使用结构化数据类型替代原始 dict：

- **`LLMUsage`** — token 消耗（含 cache hit/miss 统计）
- **`LLMResponse`** — content + tool_calls + usage + model + reasoning
- **`CallRecord`** — 单次 LLM 调用快照（source/model/usage/duration）
- **`TurnStats`** — 一次 `send()` 或 `send_stream()` 中所有 LLM 调用的聚合
- **`ProviderChunk`** — Provider 层流式 chunk
- **`StreamEventKind`** — 语义事件枚举（TEXT, THINKING, TOOL_CALL, TOOL_RESULT, DONE, ERROR…）
- **`AgentStreamEvent`** — 消费者层面的事件（用于 CLI 和 API SSE）

### 子 Agent 系统（`agent/sub_agents/`）

继承自 `BaseSubAgent`，通过 `SubAgentContext` 获取世界书 + 角色卡上下文：

| 子 Agent | 职责 | 执行时机 |
|---|---|---|
| **StatusSubAgent** | 状态表预更新 | 主 LLM 调用之前，用精简上下文判断状态变更，避免 tool calling round-trip |
| **MemorySubAgent** | 记忆总结/召回/剧情持久化 | `process()` 由 CommandDispatcher 或自动触发 |

核心特性：
- **`BaseSubAgent`** — LLM Provider 共享/自建、重入守卫、`SubAgentContext` 绑定、`ToolProvider` 接口
- **`SubAgentContext`** — 轻量上下文容器（世界书条目 + 角色卡），复用 Jinja2 模板渲染
- 子 Agent 可注册到 `CommandDispatcher` 提供斜杠命令
- 支持独立 LLM 模型（如 gpt-4o-mini 处理状态表）

### 斜杠命令系统（`agent/command.py`）

`CommandDispatcher` 在 `agent.send()` 进入 LLM 之前拦截 `/` 开头的输入：

| 命令 | 来源 | 功能 |
|---|---|---|
| `/clear` | 内置 | 清空对话历史 |
| `/reload` | 内置 | 重新加载 RPG 数据 |
| `/context` | 内置 | 查看当前上下文结构和 token 用量 |
| `/compact [N] [K]` | MemorySubAgent | 压缩最老的 N 轮对话为摘要，保留最近 K 轮 |
| `/sessions` | 内置 (CLI) | 列出所有会话 |
| `/session-create <id>` | 内置 (CLI) | 创建新会话 |
| `/session-switch <id>` | 内置 (CLI) | 切换到指定会话 |

前端 WebUI（`useCommands.js`）维护命令白名单，提供弹窗提示。

### 流式架构（Streaming）

`RPGGameAgent` 同时支持 **buffered**（`send()`）和 **streaming**（`send_stream()`）两种路径：

```
send_stream(user_input)
  → StatusSubAgent 预更新
  → [scene] 嵌入 user message
  → run_chat_loop_stream()
    → provider.chat_stream()
    → 逐 chunk 产出 ProviderChunk
    → 组装 AgentStreamEvent（TEXT/THINKING/TOOL_CALL/TOOL_RESULT/ROUND_START/ROUND_END/DONE）
  → DONE 事件携带聚合 usage + TurnStats
```

WebUI 通过 `fetch` + `ReadableStream` 消费 SSE 事件流。API 端通过 `StreamingResponse` 输出 `text/event-stream`。

### 对话历史持久化

- `history.jsonl` — 主文件，compact 时截断
- `history_cold.jsonl` — 冷备份，只追加永不截断，用于记忆搜寻
- 热重载：`get_context_info()` / `get_context_markdown()` 不修改历史，纯查看

### Loader + Manager + BaseManager 模式

每个数据域（character/lorebook/status/milestone）遵循：

1. **Loader** — 纯文件 I/O，无缓存无业务逻辑
2. **Manager** — 继承 `BaseManager`，持有 `self.data` 缓存，实现 `reload()` / `_data_dir()`
3. **BaseManager** — 构造时向 `FileWatcher` 注册数据目录，文件变更自动调用 `reload()`
4. **FileWatcher** — watchdog Observer，500ms 防抖，启动由 `deps.py` 控制

新增：`SummaryStore` / `StoryMemoryStore` / `PersistentMemoryStore` 也注册 FileWatcher。

### 场景状态模块（`scene/`）

`SceneTracker` 管理"当前场景"的时间、地点、属性，数据持久化到 `status/全局状态/当前场景.csv`。

- 纯内存状态 + CSV 持久化（复用 StatusManager）
- `[scene]` 渲染后嵌入用户消息（`agent.send()` 写入 `_history` 和 JSONL）
- 使 MemorySubAgent 在总结归纳时可见（不依赖 system 角色消息）
- Builder 组装通用状态表时排除 scene table 避免重复
- 场景属性上限 `MAX_ATTRS = 8`，超出时报错

### 路径解析（`utils/path_utils.py` / `settings.py`）

- 绝对路径 → 原样返回
- 相对路径 → 以 `rpg_world/` 为根解析
  - 有 `active_workspace`（如 `data/非公开行程`）→ `rpg_world/{workspace}/{path}`
  - 无 workspace → `rpg_world/data/{path}`
- 会话范围数据：`{workspace_root}/sessions/{session_id}/{filename}`

### Agent 数据流

```
agent.send(user_input)
  → CommandDispatcher 拦截斜杠命令（是则旁路 LLM）
  → StatusSubAgent.update() 预更新状态表（~1-2K tokens 避免主 loop round-trip）
  → SceneTracker.get_context() → [scene] 嵌入 user message
  → _build_transformed_context() → builder.build() → RPGContext.to_messages()
  → run_chat_loop(provider, tool_registry, messages)
    → LLM 可能调工具（scene.set_time / set_attr / file tools）
    → 每轮记录 TurnStats + CallRecord
  → 回复写入 _history + history.jsonl + history_cold.jsonl
  → 返回 AgentReply（含 text + tool_records + stats）
```

### REST API（`api/routers/` — CRUD 路由）

```
GET    /api/v1/{resource}           — 列表
POST   /api/v1/{resource}           — 创建
GET    /api/v1/{resource}/{name}     — 详情
PUT    /api/v1/{resource}/{name}     — 更新
DELETE /api/v1/{resource}/{name}     — 删除
```

错误码：400（校验）、404（不存在）、409（冲突）。

### Chat API（`api/routers/chat.py`）

```
GET    /api/v1/chat/history          — 获取历史会话
POST   /api/v1/chat/send             — 发送消息（缓冲回复）
POST   /api/v1/chat/stream           — 发送消息（SSE 流式回复）
POST   /api/v1/chat/command          — 执行斜杠命令
```

- Agent 实例按 `session_id + api_key` 缓存
- API Key 通过 `X-OpenAI-Api-Key` header 传递
- SSE 流式格式：`data: {json}\n\n`

### Sessions API（`api/routers/sessions.py`）

```
GET    /api/v1/workspaces/active/sessions       — 列出会话
POST   /api/v1/workspaces/active/sessions       — 创建会话
DELETE /api/v1/workspaces/active/sessions/{id}  — 删除会话
POST   /api/v1/workspaces/active/sessions/{id}/clone — 克隆会话
```

### Workspace API（`api/routers/workspace.py`）

```
GET    /api/v1/workspaces           — 列出工作区
GET    /api/v1/workspaces/active    — 获取当前工作区
PUT    /api/v1/workspaces/active    — 切换工作区（重置所有缓存）
```

### settings.json 配置

```json
{
  "active_workspace": "data/非公开行程",
  "agent_config": {
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com",
    "max_tool_call_limit": 10,
    "include_tool_records": true,
    "verbose_logging": true,
    "memory_sub_agent": {
      "enabled": true,
      "summary": { "compress_rounds": 10, "keep_rounds": 5, "trigger_rounds": 20 },
      "recall": { "max_items": 5 },
      "story": { "max_details": 10 }
    },
    "status_sub_agent": {
      "enabled": true,
      "model": null
    }
  },
  "character_path": "character",
  "lorebook_path": "lorebook"
}
```

### 前端注意事项

- **DashboardLayout** 侧边栏含工作区选择器 + 会话选择器（桌面/移动自适应）
- `useCRUD` composable 适用于 character/lorebook 的 CRUD 页面（含 tags 和动态字段）
- `StatusManagement` 是自定义 CSV 表格编辑器（不共用 useCRUD）
- `ChatView` 使用 SSE 流式渲染（`streamMessage()` 基于 fetch + ReadableStream）
- 中文路径在前端 axios 层用 `encodeURIComponent()` 编码，后端 FastAPI 自动解码
- 暗色模式：`data-theme` 属性控制，Pinia store 持久化（antd 主题联动）
- Vite 开发代理：`/api` → `http://127.0.0.1:8000`

### 数据格式

- **Character/Lorebook/Milestone**: JSON 文件（name, enable, content, tags, 自定义字段）
- **Status**: CSV 文件，UTF-8 BOM (`utf-8-sig`) 编码，Excel 兼容
- **场景状态**: CSV（两列 key-value 格式，属性名/值）
- **会话历史**: JSONL（每行一个 `{"role":..., "content":...}`），含冷备份
- **摘要**: JSON（`["summary1", "summary2", ...]` 数组格式）
- **剧情记忆**: JSON（`[{"text":..., "metadata":...}]` 数组格式）
- **持久化路径**: worktree 构造时从 `settings.json` 读取路径配置

### 新增模块速查

| 模块 | 说明 | 关键文件 |
|---|---|---|
| 子 Agent | 预更新状态表 + 记忆管理 | `sub_agents/base.py`, `status_sub_agent.py`, `memory_sub_agent.py` |
| 流式输出 | SSE 实时推送 LLM 回复 | `loop.py` → `run_chat_loop_stream()`, `chat.py` → `/chat/stream` |
| 斜杠命令 | `/clear` `/reload` `/compact` `/context` | `command.py` `useCommands.js` |
| 会话管理 | 多会话切换/创建/克隆 | `sessions.py` `session.js` |
| 工作区切换 | 多项目工作区支持 | `workspace.py` `workspace.js` |
| Jinja2 模板 | 层级化模板渲染替代 f-string | `jinja/layers/` `jinja/modules/` |
| Token 统计 | LLM usage/cache 追踪 | `agent_types.py` → TurnStats, `stats_formatter.py` |
| API 日志 | 独立日志配置 | `api/logger.py` `api/settings.json` |
