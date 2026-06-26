# RPG World

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。
记忆检索已经拆成 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三个独立 retriever；`HybridRetriever` 只负责组装与融合，不承载底层检索实现。关键词检索通过 `memory.keyword_tokenizer` 选择 `jieba`、`bigram` 或 `both`，配置使用 `keyword_k` / `hybrid_keyword_weight`。raw markdown 由 `memory.raw_md_mode` 控制，`always` 是主召回策略，`fallback_only` 是补候选触发策略。


## 产品路线

RPG World 的产品定位从“Telegram 优先的 RP 聊天入口”升级为“WebUI 主体验 + Telegram 辅助触达”的 AI RPG World 平台：

- **Play WebUI**：前台游玩端，面向玩家，提供沉浸式 RP 聊天、场景 HUD、角色/NPC 信息、剧情日志、快捷行动和玩法模块交互。
- **Telegram**：保留为轻量入口、推送通知、快速回复和 WebUI 不可用时的兜底交互，不承载复杂沉浸式 UI。

Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口。前端不得复制核心业务规则；渠道之间必须共享 workspace/session 映射，避免故事分裂。不要恢复 Dashboard API/WebUI。

Play WebUI 的会话定位采用 `rpg_data` catalog 中的全局短 `session_id`。创建 session 时绑定 `workspace_id + story_id`；进入会话后，前端 URL 和会话内请求只传 `session_id`，由 Play API 反查 workspace/story 并调用 Agent 服务。不要恢复前端每次传 `workspace + story_id + session_id` 的三元 locator。

## 启动

