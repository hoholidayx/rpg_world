# RPG World — 故事数据管理与 LLM Agent 交互子系统

RPG World 是 nanobot 项目的一个子系统，专注于故事驱动的 RPG 数据管理和 LLM Agent 交互。提供角色卡管理、世界书管理、状态表管理、场景上下文构建等功能。

## 快速起步

```bash
# 安装依赖
uv sync

# 启动所有模块（读取 channels.json，按配置启动 API / Telegram / CLI）
uv run python -m rpg_world.run

# 仅启动 API
MODULES=api uv run python -m rpg_world.run

# 仅启动 Telegram（需先在 channels.json 配置 bot_token / workspace）
MODULES=telegram uv run python -m rpg_world.run

# 独立 CLI（无需 API / Telegram，直接 LLM 对话）
uv run python -m rpg_world.channels.cli.repl

# 启动 WebUI（另一个终端）
cd rpg_world/webui && npx vite
```

`channels.json` 当前默认关闭所有模块。开发时可通过 `MODULES=api`、
`MODULES=telegram`、`MODULES=api,telegram` 临时覆盖启用模块。

## 架构

### 统一进程 CS 架构

所有模块由 `run.py`（Launcher）在单一进程中统一启动，共享 `AgentManager` 单例：

```
进程 (run.py)
├── AgentManager 单例
│   ├── RPGGameAgent 实例池（按 session_id + api_key 缓存）
│   ├── FileWatcher（watchdog 文件监听）
│   └── BaseManager 缓存（角色/世界书/状态）
├── FastAPI（REST + SSE）
├── Telegram 长轮询（可选）
└── CLI REPL（可选）
```

模块启停通过 `channels.json` 配置，所有配置字段封装为类型化属性：

```python
from rpg_world.channels.config import settings as cfg

cfg.api_enabled       # modules.api.enabled
cfg.telegram_token    # modules.telegram.bot_token
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
- `chat_id` 默认映射为 `telegram_<chat_id>`，显式切换后会在当前 chat 内钉住 session。
- `proxy`、流式编辑间隔、最小编辑字符数、请求超时等参数由 `channels.json` 控制。

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

`memory/` 是一个独立的检索子系统，不再把向量、关键词、原始 markdown 扫描和 query 规划混在一个类里。当前结构按职责拆分为三层：

```text
memory/
├── planning/    QueryPlan 生成与 query rewrite
├── retrieval/   Dense / hybrid / raw markdown recall
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
     - keyword: bigram FTS 关键词召回
     - raw md: jieba/term coverage fallback
  -> scoring / fusion
  -> RecallItem 列表
```

### 子包职责

#### `planning/`

负责把用户 query 变成结构化 `QueryPlan`。

- `RuleBasedQueryPlanner`：无模型兜底，负责归一化、关键词抽取、jieba 切词
- `LlamaQueryPlanner`：可选，本地 gguf query planner
- `FallbackQueryPlanner`：运行时异常兜底，保证 recall 不被 planner 中断

#### `retrieval/`

负责实际召回，不负责 query 解析。

- `DenseRetriever`：纯向量召回
- `HybridRetriever`：向量 + bigram keyword + raw md 的融合召回
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
- `TextIndex`：FTS5 / keyword 索引实现
- `VectorStore`：存储门面，封装 repository + vector index + text index

### 配置

记忆系统的主要配置来自 `settings.json` 对应的 `MemorySettings`：

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

代码中已有 hybrid retrieval 和可选 rerank 结构，但当前 `settings.json`
默认配置尚未暴露完整的 hybrid/rerank 开关。新增配置前应同步更新
`rpg_core/settings.py`、README 和测试。

### 设计原则

- `MemoryManager` 负责组装，不负责检索细节
- `QueryPlanner` 是增强能力，不是主链路硬依赖
- bigram 查询格式始终由 tokenizer 保证
- raw md 兜底优先保证可用性，再逐步提升召回质量
- 检索层优先保持可解释的分数融合，避免把排序黑箱化

## 配置

### `channels.json` — 模块启停

```json
{
  "modules": {
    "api": {
      "enabled": false,
      "host": "127.0.0.1",
      "port": 8000,
      "reload": false
    },
    "telegram": {
      "enabled": false,
      "bot_token": "xxx",
      "streaming": true,
      "proxy": "http://127.0.0.1:7890",
      "workspace": "data/工作区名"
    },
    "cli": {
      "enabled": false,
      "workspace": "data/工作区名"
    }
  }
}
```

### `settings.json` — Agent 参数和数据路径

```json
{
  "agent_config": {
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com"
  },
  "character_path": "character",
  "lorebook_path": "lorebook"
}
```

工作区不再放在 `settings.json` 的 `active_workspace` 中。API/WebUI 通过请求参数选择
workspace；Telegram/CLI 通过 `channels.json` 中各自的 `workspace` 绑定。

## Session ID 规则

`session_id` 只能包含英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。
它会直接映射到 `sessions/{session_id}/` 目录，因此默认渠道会话名使用下划线格式，例如 `cli_direct`、`telegram_12345`。

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
- `channels.json` — 模块启停配置
- `settings.json` — agent 参数和数据路径配置
