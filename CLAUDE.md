# rpg_world

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。
记忆检索已经拆成 `SqlVecRetriever`、`BigramRetriever`、`RawMarkdownRetriever` 三个独立 retriever；`HybridRetriever` 只负责组装与融合，不承载底层检索实现。

## 启动

```bash
# 统一启动（读取 settings.yaml，按配置启动模块，supervisor 会拉起子进程）
uv run python -m rpg_world.run

# 同级快捷入口，便于查找和单独调试
uv run python -m rpg_world.run_all
uv run python -m rpg_world.run_api
uv run python -m rpg_world.run_telegram
uv run python -m rpg_world.run_cli

# 仅启动 API（开发，自动重载）
MODULES=api uv run python -m rpg_world.run

# 或直接 uvicorn
uv run uvicorn rpg_world.api.main:app --reload --reload-dir rpg_world --host 127.0.0.1 --port 8000

# WebUI 开发服务器（端口 5173，代理 /api → 后端）
cd rpg_world/webui && npx vite

# 仅启动 Telegram（需先配置 settings.yaml modules.telegram.bots）
MODULES=telegram uv run python -m rpg_world.run

# 独立 CLI（无 API / Telegram，直接 LLM 对话）
uv run python -m rpg_world.channels.cli.repl [--model gpt-4o] [--session-id mygame_01]

# 验证导入
uv run python3 -c "from rpg_world.rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── run.py                        # supervisor（批量拉起子进程）
├── settings.yaml                  # 业务/渠道/模块配置（base + profiles）
├── llm.yaml                       # LLM provider / 模型配置（base + profiles）
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
│   └── tests/                    #   渠道测试（mock LLM / Telegram SDK）
│       ├── conftest.py           #    共享 fixture（FakeAgent, FakeBot）
│       ├── test_base.py          #    ChannelAdapter 基类
│       ├── test_cli.py           #    CLIAdapter
│       ├── test_manager.py       #    AgentManager
│       └── test_telegram.py      #    Telegram 会话/命令/渲染/流式发送
├── rpg_core/                     # 核心逻辑（无框架依赖）
│   ├── agent/                    #   LLM Agent 引擎
│   │   ├── agent.py              #     RPGGameAgent — 主入口（send/send_stream/single_turn）
│   │   ├── agent_types.py        #     结构化类型 + QueueItem 队列类型
│   │   ├── manager.py            #     AgentManager 单例（统一 agent 缓存）
│   │   ├── command.py            #     CommandDispatcher — 斜杠命令分发器
│   │   ├── loop.py               #     chat loop（LLM 往返 + tool calling）
│   │   ├── prompt.py             #     PromptManager — 系统提示词
│   │   ├── stats_formatter.py    #     LLM 统计格式化
│   │   ├── tokenizer.py          #     TokenCounter 抽象
│   │   ├── sub_agents/           #     子 Agent 系统
│   │   └── tools/                #     工具系统
│   ├── llm/                      #   LLMProvider 抽象、OpenAI/llama provider、LLMManager、llm.yaml 解析
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
│   ├── main.py                   #   入口 + CORS + lifespan（不启动渠道）
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
│       └── workspace.py          #   list/create/rename/delete
├── webui/                        # Vue 3 SPA（Ant Design Vue + Pinia，优先数据管理）
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
            ├── rpg_summaries.json
            ├── summaries/
            └── memory_vectors.db
```

## 进程隔离架构

rpg_world 采用 **supervisor + 子进程** 模式：`run.py` 只负责按配置拉起 API、
Telegram、CLI 子进程，转发停止信号并回收退出。每个模块都有自己的进程和
自己的 `AgentManager` 单例，模块间不共享运行时状态。`api/main.py` 的 lifespan
不做任何渠道初始化。

```
supervisor (rpg_world.run)
├── api 子进程      -> uvicorn rpg_world.api.main:app
├── telegram 子进程 -> rpg_world.channels.telegram.runner
└── cli 子进程      -> rpg_world.channels.cli.repl
```

根目录还提供同级快捷入口，便于单独调试和查找：

```
run_all.py      -> rpg_world.run
run_api.py      -> rpg_world.api.main
run_telegram.py -> rpg_world.channels.telegram.runner
run_cli.py      -> rpg_world.channels.cli.repl
```

每个子进程内部仍然保留进程内单例与缓存：