```bash
# Agent 服务（唯一持有 AgentManager/RPGGameAgent/rp_memory/llama lazy worker）
uv run python -m run_agent

# 独立入口，按需分别启动
uv run python -m run_play_api
uv run python -m run_telegram
uv run python -m run_cli

# 或直接 uvicorn
uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llama_service --host 127.0.0.1 --port 8000

# Play WebUI 开发服务器
cd play_webui && npm run dev

# CLI / Telegram 通过 agent_client 访问 Agent 服务
uv run python -m channels.cli.repl

# 验证导入
uv run python3 -c "from rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── run_agent.py                   # Agent 服务入口（唯一 agent runtime owner）
├── run_play_api.py                # Play API 入口
├── run_cli.py                     # CLI 入口（AgentClient）
├── run_telegram.py                # Telegram 入口（AgentClient）
├── settings.yaml                  # 业务/services/agent_client/渠道配置（base + profiles）
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
│   │   ├── sub_agents/           #     子 Agent 系统
│   │   └── tools/                #     工具系统
│   ├── llm/                      #   LLMProvider 抽象、OpenAI/llama provider、LLMManager、llm.yaml 解析
│   ├── scene/                    # 场景状态（时间/地点/属性）
│   ├── context/                  # 结构化 RPG 上下文、固定层、渲染边界和诊断
│   ├── jinja/                    # Jinja2 模板
│   ├── character/                # 角色卡（JSON）
│   ├── lorebook/                 # 世界书（JSON）
│   ├── status/                   # 状态表（CSV）
│   ├── summary/                  # 对话摘要
│   ├── common_types.py           # 共享类型别名
│   ├── settings.py               # Settings 单例
│   └── utils/
│       ├── manager_base.py       #   BaseManager（注册 FileWatcher）
│       ├── stats_formatter.py    #   LLM 统计格式化
│       ├── tokenizer.py          #   TokenCounter 抽象
│       ├── watcher.py            #   FileWatcher（watchdog 文件监控）
│       └── path_utils.py         #   路径解析
├── rp_memory/                    # 记忆系统（检索、索引、规划、召回、rerank）
│   ├── planning/                 #   QueryPlan / planner
│   ├── retrieval/                #   sqlvec / keyword / raw md retrievers
│   ├── rerank/                   #   pointwise rerank
│   └── storage/                  #   SQLite repository / vector / text index
├── llama_service/                # llama.cpp 本地模型服务客户端/服务端
├── play_api/                     # Play WebUI 专用 FastAPI 应用
│   ├── main.py                   #   入口 + CORS + lifespan（不启动渠道）
│   ├── settings.yaml             #   Play API 进程配置（监听 + 日志）
│   ├── settings.py               #   PlaySettings 单例
│   ├── backends/                 #   AgentClient / rpg_data 后端适配
│   └── routers/
│       ├── sessions.py           #   session APIs + history/scene/commands/turn/stream
│       ├── chat.py               #   legacy placeholder；不要恢复为主入口
│       ├── commands.py           #   legacy placeholder；不要恢复为主入口
│       ├── scene.py              #   legacy placeholder；不要恢复为主入口
│       └── workspace.py          #   workspace APIs
├── play_webui/                   # Play WebUI：Next.js + React + TypeScript
│   ├── src/app/                  #   App Router
│   ├── src/features/             #   home/session/scene/stream features
│   ├── src/lib/api/              #   Play API client
│   └── src/components/           #   Timeline、Scene HUD、输入区等
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

RPG World 采用 **单 Agent 服务 + 独立入口** 模式。根目录聚合 supervisor 入口已移除。
只有 `run_agent.py` 进程持有 `AgentManager`、`RPGGameAgent`、`rp_memory` 和 llama lazy worker。
Play API、CLI、Telegram 不创建 agent，不缓存 agent，不配置 llama，只通过
`agent_service.client.AgentClient` 访问 Agent 服务。

```
run_agent          -> agent_service.main:app
run_play_api       -> play_api.main:app           -> AgentClient
run_cli            -> channels.cli.repl           -> AgentClient
run_telegram       -> channels.telegram.runner    -> AgentClient
```

根目录还提供同级快捷入口，便于单独调试和查找：

```
run_agent.py -> agent_service.main
run_play_api.py -> play_api.main
run_telegram.py -> channels.telegram.runner
run_cli.py      -> channels.cli.repl
```

Agent runtime 只存在于 Agent 服务进程：

```
agent_service 进程
├── AgentManager 单例
│   ├── RPGGameAgent 实例池（按 session_id + api_key 缓存）
│   ├── FileWatcher（watchdog 文件监听）
│   ├── rp_memory
│   └── llama_service lazy worker
└── HTTP + SSE: /agent/v1
```

### 配置（`settings.yaml` / `llm.yaml`）

配置已拆分到各进程/模块目录：`rpg_core/settings.yaml` 管核心业务配置，`agent_service/settings.yaml` 管 Agent 服务监听与客户端默认值，`channels/settings.yaml` 管 CLI/Telegram 行为，`play_api/settings.yaml` 管 Play API 监听与日志，`llama_service/llm.yaml` 管 LLM provider、模型、上下文窗口、温度、超时等 LLM 强相关配置。它们都采用 `base + profiles`，通过 `RPG_WORLD_PROFILE` 选择 profile，默认 `local`；同级 `settings.local.yaml` / `llm.local.yaml` 等 profile 覆盖文件会自动加载。
进程启停不由配置控制。监听和客户端配置通过 `ChannelsSettings` 的类型化属性访问（`channels/config.py`），外部调用不做字符串拼接：

```python
channels_settings.agent_port
channels_settings.play_api_port
channels_settings.agent_client_base_url
channels_settings.telegram_bots
channels_settings.cli_workspace
```

核心配置访问规则：

- 业务代码读取业务配置走 `rpg_core.settings.settings` 的属性或方法，例如 `settings.memory_settings`。
- LLM provider 创建走 `LLMManager.get().get_provider(biz_key)`，不要在业务模块中直接 new OpenAI/llama client。
- LLM 配置解析只通过 `rpg_core.llm.config.resolve_biz_config()`、`get_runtime_config()` 等封装方法。
- memory 检索、融合、chunk 和 rerank pool 参数都属于 `settings.yaml`，包括 `keyword_tokenizer`、`keyword_k`、`raw_md_mode`、`raw_md_min_results`、`hybrid_*_weight`、`rerank_candidate_k`、`rerank_score_weight`。
- `keyword_k` / `hybrid_keyword_weight` 是当前 keyword 架构配置；不要恢复旧 `bigram_k` / `hybrid_bigram_weight`。
- `llm.yaml` 的 `memory.rerank` 只放 provider/model/model_path/n_ctx/temperature/request_timeout_ms 等 LLM 参数，并且 `kind: rerank` 必须显式声明 `rerank_model_type`。

### AgentManager（`rpg_core/agent/manager.py`）

进程内单例，统一管理 `RPGGameAgent` 的创建与缓存。每个子进程各自持有一个
独立实例池：

```python
from rpg_core.agent.manager import AgentManager

