# Repository Guidelines

## 项目结构与模块组织
本仓库采用 supervisor + 子进程的启动架构，统一批量启动入口是 `run.py`，同级提供 `run_all.py`、`run_api.py`、`run_telegram.py`、`run_cli.py` 作为快捷入口。核心业务逻辑位于 `rpg_core/`，其中 `agent/` 负责 LLM Agent 与命令分发，`context/` 负责上下文构建，`character/`、`lorebook/`、`status/`、`memory/`、`summary/` 分别处理领域数据。API 放在 `api/`，多渠道适配器与测试位于 `channels/` 和 `channels/tests/`。前端 WebUI 在 `webui/`，运行数据在 `data/`。

修改启动流程、渠道生命周期或共享状态前，先阅读 `CLAUDE.md`。不要绕过 `run.py` 自行拼装多模块启动，也不要破坏 `AgentManager` 单例和 `settings.yaml` 的配置边界。

当前产品优先级是 Telegram 渠道优先、核心数据链路其次、WebUI 数据管理后台再次、WebUI Chat 最后。涉及聊天体验的改动默认先保障 Telegram，不要为了 WebUI Chat 破坏 Telegram 的 session、stream 或命令行为。

## 构建、测试与开发命令
- `uv sync`：安装后端依赖。
- `uv run python -m rpg_world.run`：按 `settings.yaml` 启动全部启用模块，supervisor 拉起子进程。
- `uv run python -m rpg_world.run_all`：`run.py` 的同级快捷入口。
- `uv run python -m rpg_world.run_api`：API 快捷入口。
- `uv run python -m rpg_world.run_telegram`：Telegram 快捷入口。
- `uv run python -m rpg_world.run_cli`：CLI 快捷入口。
- `MODULES=api uv run python -m rpg_world.run`：仅启动 API，适合后端开发。
- `MODULES=telegram uv run python -m rpg_world.run`：仅启动 Telegram，适合验证主聊天入口。
- `MODULES=api,telegram uv run python -m rpg_world.run`：同时启动 API 与 Telegram，共享同一 `AgentManager`。
- `uv run uvicorn rpg_world.api.main:app --reload --reload-dir rpg_world --host 127.0.0.1 --port 8000`：直接调试 FastAPI。
- `uv run python -m rpg_world.channels.cli.repl`：启动独立 CLI 会话。
- `uv run python -m pytest channels/tests rpg_core/tests api/tests -q`：运行当前 Python 测试基线。
- `uv run python -m pytest channels/tests/test_telegram.py -q`：专项验证 Telegram 渠道。
- `cd webui && npm run dev`：启动前端开发服务器。
- `cd webui && npm run build`：构建前端产物。

## 代码风格与命名约定
Python 使用 4 空格缩进，函数、模块使用 `snake_case`，类使用 `PascalCase`。保持 `api/`、`channels/` 作为框架接入层，`rpg_core/` 作为无框架核心层，不要把 HTTP、Telegram 或 CLI 细节侵入核心模块。

Vue 代码沿用现有模式：组件文件使用 `PascalCase.vue`，store 与 composable 使用 `camelCase` 或 `useXxx`。新增注释应简短，只解释非直观逻辑。

## 测试约定
测试框架为 `pytest`，所有外部调用都应使用 mock，避免真实 LLM、Telegram 或网络依赖。新增测试文件命名为 `test_<feature>.py`。涉及渠道适配、命令分发、会话切换、管理器生命周期时，必须补对应测试。

Telegram 是当前主聊天入口。修改 `channels/telegram/adapter.py`、`channels/telegram/session_flow.py` 或 Telegram 渲染逻辑时，必须补 `channels/tests/test_telegram.py`，覆盖普通消息、斜杠命令、会话菜单、二段式创建、stream 编辑节流、异常分支或 Markdown 分块中的相关行为。

API/WebUI 管理能力应补 `api/tests/` 的契约测试；核心上下文、memory、summary、session 行为应补 `rpg_core/tests/`。

## 提交与合并请求规范
提交信息遵循现有历史风格：`feat:`、`fix:`、`refactor:`、`chore:` 等前缀，后接简洁中文说明，例如 `feat: 实现向量记忆系统`。一次提交只处理一个逻辑主题。

PR 说明应写清影响模块、行为变化、配置变更（如 `settings.yaml`）、测试结果，以及是否影响现有工作区数据结构。涉及 `webui/` 可见改动时，附上界面截图。

## 配置与架构注意事项
`settings.yaml` 是根配置唯一入口，用于模块启停、渠道参数、agent 配置和数据路径。profile 可通过 `file: settings.local.yaml` 读取被 git ignore 的覆盖文件。`api/settings.json` 仅保留 API 服务级配置。每个子进程内部必须通过共享的 `AgentManager` 获取 agent，避免重复初始化 `FileWatcher`、缓存不一致或单进程内状态漂移。

`session_id` 只能由英文字母、数字、下划线组成，规则为 `^[A-Za-z0-9_]+$`，并会直接映射到 `sessions/{session_id}/` 目录。默认渠道会话名使用下划线格式，例如 `cli_direct`、`telegram_12345`。

工作区选择不要写回运行时状态。Telegram/CLI 的默认工作区来自 `settings.yaml` 的 `workspace` 字段，API/WebUI 通过请求参数传入 workspace，空 workspace 会解析为 API 默认工作区。运行数据、会话历史、摘要、向量索引和 SQLite WAL/SHM 文件都属于 `data/` 下的工作区数据，除非明确要求，不要把这些文件纳入提交。
