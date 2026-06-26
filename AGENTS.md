# Repository Guidelines

## 工作边界
- 当前产品路线：WebUI 是沉浸式 RP 主体验，Telegram 是轻量入口、推送通知与兜底交互；短期仍保持 Telegram 稳定性，但新增体验型能力优先沉淀到 WebUI。
- Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口；不要恢复 Dashboard API/WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前，先阅读 `CLAUDE.md`。
- 根目录聚合 supervisor 入口已移除；各进程必须通过独立入口启动。只有 `run_agent.py` 持有 `AgentManager` / `RPGGameAgent` / `rp_memory` / llama lazy worker，其它进程只能通过 `agent_service.client.AgentClient` 访问 Agent 服务。
- 保持 `play_api/`、`channels/` 为接入层，`rpg_core/` 为无框架核心层；不要把 HTTP、Telegram、CLI 细节侵入核心模块。
- `data/` 是运行数据目录。会话历史、摘要、向量索引、SQLite WAL/SHM 等文件默认不纳入提交。

## 常用命令
- `uv sync`：安装后端依赖。
- `uv run python -m run_agent`：启动 Agent 服务（默认 `http://127.0.0.1:8010/agent/v1`）。
- `uv run python -m run_play_api`：启动 Play API。
- `uv run python -m run_cli`：启动 CLI（通过 Agent 服务交互）。
- `uv run python -m run_telegram`：启动 Telegram（通过 Agent 服务交互）。
- `uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llama_service --host 127.0.0.1 --port 8000`：直接调试 Play API。
- `uv run python -m channels.cli.repl`：启动独立 CLI。
- `uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llama_service/tests play_api/tests agent_service/tests rpg_data/tests -q`：运行 Python 测试基线。
- `uv run python -m pytest channels/tests/test_telegram.py -q`：专项验证 Telegram。
- `cd play_webui && npm run dev`：启动 Play 前端开发服务器。
- `cd play_webui && npm run build`：构建 Play 前端产物。

## 代码规范
- Python 使用 4 空格缩进，模块/函数用 `snake_case`，类用 `PascalCase`。
- Vue 组件使用 `PascalCase.vue`，store/composable 使用 `camelCase` 或 `useXxx`。
- 新增注释只解释非直观逻辑，避免复述代码。
- 配置访问必须走封装：`settings.memory_settings`、`settings.agent_model`、`channels.config.settings`、`resolve_biz_config()`、`get_runtime_config()` 或 `LLMManager`。
- 业务代码不要直接解析 YAML key，不要直接 new OpenAI/llama 客户端。

## 架构约束
- 记忆检索保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立；`HybridRetriever` 只负责组装与融合。
- keyword 配置使用 `keyword_k` / `hybrid_keyword_weight`，不要恢复 `bigram_k` 或 `hybrid_bigram_weight`。
- `memory.raw_md_mode` 语义保持：`disabled` 关闭，`always` 主召回，`fallback_only` 仅在主召回不足或失败时补候选。
- memory rerank 使用统一的 `PointwiseMemoryReranker`，不要恢复旧的 provider-specific reranker/factory。
- 上下文主流程保持结构化，最终发送给 LLM 前由 `ContextRenderer` 渲染；调试 markdown/token 概览放在 `ContextInspector`，不要回流到 `RPGContext` 数据模型。
- `当前场景.csv` 是高优先级 scene 状态，应作为 user prefix 进入最终用户消息；不要把它当普通状态表放入 `STATUS_TABLES`。
- RP Modules 是 RP 业务模块占位，不是通用 skill 体系；骰子、战斗、物品等能力应围绕 RP 工具流程和受控状态读写设计。

## 测试要求
- 所有外部调用使用 mock，避免真实 LLM、Telegram 或网络依赖。
- 新增测试文件命名为 `test_<feature>.py`。
- 修改 Telegram 适配、会话流程或渲染逻辑时，必须补 `channels/tests/test_telegram.py`。
- 修改 API/Play WebUI 管理能力时，补 `play_api/tests/` 契约测试。
- 修改核心上下文、summary、session 行为时，补 `rpg_core/tests/`；修改 memory 行为时，补 `rp_memory/tests/`。
- 修改主 agent、LLM provider、session manager、context 或相关配置时，默认跑：
  `INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q`。
- 保留 `pytest.ini` 中的 `asyncio_mode = auto`。
- pytest 默认会清理代理环境变量；需要保留代理时显式设置 `PYTEST_KEEP_PROXY=1`。

## 配置与数据
- 配置按进程/模块拆分：`rpg_core/settings.yaml` 管核心业务配置，`agent_service/settings.yaml` 管 Agent 服务监听与客户端默认值，`channels/settings.yaml` 管 CLI/Telegram 行为，`play_api/settings.yaml` 管 Play API 监听与日志。
- `llama_service/llm.yaml` 管 LLM provider、模型、上下文窗口和超时等 LLM 强相关配置。
- 它们都支持 `base + profiles`；`local` / `test` / `prod` 是固定 profile 名称，同级 `settings.local.yaml` / `llm.local.yaml` 等覆盖文件会自动加载。
- `llm.yaml` 中 `kind: rerank` 的 biz 配置必须显式声明 `rerank_model_type`，当前允许 `qwen3_logit` 和 `chat_pointwise`。
- `session_id` 只能使用英文字母、数字、下划线，规则为 `^[A-Za-z0-9_]+$`。
- 工作区选择不要写回运行时状态。Telegram/CLI 默认工作区来自 `settings.yaml`，API/WebUI 通过请求参数传入。

## 提交规范
- 提交信息使用 `feat:`、`fix:`、`refactor:`、`chore:` 等前缀，后接清晰中文说明。
- 一次提交只处理一个逻辑主题。
- 提交前确认没有误纳入 `data/` 运行文件。
- PR 说明应包含影响模块、行为变化、配置变更、测试结果，以及是否影响现有工作区数据结构。
