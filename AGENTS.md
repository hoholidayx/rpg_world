# Repository Guidelines

## 项目结构与模块组织
本仓库采用 supervisor + 子进程的启动架构，统一批量启动入口是 `run.py`，同级提供 `run_all.py`、`run_api.py`、`run_telegram.py`、`run_cli.py` 作为快捷入口。核心业务逻辑位于 `rpg_core/`，其中 `agent/` 负责 LLM Agent 与命令分发，`context/` 负责上下文构建，`character/`、`lorebook/`、`status/`、`memory/`、`summary/` 分别处理领域数据。API 放在 `api/`，多渠道适配器与测试位于 `channels/` 和 `channels/tests/`。前端 WebUI 在 `webui/`，运行数据在 `data/`。
记忆检索拆成 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三个独立 retriever；`HybridRetriever` 只负责组装与融合，不承载底层检索实现。关键词检索通过 `memory.keyword_tokenizer` 选择 `jieba`、`bigram` 或 `both`，新增调参使用 `keyword_k` / `hybrid_keyword_weight`，不要恢复 `bigram_k` 或 `hybrid_bigram_weight`。raw markdown 由 `memory.raw_md_mode` 控制：`disabled` 完全关闭，`always` 作为主召回一路参与融合，`fallback_only` 仅在主召回不足或主检索失败时补候选；`raw_md_min_results=0` 时阈值为当前召回池目标（有 rerank 时是 `rerank_candidate_k`，否则是 `top_k`）。
LLM provider 统一位于 `rpg_core/llm/`，业务代码通过 `LLMManager.get().get_provider(biz_key)` 获取 provider，不直接 new OpenAI/llama 客户端，也不直接读取 `llm.yaml` 字符串 key。memory rerank 使用统一的 `PointwiseMemoryReranker`，不要恢复旧的 provider-specific reranker/factory。

修改启动流程、渠道生命周期或共享状态前，先阅读 `CLAUDE.md`。不要绕过 `run.py` 自行拼装多模块启动，也不要破坏 `AgentManager` 单例和配置边界。

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

本目录的 `pytest.ini` 必须保留 `asyncio_mode = auto`，否则 `channels/tests/` 中未显式标记的 `async def` 用例会报 `async def functions are not natively supported`。当前测试依赖来自上层项目 extras；如果 API 测试报 `ModuleNotFoundError: fastapi`，先在项目根运行 `uv sync --extra dev --extra api`（或安装等价 extras）后再跑测试。

pytest 启动时会通过根目录 `conftest.py` 清理 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及小写同名环境变量，避免本机 `ALL_PROXY=socks://127.0.0.1:7890` 这类 httpx 不支持的代理格式导致 `AsyncOpenAI`/httpx 初始化失败。需要刻意在测试中保留代理时，显式设置 `PYTEST_KEEP_PROXY=1`。

Telegram 是当前主聊天入口。修改 `channels/telegram/adapter.py`、`channels/telegram/session_flow.py` 或 Telegram 渲染逻辑时，必须补 `channels/tests/test_telegram.py`，覆盖普通消息、斜杠命令、会话菜单、二段式创建、stream 编辑节流、异常分支或 Markdown 分块中的相关行为。

API/WebUI 管理能力应补 `api/tests/` 的契约测试；核心上下文、memory、summary、session 行为应补 `rpg_core/tests/`。

修改主 agent 或 LLM provider 相关路径时，默认还要跑 `rpg_core/tests/integration/` 的真实集成验证，重点覆盖 `rpg_core/agent/agent.py`、`rpg_core/agent/command.py`、`rpg_core/llm/`、`rpg_core/session/manager.py`、`rpg_core/context/` 以及会影响这些路径的配置变更。若改动会触发真实 LLM 调用，先用 `INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q` 做门禁验证，再考虑提交。

## 提交与合并请求规范
提交信息遵循现有历史风格：`feat:`、`fix:`、`refactor:`、`chore:` 等前缀，后接简洁中文说明，例如 `feat: 实现向量记忆系统`。一次提交只处理一个逻辑主题。

PR 说明应写清影响模块、行为变化、配置变更（如 `settings.yaml`）、测试结果，以及是否影响现有工作区数据结构。涉及 `webui/` 可见改动时，附上界面截图。

## 配置与架构注意事项
`settings.yaml` 用于业务配置、模块启停、渠道参数和数据路径；`llm.yaml` 用于 LLM provider、模型、上下文窗口和超时等 LLM 强相关配置。二者都支持 `base + profiles`，profile 可通过 `file: *.local.yaml` 读取被 git ignore 的覆盖文件。`api/settings.json` 仅保留 API 服务级配置。每个子进程内部必须通过共享的 `AgentManager` 获取 agent，避免重复初始化 `FileWatcher`、缓存不一致或单进程内状态漂移。

配置访问必须走封装方法：`settings.memory_settings`、`settings.agent_model`、`channels.config.settings`、`resolve_biz_config()`、`get_runtime_config()` 或 `LLMManager`。不要在业务模块中手写 YAML key 路径或绕过 `Settings`/`llm.config` 直接解析配置。排序、检索、chunk 等业务参数保留在 `settings.yaml`，不要塞进 `llm.yaml` 的 provider block；例如 rerank 融合权重使用 `memory.rerank_score_weight`。

`llm.yaml` 中 `kind: rerank` 的 biz 配置必须显式声明 `rerank_model_type`。当前允许值为 `qwen3_logit`（本地 llama/Qwen3 reranker yes/no logits 打分）和 `chat_pointwise`（OpenAI chat 模型按 prompt 输出数字的兼容路径），并且 `LLMManager` 会校验 model type 与 provider 是否匹配。

`session_id` 只能由英文字母、数字、下划线组成，规则为 `^[A-Za-z0-9_]+$`，并会直接映射到 `sessions/{session_id}/` 目录。默认渠道会话名使用下划线格式，例如 `cli_direct`、`telegram_12345`。

工作区选择不要写回运行时状态。Telegram/CLI 的默认工作区来自 `settings.yaml` 的 `workspace` 字段，API/WebUI 通过请求参数传入 workspace，空 workspace 会解析为 API 默认工作区。运行数据、会话历史、摘要、向量索引和 SQLite WAL/SHM 文件都属于 `data/` 下的工作区数据，除非明确要求，不要把这些文件纳入提交。