```
单个子进程
├── AgentManager 单例
│   ├── RPGGameAgent 实例池（按 session_id + api_key 缓存）
│   ├── FileWatcher（watchdog 文件监听）
│   └── BaseManager 缓存（character/lorebook/status）
└── 本模块运行态（API / Telegram / CLI 之一）
```

### 配置（`settings.yaml` / `llm.yaml`）

`settings.yaml` 负责业务配置、模块启停、渠道参数和数据路径；`llm.yaml` 负责 LLM provider、模型、上下文窗口、温度、超时等 LLM 强相关配置。二者都采用 `base + profiles`，通过 `RPG_WORLD_PROFILE` 选择 profile，默认 `local`。profile 可通过 `file: *.local.yaml` 读取被 git ignore 的覆盖文件；缺失文件默认按空覆盖处理，`required: true` 时缺失会报错。
`api/settings.json` 仍只用于 API 服务级日志等配置。
模块启停通过 `ChannelsSettings` 的类型化属性访问（`channels/config.py`），外部调用不做字符串拼接：

```python
channels_settings.api_enabled      # modules.api.enabled
channels_settings.api_host          # modules.api.host
channels_settings.api_port          # modules.api.port
channels_settings.api_reload        # modules.api.reload
channels_settings.telegram_enabled  # modules.telegram.enabled
channels_settings.telegram_bots     # modules.telegram.bots
channels_settings.cli_enabled       # modules.cli.enabled
channels_settings.cli_workspace     # modules.cli.workspace
channels_settings.enabled_module_names  # 所有已启用模块列表
```

核心配置访问规则：

- 业务代码读取业务配置走 `rpg_core.settings.settings` 的属性或方法，例如 `settings.memory_settings`。
- LLM provider 创建走 `LLMManager.get().get_provider(biz_key)`，不要在业务模块中直接 new OpenAI/llama client。
- LLM 配置解析只通过 `rpg_core.llm.config.resolve_biz_config()`、`get_runtime_config()` 等封装方法。
- `rerank_score_weight` 是 memory 排序业务参数，属于 `settings.yaml`；`llm.yaml` 的 `memory.rerank` 只放 provider/model/model_path/n_ctx/temperature/request_timeout_ms 等 LLM 参数。

### AgentManager（`rpg_core/agent/manager.py`）

进程内单例，统一管理 `RPGGameAgent` 的创建与缓存。每个子进程各自持有一个
独立实例池：

```python
from rpg_world.rpg_core.agent.manager import AgentManager

agent = AgentManager.get_or_create(session_id="mygame_01")
```

单个进程内，所有模块通过同一个 `AgentManager` 获取 agent，确保 FileWatcher
只初始化一次、BaseManager 缓存一致。跨进程不共享这些对象。

`AgentManager` 的缓存键包含 `workspace`、`session_id`、`api_key`。同名 session
在不同 workspace 下会得到不同 agent，避免跨工作区污染。所有入口必须提供有效
workspace；API 空 workspace 会解析为 `data/api_default_workspace`，Telegram/CLI
从 `settings.yaml` 读取 workspace，缺省时分别使用渠道默认 workspace。

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

Telegram 例外：`/sessions`、无参数 `/session_switch`、无参数 `/session_create`
和 `/cancel` 的菜单/二段输入属于渠道交互状态，由
`channels/telegram/session_flow.py` 消费；真正带参数的 session 命令仍交回
agent 的 `CommandDispatcher` 执行。

### Telegram 渠道当前能力

Telegram 是当前优先保障的主对话入口，WebUI Chat 不是当前优先级最高的聊天入口。

| 能力 | 当前实现 |
|---|---|
| 启动方式 | `MODULES=telegram uv run python -m rpg_world.run` 或 `settings.yaml` 启用 |
| 长轮询 | `python-telegram-bot` `Application` + `updater.start_polling()` |
| 流式输出 | `send_delta()` 首条发送、后续编辑消息，支持间隔和最小字符数节流 |
| 非流式输出 | `send_text()` 完整发送，自动分块 |
| 渲染 | Markdown 转 Telegram HTML，长文本按 Telegram 限制分块 |
| 命令 | `/start`、后端斜杠命令、Telegram 菜单命令规范化 |
| 会话 | 默认 `telegram_<bot_name>_<chat_id>`，支持 `/sessions` 菜单、按钮切换、二段式创建 |
| 取消流程 | `/cancel` 取消 Telegram 专属二段式创建 |
| 网络参数 | `proxy`、请求超时、流式编辑节流参数来自 `settings.yaml` 的 bot 配置 |