agent = AgentManager.get_or_create(session_id="mygame_01")
```

单个进程内，所有模块通过同一个 `AgentManager` 获取 agent，确保 FileWatcher
只初始化一次、BaseManager 缓存一致。跨进程不共享这些对象。

`AgentManager` 的缓存键包含 `workspace`、`session_id`、`api_key`。同名 session
在不同 workspace 下会得到不同 agent，避免跨工作区污染。所有入口必须提供有效
workspace；API 空 workspace 会解析为 API 默认工作区，Telegram/CLI
从 `settings.yaml` 读取 workspace，缺省时分别使用渠道默认 workspace。

### Play catalog 与 session 定位

`rpg_data` 的数据关系是：workspace 下有多个 story，story 下有多个 session；角色卡和世界书条目属于 workspace，并通过 `rpg_story_characters`、`rpg_story_lorebook_entries` 挂载到 story。同一个角色卡或世界书条目可以挂载到多个 story，挂载表只禁止同一 story 内重复挂载。

Play WebUI 公开的 `session_id` 是短 ID，格式为 `s_` + 10 位小写字母/数字，兼容 `rpg_core` 当前 `^[A-Za-z0-9_]+$` 校验。`rpg_sessions.id` 是稳定定位 ID，`rpg_session_profiles` 保存 title、description 等可读字段。Play API 是 catalog session 到 Agent 服务的边界层：会话内接口只收 `session_id`，内部解析出 workspace/story，再用 `workspace + session_id` 调用 Agent 服务；本轮不要求 Agent/rpg_core 感知 story。

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
| 启动方式 | `uv run python -m run_telegram`（通过 `agent_client` 访问 Agent 服务） |
| 长轮询 | `python-telegram-bot` `Application` + `updater.start_polling()` |
| 流式输出 | `send_delta()` 首条发送、后续编辑消息，支持间隔和最小字符数节流 |
| 非流式输出 | `send_text()` 完整发送，自动分块 |
| 渲染 | Markdown 转 Telegram HTML，长文本按 Telegram 限制分块 |
| 命令 | `/start`、后端斜杠命令、Telegram 菜单命令规范化 |
| 会话 | 默认 `telegram_<bot_name>_<chat_id>`，支持 `/sessions` 菜单、按钮切换、二段式创建 |
| 取消流程 | `/cancel` 取消 Telegram 专属二段式创建 |
| 网络参数 | `proxy`、请求超时、流式编辑节流参数来自 `channels/settings.yaml` 的 bot 配置 |

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
`HybridRetriever` 负责把 `sqlvec / keyword / raw_md` 三路结果合并，`MemoryManager.hybrid_search()`
会再把候选转成对外返回的 `metadata`。

召回主流程：

- sqlvec 可用时执行向量召回。
- keyword 可用时执行 tokenizer 可插拔的 FTS 召回。
- `raw_md_mode=always` 时 raw md 每次作为主召回一路参与 merge / scoring / rerank。
- `raw_md_mode=fallback_only` 时，主候选数低于阈值或主检索失败才执行 raw md。`raw_md_min_results > 0` 使用显式阈值；否则有 reranker 时使用 `rerank_candidate_k`，无 reranker 时使用 `top_k`。
- rerank 取最多 `rerank_candidate_k` 个 hybrid 候选，最终仍只返回 `top_k`。

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
| `keyword_score` | `KeywordRetriever` / FTS | keyword / BM25 分数 |
| `raw_md_score` | `RawMarkdownGrepSearch` | raw markdown 原文 query / term 覆盖分 |
| `exact_score` | `exact_and_fuzzy_scores()` | query 完全命中时为 1.0 |
| `fuzzy_score` | `exact_and_fuzzy_scores()` | query 模糊匹配分数 |
| `expanded_score` | `RawMarkdownGrepSearch` / `HybridRetriever._finalize()` | query planner 扩展查询或扩展分词命中分 |
| `recency_score` | `HybridRetriever._finalize()` | 时间越近分数越高 |
| `granularity_score` | `HybridRetriever._finalize()` | 记忆粒度优先级分，front matter 中的 `batch_id`、`type: overall` 等会参与解析 |
| `hybrid_score` | `apply_hybrid_scores()` | 向量、keyword、raw md、exact、expanded、recency、granularity 的融合分 |
| `rerank_score` | `PointwiseMemoryReranker` | 最终重排分 |
| `debug` | 各检索 / 重排阶段逐步写入 | 调试信息，通常包含 `*_norm`、`*_reason`、`raw_md_*` |

常见 `debug` 键：

| debug 键 | 来源 | 说明 |
|---|---|---|
| `keyword_bm25` | `KeywordRetriever` | keyword FTS 的原始 BM25 分数 |
| `keyword_relevance` | `KeywordRetriever` | BM25 转换后的有界 keyword 相关性分 |
| `keyword_tokenizer` | `TextIndex` | 当前 keyword FTS 使用的 tokenizer：`jieba` / `bigram` / `both` |
| `keyword_query_hits` | `KeywordRetriever` | 多 query 命中明细，包含 query、来源权重、原始分和加权分 |
| `keyword_queries` | `KeywordRetriever` | 参与 keyword 搜索的 query 列表 |
| `raw_md_source` | `RawMarkdownGrepSearch` | raw markdown 源文件路径 |
| `raw_md_terms` | `RawMarkdownGrepSearch` | raw markdown 计算命中的 term |
| `raw_md_expanded_queries` | `RawMarkdownGrepSearch` | raw markdown 使用的扩展查询 |
| `raw_md_expanded_terms` | `RawMarkdownGrepSearch` | 扩展查询再次分词得到的 raw md term |
| `raw_md_match_score` | `RawMarkdownGrepSearch` | raw md 阶段 exact、raw_md、expanded 三者的最大命中分 |
| `vector_score_norm` | `apply_hybrid_scores()` | 向量分归一化结果 |
| `keyword_score_norm` | `apply_hybrid_scores()` | keyword 分归一化结果 |
| `recency_score_norm` | `apply_hybrid_scores()` | 时间分归一化结果 |
| `exact_or_fuzzy_score` | `apply_hybrid_scores()` | exact / fuzzy 的合并分 |
| `expanded_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的扩展查询命中分 |
| `granularity_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的记忆粒度分 |
| `memory_granularity` | `HybridRetriever._finalize()` | 解析出的记忆粒度，如 `batch`、`event`、`global`、`unknown` |
| `llama_score_norm` | `PointwiseMemoryReranker` | llama provider rerank 归一化分 |
| `llama_reason` | `PointwiseMemoryReranker` | llama provider rerank 给出的原因 |
| `openai_score_norm` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 归一化分 |
| `openai_reason` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 给出的原因 |

### 结构化 RPG 上下文（`context/`）

上下文主流程保持结构化数据，直到发送给 LLM 前才统一渲染。核心分工：

| 模块 | 职责 |
|---|---|
| `fixed_layer.py` | `FixedLayerComposer` 与 `FixedLayerSection`，维护稳定固定层 |
| `builder.py` | 读取世界书、角色卡、摘要、记忆、状态表、用户扩展块，构建结构化 `RPGContext` |
| `rpg_context.py` | 只保留上下文层数据结构和薄委托方法 |
| `renderer.py` | LLM 请求边界渲染，将结构化层转成 OpenAI-compatible messages |
| `inspector.py` | `/context`、日志和调试用 markdown / token 诊断 |
| `rendering.py` | 共享 Jinja2 环境和模板渲染工具 |

LLM 调用时的消息构建顺序，按变更频率排列以优化 prefix cache：

| 层 | role | 内容 | 变更频率 |
|---|---|---|---|
| [0] Fixed | system | 系统提示 + 世界书 + 角色卡 | ★ 几乎不变 |
| [1] Persistent Memory | system | 常驻记忆 | ★ 离线更新 |
| [2] Summary | system | 历史摘要（条件触发） | ★☆ 少量 |
| [3..N] Hot History | mixed | 最近 N 轮对话 | ★★☆ 每轮追加 |
| [N+1] Story Memory | system | 剧情细节 | ★★☆ 累积 |
| [N+2] Recalled Memory | system | 动态召回 | ★★★ 动态注入 |
| [N+3] Status Tables | system | 普通状态 CSV 表，不包含 `当前场景.csv` | ★★★★ 高频变化 |
| [N+4] RP Modules | system | RP 模块运行态，如骰子、战斗、物品等后续模块 | ★★★★ 动态 |
| [N+5] User Message | user | `[scene]` + 用户输入 + 前后缀 | 总是新的 |

`当前场景.csv` 是特殊状态表，不走普通 `STATUS_TABLES` 层。`SceneTracker.get_context()`
会将它作为 user prefix 注入最终用户消息：一方面提高模型对当前时空、地点、场景属性的注意力，
另一方面让场景状态随 user message 进入历史，便于后续摘要和记忆按时间顺序归纳。

上下文基于 Jinja2 模板（`rpg_core/jinja/`），通过 `RPGContext.to_message_objects()`
展平为 OpenAI-compatible 消息列表。不要在 builder 或 dataclass 中提前拼接最终 prompt，
也不要把 markdown 诊断输出放回主业务数据模型。

RP Modules 不是通用 skill 体系。后续骰子、战斗、物品、关系等能力应定义为围绕 RP 语义的模块：
模块可以注册工具、暴露运行态 section、读写受控状态，但固定 instruction 层和不可变模块描述应保持稳定，
避免频繁变化破坏 prefix cache。

### Agent 数据流

```
agent.send(user_input)
  → CommandDispatcher 拦截斜杠命令（是则旁路 LLM，不入历史）
  → StatusSubAgent.update() 预更新状态表（~1-2K tokens 避免主 loop round-trip）
  → SceneTracker.get_context() → [scene] 嵌入 user message
  → _build_transformed_context() → builder.build() → RPGContext.to_message_objects()
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

