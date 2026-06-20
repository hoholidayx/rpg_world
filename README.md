# RPG World — 故事数据管理与 LLM Agent 交互子系统

RPG World 是 nanobot 项目的一个子系统，专注于故事驱动的 RPG 数据管理和 LLM Agent 交互。提供角色卡管理、世界书管理、状态表管理、场景上下文构建等功能。

## 快速起步

```bash
# 安装依赖
uv sync

# 启动所有模块（读取 settings.yaml，按配置启动 API / Telegram / CLI）
uv run python -m rpg_world.run

# 同级快捷入口，便于查找和调试
uv run python -m rpg_world.run_all
uv run python -m rpg_world.run_api
uv run python -m rpg_world.run_telegram
uv run python -m rpg_world.run_cli

# 仅启动 API
MODULES=api uv run python -m rpg_world.run

# 仅启动 Telegram（需先在 settings.yaml 配置 modules.telegram.bots）
MODULES=telegram uv run python -m rpg_world.run

# 独立 CLI（无需 API / Telegram，直接 LLM 对话）
uv run python -m rpg_world.channels.cli.repl

# 直接启动 API
uv run python -m rpg_world.api.main

# 启动 WebUI（另一个终端）
cd rpg_world/webui && npx vite
```

`settings.yaml` 当前默认关闭所有模块。开发时可通过 `MODULES=api`、
`MODULES=telegram`、`MODULES=api,telegram` 临时覆盖启用模块。

## 架构

### 进程隔离架构

`run.py` 是 supervisor，只负责按配置拉起子进程、转发信号和回收退出。API、
Telegram、CLI 都是独立进程，各自维护自己的 `AgentManager` 单例和运行时状态。

```
supervisor: rpg_world.run
├── api 子进程      -> uvicorn rpg_world.api.main:app
├── telegram 子进程 -> rpg_world.channels.telegram.runner
└── cli 子进程      -> rpg_world.channels.cli.repl
```

根目录还提供同级快捷入口，便于调试和查找：

```
run_all.py      -> rpg_world.run
run_api.py      -> rpg_world.api.main
run_telegram.py -> rpg_world.channels.telegram.runner
run_cli.py      -> rpg_world.channels.cli.repl
```

模块启停通过 `settings.yaml` 的 `modules` 配置，所有配置字段封装为类型化属性：

```python
from rpg_world.channels.config import settings as cfg

cfg.api_enabled       # modules.api.enabled
cfg.telegram_bots     # modules.telegram.bots
cfg.cli_enabled       # modules.cli.enabled
cfg.enabled_module_names  # 所有已启用的模块名列表
```

### 多渠道适配器

所有外部交互渠道继承同一抽象基类 `ChannelAdapter`：

| 渠道 | 实现 | 技术栈 |
|---|---|---|
| CLI | `channels/cli/adapter.py` | Rich + prompt_toolkit |
| Telegram | `channels/telegram/adapter.py` | python-telegram-bot |
| 未来 | 只需继承 ChannelAdapter | 实现 start/stop/send_text 即可 |

当前实现优先保障 Telegram 作为主要对话入口。WebUI 定位为个人数据管理后台，
Chat 页面保留基础调试能力，完整聊天体验放在 Telegram 稳定后再完善。

### Telegram 渠道

Telegram 渠道当前支持：

- 长轮询启动与优雅关闭。
- `streaming=true` 时通过编辑消息实现流式输出。
- Markdown 到 Telegram HTML 的渲染与 4096 字符分块发送。
- `/start`、后端斜杠命令透传，以及 Telegram 菜单命令规范化。
- `/sessions` 会话菜单、按钮切换会话、`/session_create` 二段式创建、`/cancel` 取消。
- `chat_id` 默认映射为 `telegram_<bot_name>_<chat_id>`，显式切换后会在当前 chat 内钉住 session。
- `proxy`、流式编辑间隔、最小编辑字符数、请求超时等参数由 `settings.yaml` 的 bot 配置控制。

### 核心引擎

| 模块 | 说明 |
|---|---|
| `agent/` | LLM Agent 引擎（消息队列、chat loop、子 Agent、命令系统） |
| `context/` | 5 层 RPG 上下文构建（Jinja2 模板） |
| `scene/` | 场景状态跟踪（时间/地点/属性） |
| `character/` | 角色卡 CRUD |
| `lorebook/` | 世界书 CRUD |
| `status/` | 状态表（CSV 表格） |
| `memory/` | 记忆系统（检索、索引、规划、召回） |
| `summary/` | 对话摘要压缩 |

## 记忆系统

`memory/` 是一个独立的检索子系统，不再把向量、bigram FTS、原始 markdown 扫描和 query 规划混在一个类里。当前结构按职责拆分为三层：

```text
memory/
├── planning/    QueryPlan 生成与 query rewrite
├── retrieval/   SqlVec / bigram / raw markdown recall
├── rerank/      可选的 llama 本地重排
└── storage/     SQLite repository、vector index、text index
```

### 运行链路

```text
用户 query
  -> MemoryManager
  -> QueryPlanner
     - 优先使用本地 gguf + llama-cpp-python
     - 配置缺失或加载失败时降级到 rule-based planner
  -> Retrieval
     - vector: 向量相似度召回
     - bigram: bigram FTS 召回
     - raw md: jieba/term coverage fallback
  -> scoring / fusion
  -> RecallItem 列表
```

### 子包职责

#### `planning/`