后续涉及 Telegram 的修改应优先补 `channels/tests/test_telegram.py`，尤其是：
会话菜单、命令规范化、stream 编辑节流、请求失败/超时、Markdown 渲染、长文本分块。

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

### 记忆 `meta` 字段

最终返回的记忆 `meta` 是由 `candidate.metadata`、检索分数和 rerank 调试信息合并而成。
`HybridRetriever` 负责把 `sqlvec / bigram / raw_md` 三路结果合并，`MemoryManager.hybrid_search()`
会再把候选转成对外返回的 `metadata`。

| 字段 | 来源 | 作用 |
|---|---|---|
| `type` | `summary/overall.md` front matter，来自 `BatchSummaryStore.save_overall()` | 摘要类型，通常是 `overall` |
| `last_batch_id` | `summary/overall.md` front matter | overall 记录追踪到的最新批次 |
| `memory_id` | SQL chunk 的 `chunks.id` 或 raw md 的稳定哈希 ID | 召回项唯一标识，也是分数合并键 |
| `source` | 原始文件元信息或 raw md 目录名 | 例如 `summaries` |
| `file` | 原始文件路径 | 定位到源文件 |
| `chunk_idx` | 分块索引 | 同一文件内的 chunk 序号 |
| `created_at` | SQL chunk 的写入时间；raw md 的文件 mtime | 用于 `recency_score` |
| `vector_score` | `SqlVecRetriever` / `VectorIndex` | 向量相似度分数 |
| `bigram_score` | `BigramRetriever` / FTS | bigram / BM25 分数 |
| `exact_score` | `exact_and_fuzzy_scores()` | query 完全命中时为 1.0 |
| `fuzzy_score` | `exact_and_fuzzy_scores()` | query 模糊匹配分数 |
| `recency_score` | `HybridRetriever._finalize()` | 时间越近分数越高 |
| `hybrid_score` | `apply_hybrid_scores()` | 召回融合分 |
| `rerank_score` | `PointwiseMemoryReranker` | 最终重排分 |
| `debug` | 各检索 / 重排阶段逐步写入 | 调试信息，通常包含 `*_norm`、`*_reason`、`raw_md_*` |

常见 `debug` 键：

| debug 键 | 来源 | 说明 |
|---|---|---|
| `bigram_bm25` | `BigramRetriever` | bigram FTS 的原始 BM25 分数 |
| `bigram_queries` | `BigramRetriever` | 参与 bigram 搜索的 query 列表 |
| `raw_md_source` | `RawMarkdownGrepSearch` | raw markdown 源文件路径 |
| `raw_md_terms` | `RawMarkdownGrepSearch` | raw markdown 计算命中的 term |
| `vector_score_norm` | `apply_hybrid_scores()` | 向量分归一化结果 |
| `bigram_score_norm` | `apply_hybrid_scores()` | bigram 分归一化结果 |
| `recency_score_norm` | `apply_hybrid_scores()` | 时间分归一化结果 |
| `exact_or_fuzzy_score` | `apply_hybrid_scores()` | exact / fuzzy 的合并分 |
| `llama_score_norm` | `PointwiseMemoryReranker` | llama provider rerank 归一化分 |
| `llama_reason` | `PointwiseMemoryReranker` | llama provider rerank 给出的原因 |
| `openai_score_norm` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 归一化分 |
| `openai_reason` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 给出的原因 |

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

支持独立 LLM provider 配置，通过 `llm.yaml` 的 `agent.status_sub_agent` / `agent.memory_sub_agent` biz key 选择 `shared`、`openai` 或 `llama`，通过 `SubAgentContext` 获取世界书 + 角色卡上下文。

### 斜杠命令系统（`agent/command.py`）

