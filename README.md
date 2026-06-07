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

# 独立 CLI（无需 API / Telegram，直接 LLM 对话）
uv run python -m rpg_world.channels.cli.repl

# 启动 WebUI（另一个终端）
cd rpg_world/webui && npx vite
```

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

### 核心引擎

| 模块 | 说明 |
|---|---|
| `agent/` | LLM Agent 引擎（消息队列、chat loop、子 Agent、命令系统） |
| `context/` | 5 层 RPG 上下文构建（Jinja2 模板） |
| `scene/` | 场景状态跟踪（时间/地点/属性） |
| `character/` | 角色卡 CRUD |
| `lorebook/` | 世界书 CRUD |
| `status/` | 状态表（CSV 表格） |
| `memory/` | 记忆存储（故事记忆、常驻记忆） |
| `summary/` | 对话摘要压缩 |

## 配置

### `channels.json` — 模块启停

```json
{
  "modules": {
    "api": { "enabled": true, "port": 8000, "reload": false },
    "telegram": { "enabled": true, "bot_token": "xxx", "streaming": true },
    "cli": { "enabled": false }
  }
}
```

### `settings.json` — Agent 参数和数据路径

```json
{
  "active_workspace": "data/工作区名",
  "agent_config": {
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com"
  }
}
```

## 测试

所有测试 mock LLM 调用，无需 API key：

```bash
uv run python -m pytest rpg_world/channels/tests/ -v
```

| 文件 | 测试数 | 说明 |
|---|---|---|
| `test_base.py` | 12 | 基类功能 |
| `test_cli.py` | 11 | CLI 渠道 |
| `test_manager.py` | 9 | AgentManager 单例 |
| `test_telegram.py` | 16 | Telegram 渠道 |

## 相关文档

- `CLAUDE.md` — 完整架构文档和技术细节
- `channels.json` — 模块启停配置
- `settings.json` — agent 参数和数据路径配置