负责把用户 query 变成结构化 `QueryPlan`。

- `RuleBasedQueryPlanner`：无模型兜底，负责归一化、term extraction、jieba 切词
- `LlamaQueryPlanner`：可选，本地 gguf query planner
- `FallbackQueryPlanner`：运行时异常兜底，保证 recall 不被 planner 中断

#### `retrieval/`

负责实际召回，不负责 query 解析。

- `SqlVecRetriever`：纯向量召回
- `HybridRetriever`：组装 sqlvec + bigram + raw md 的融合召回
- `RawMarkdownGrepSearch`：直接扫描 markdown 文件，作为最后兜底
- `RawMarkdownRetriever`：只走 raw md 的 retriever 适配器

#### `rerank/`

负责可选的最终重排，不参与召回和 query 解析。

- `LlamaRerankConfig`：重排配置
- `LlamaReranker`：本地 gguf + llama-cpp-python 重排器

#### `storage/`

负责持久化和底层索引。

- `MemoryRepository`：SQLite chunk 存取
- `VectorIndex`：向量索引实现
- `TextIndex`：FTS5 / bigram 索引实现
- `VectorStore`：存储门面，封装 repository + vector index + text index

### 配置

记忆系统的主要配置来自 `settings.yaml` 对应的 `MemorySettings`：

- 向量模型路径与 embedding 参数
- `query_planner_enabled`
- `query_planner_model_path`
- `query_planner_n_ctx`
- `query_planner_n_gpu_layers`
- `query_planner_temperature`
- `query_planner_max_tokens`
- `top_k`
- `chunk_size`
- `chunk_overlap`

代码中已有 sqlvec + bigram + raw md 三路独立 retriever，`HybridRetriever` 只负责组装与融合。
当前 `settings.yaml` 默认配置尚未暴露完整的 hybrid/rerank 开关。新增配置前应同步更新
`rpg_core/settings.py`、README 和测试。

### 设计原则

- `MemoryManager` 负责组装，不负责检索细节
- `QueryPlanner` 是增强能力，不是主链路硬依赖
- bigram 查询格式始终由 tokenizer 保证
- raw md 兜底优先保证可用性，再逐步提升召回质量
- 检索层优先保持可解释的分数融合，避免把排序黑箱化

## 配置

### `settings.yaml` — 唯一根配置入口

根配置使用 `base + profiles`，通过 `RPG_WORLD_PROFILE` 选择 profile，默认 `local`。
profile 可以内联写覆盖，也可以通过 `file` 读取一个被 git ignore 的覆盖文件：

```yaml
base:
  agent:
    model: deepseek-v4-flash
    base_url: https://api.deepseek.com
    api_key_env: OPENAI_API_KEY_LOCAL
  data:
    character_path: character
    lorebook_path: lorebook
  modules:
    telegram:
      enabled: false
      bots:
        - name: main
          enabled: false
          token_env: TELEGRAM_BOT_TOKEN_MAIN
          workspace: data/工作区名
profiles:
  local:
    file: settings.local.yaml
  prod:
    file: settings.prod.yaml
```

`settings.*.yaml` 已被 `.gitignore` 忽略。文件不存在时按空覆盖处理；如果希望缺失时报错，
可写 `required: true`。同一个 profile 同时写内联覆盖和 `file` 时，先合并内联覆盖，
再合并文件覆盖。

工作区不再放在旧 JSON 配置中。API/WebUI 通过请求参数选择 workspace；
Telegram/CLI 通过 `settings.yaml` 中各自的 `workspace` 绑定。

## Session ID 规则

`session_id` 只能包含英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。
它会直接映射到 `sessions/{session_id}/` 目录，因此默认渠道会话名使用下划线格式，例如 `cli_direct`、`telegram_main_12345`。

### 会话历史字段

`history.jsonl` 中每条消息会持久化 `hid`、`turn_id`、`seq_in_turn` 等字段。`hid` 只是记录用的消息标识，
故事记忆和压缩等逻辑统一按 `turn_id` 计数。

## 测试

所有测试 mock LLM 调用，无需 API key：

```bash
uv run python -m pytest channels/tests rpg_core/tests api/tests -q
```

当前基线：`110 passed, 1 warning`。覆盖范围包括：

- `channels/tests/`：ChannelAdapter、CLI、AgentManager、Telegram 渠道。
- `rpg_core/tests/`：命令分发、上下文、memory、scene、session、summary、AgentManager。
- `api/tests/`：workspace/session/character/lorebook/status/chat 契约。

Telegram 测试已覆盖会话菜单、命令规范化、二段式创建、流式编辑节流、
Markdown 渲染和长文本分块。后续修改 Telegram 行为必须补对应测试。

## 当前实现优先级

1. **P0：Telegram 渠道稳定性**。优先保障真实 Telegram 长轮询、会话管理、
   stream/non-stream、异常回复、命令菜单和运行配置可靠。
2. **P1：核心数据与记忆链路**。确保角色卡、世界书、状态表、summary、memory
   在 Telegram 主入口下稳定可用。
3. **P2：WebUI 数据管理后台**。优先完善角色、世界书、状态、workspace、session
   管理能力，方便人工维护数据。
4. **P3：WebUI Chat 体验**。最后再完善 SSE、tool records、stats、聊天 UX 和前端分包。

## 相关文档

- `CLAUDE.md` — 完整架构文档和技术细节
- `settings.yaml` — 根配置、模块启停、agent 参数和数据路径配置