| 命令 | 来源 | 功能 |
|---|---|---|
| `/clear` | 内置 | 清空对话历史 |
| `/reload` | 内置 | 重新加载 RPG 数据 |
| `/context` | 内置 | 查看上下文结构和 token 用量 |
| `/compact [N] [K]` | MemorySubAgent | 压缩最老的 N 轮对话为摘要 |
| `/sessions` | 内置 | 列出所有会话 |
| `/session_create <id>` | 内置 | 创建新会话 |
| `/session_switch <id>` | 内置 | 切换到指定会话 |
| `/memory_reindex` | 内置 | 手动重建 memory 索引 |

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
GET    /api/v1/chat/commands         — 获取可用斜杠命令
```

Workspace / Session API：

```
GET    /api/v1/workspaces                         — 列出工作区
POST   /api/v1/workspaces                         — 创建工作区
PUT    /api/v1/workspaces/{workspace}             — 重命名工作区
DELETE /api/v1/workspaces/{workspace}             — 删除工作区
GET    /api/v1/workspaces/{workspace}/sessions    — 列出会话
POST   /api/v1/workspaces/{workspace}/sessions    — 创建会话
DELETE /api/v1/workspaces/{workspace}/sessions/{session_id}
POST   /api/v1/workspaces/{workspace}/sessions/{session_id}/clone
```

- Agent 实例通过 `AgentManager` 统一管理
- API Key 通过 `X-OpenAI-Api-Key` header 传递
- SSE 流式格式：`data: {json}\n\n`

### 对话历史持久化

- `history.jsonl` — 主文件，消息记录使用 `hid` 作为标识，`hid` 只用于记录，不参与 turn 逻辑
- `history_cold.jsonl` — 冷备份，只追加永不截断
- `story_memory.json` — 剧情记忆（FileWatcher）
- `rpg_summaries.json` — 对话摘要（FileWatcher）
- `summaries/` — 批次摘要文件
- `memory_vectors.db*` — memory SQLite / WAL / SHM 索引文件

会话层的 turn / rounds 统一由 `SessionManager` 负责，降级顺序固定为：`turn_id -> user anchor -> 2 messages -> 1 message`。故事记忆续提游标按逻辑 turn 索引持久化，进程重启后继续沿同一套 turn 分组规则提取。

所有会话数据文件集中在 `{workspace_root}/sessions/{session_id}/` 下。

`session_id` 只能使用英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。默认渠道映射示例：`cli_direct`、`telegram_12345`。

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
- 当前 WebUI 优先作为个人数据管理后台：角色卡、世界书、状态表、workspace、session 管理优先
- `ChatView` 使用 SSE 流式渲染（`streamMessage()` 基于 fetch + ReadableStream），但完整 Chat UX 排在 Telegram 稳定之后
- 中文路径在前端 axios 层用 `encodeURIComponent()` 编码
- 暗色模式：`data-theme` 属性控制，Pinia store 持久化
- Vite 开发代理：`/api` → `http://127.0.0.1:8000`
- `session_id` 输入必须与后端一致，只允许字母、数字、下划线，不允许连字符

### 数据格式

- **Character/Lorebook**: JSON（name, enable, content, tags, 自定义字段）
- **Status**: CSV，UTF-8 BOM（`utf-8-sig`），Excel 兼容
- **会话历史**: JSONL（每行一个 message 对象）
- **摘要**: JSON 数组
- **剧情记忆**: JSON 数组（含 metadata）

## 测试基线

当前自动化测试基线：

```bash
uv run python -m pytest channels/tests rpg_core/tests api/tests -q
```

这些测试 mock 外部 LLM、Telegram SDK 和网络调用，不需要真实 API key。若本地缺少 `pytest-asyncio`，`rpg_core/tests/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。

覆盖范围：

- `channels/tests/`：ChannelAdapter、CLI、AgentManager、Telegram 渠道。
- `rpg_core/tests/`：命令分发、上下文、memory、scene、session、summary、AgentManager。
- `api/tests/`：workspace/session/character/lorebook/status/chat 契约。

## 当前实现优先级

1. **P0：Telegram 渠道完善**。保障 Telegram 作为主要对话入口，包括真实运行、
   会话管理、stream/non-stream、异常回复、命令菜单、配置和日志。
2. **P1：核心数据与记忆链路**。确保角色卡、世界书、状态表、summary、memory
   在 Telegram 使用路径下稳定可用。
3. **P2：WebUI 数据管理后台**。优先完善数据维护能力，方便人工管理工作区、
   角色、世界书、状态表和会话。
4. **P3：WebUI Chat**。最后再完善 SSE 体验、tool records、stats、多会话聊天 UX
   和前端分包。