支持独立 LLM provider 配置，通过 `llama_service/llm.yaml` 的 `agent.status_sub_agent` / `agent.memory_sub_agent` biz key 选择 `shared`、`openai` 或 `llama`，通过 `SubAgentContext` 获取世界书 + 角色卡上下文。

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

Play API 使用 `play_api/settings.yaml` 中的 `api_prefix`，默认 `/play-api/v1`。路由集中在
`play_api/routers/`，作为 Play WebUI 的唯一 Web 后端契约。

当前主要路由：

| 模块 | 路由文件 | 职责 |
|---|---|---|
| workspace | `play_api/routers/workspace.py` | 工作区列表 |
| sessions | `play_api/routers/sessions.py` | 会话列表、创建、读取，以及 `history/scene/commands/turn/stream` 子资源 |
| scene / commands / chat | 对应 router 文件 | legacy placeholder，保留模块名但不作为主入口 |

- Play API 通过 `agent_service.client.AgentClient` 访问 Agent 服务。
- Play WebUI 会话内请求只传 `session_id`；Play API 负责从 catalog 解析 workspace/story。
- API Key 通过 `X-OpenAI-Api-Key` header 传递。
- SSE 流式格式：`data: {json}\n\n`。

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

- Play WebUI 使用 Next.js App Router + React + TypeScript。
- Play WebUI 只访问 Play API，不直接访问 `data/`。
- Web 管理能力也沉淀在 Play WebUI 内，不跳转旧 Dashboard。
- 中文路径在前端 API 层用 `encodeURIComponent()` 编码。
- `session_id` 输入必须与后端一致，只允许字母、数字、下划线，不允许连字符。

### 数据格式

- **Character/Lorebook**: JSON（name, enable, content, tags, 自定义字段）
- **Status**: CSV，UTF-8 BOM（`utf-8-sig`），Excel 兼容
- **会话历史**: JSONL（每行一个 message 对象）
- **摘要**: JSON 数组
- **剧情记忆**: JSON 数组（含 metadata）

## 测试基线

当前自动化测试基线：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llama_service/tests play_api/tests agent_service/tests rpg_data/tests -q
```

这些测试 mock 外部 LLM、Telegram SDK 和网络调用，不需要真实 API key。若本地缺少 `pytest-asyncio`，`rpg_core/tests/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。

覆盖范围：

- `channels/tests/`：ChannelAdapter、CLI、AgentManager、Telegram 渠道。
- `rpg_core/tests/`：命令分发、上下文、scene、session、summary、AgentManager。
- `rp_memory/tests/`：memory 检索、索引、规划、rerank。
- `llama_service/tests/`：llama 本地服务客户端/服务端协议。
- `play_api/tests/`：Play API workspace/session/scene/chat 契约。

## 当前实现优先级

1. **P0：Telegram 渠道完善**。保障 Telegram 作为主要对话入口，包括真实运行、
   会话管理、stream/non-stream、异常回复、命令菜单、配置和日志。
2. **P1：核心数据与记忆链路**。确保角色卡、世界书、状态表、summary、memory
   在 Telegram 使用路径下稳定可用。
3. **P2：Play WebUI 管理能力**。在 Play WebUI 内完善数据维护能力，方便人工管理工作区、
   角色、世界书、状态表和会话。
4. **P3：Play WebUI Chat 体验**。继续完善 SSE 体验、tool records、stats、多会话聊天 UX
   和前端分包。
