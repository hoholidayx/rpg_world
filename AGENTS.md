# Repository Guidelines

## 工作边界
- 当前产品路线：WebUI 是沉浸式 RP 主体验，Telegram 是轻量入口、推送通知与兜底交互；短期仍保持 Telegram 稳定性，但新增体验型能力优先沉淀到 WebUI。
- Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口；不要恢复 Dashboard API/WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前，先阅读 `CLAUDE.md`。
- 根目录聚合 supervisor 入口已移除；各进程必须通过独立入口启动。只有 `run_agent.py` 持有 `AgentManager` / `RPGGameAgent` / `rp_memory` / llama lazy worker，其它进程只能通过 `agent_service.client.AgentClient` 访问 Agent 服务。
- 保持 `play_api/`、`channels/` 为接入层，`rpg_core/` 为无框架核心层；不要把 HTTP、Telegram、CLI 细节侵入核心模块。
- Play WebUI 会话内链路只使用全局短 `session_id` 定位；创建 session 时在 `rpg_data` 绑定 `workspace_id + story_id`，之后由 Play API 反查上下文并调用 Agent 服务。不要恢复前端每次传 `workspace + story_id + session_id` 的三元 locator。
- 玩家扮演角色是 session 级绑定，保存在 `rpg_session_profiles.player_character_id` 和 `player_character_snapshot_json`。WebUI 的选择/切换和 CLI/Telegram 文本渠道都必须统一走 Agent 服务的 `/role_bind <序号>` 命令链路；Play API 只能转发到 Agent service 后刷新 summary，不要直接在 Play API/DataManager 中写绑定。
- CLI / Telegram 也必须通过 `rpg_data` catalog 解析会话：配置使用 `workspace_id + story_id + optional session_id + session_title`；未配置 `session_id` 时由 Agent service 创建系统生成 ID 的 session，配置了则只校验并加载既有 session。不要恢复 `workspace` 字段、`cli_direct` 默认 ID 或用户自定义 session ID 创建入口。
- `AgentManager` 只按全局 `session_id` 缓存 agent；`api_key` 不再作为 Agent service schema、AgentClient 参数或缓存键。LLM key/provider 选择只走 `llm_service` 配置。
- `data/` 是运行数据目录。会话历史、摘要、向量索引、SQLite WAL/SHM 等文件默认不纳入提交。

## 常用命令
- `uv sync`：安装后端依赖。
- `uv run python -m run_agent`：启动 Agent 服务（默认 `http://127.0.0.1:8010/agent/v1`）。
- `uv run python -m run_play_api`：启动 Play API。
- `uv run python -m run_cli`：启动 CLI（通过 Agent 服务交互）。
- `uv run python -m run_telegram`：启动 Telegram（通过 Agent 服务交互）。
- `uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llm_service --host 127.0.0.1 --port 8000`：直接调试 Play API。
- `uv run python -m channels.cli.repl`：启动独立 CLI。
- `uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests -q`：运行 Python 测试基线。
- `uv run python -m pytest channels/tests/test_telegram.py -q`：专项验证 Telegram。
- `cd play_webui && npm run dev`：启动 Play 前端开发服务器。
- `cd play_webui && npm run build`：构建 Play 前端产物。

## 代码规范
- Python 使用 4 空格缩进，模块/函数用 `snake_case`，类用 `PascalCase`。
- Play WebUI 使用 Next.js App Router + React + TypeScript；React 组件用 `PascalCase.tsx`，hook/composable 用 `useXxx`，前端状态 store 用清晰的 camelCase 命名。
- 新增注释只解释非直观逻辑，避免复述代码。
- 配置访问必须走封装：`settings.memory_settings`、`settings.agent_model`、`channels.config.settings`、`resolve_biz_config()`、`get_runtime_config()` 或 `LLMManager`。
- 业务代码不要直接解析 YAML key，不要直接 new OpenAI/llama 客户端。

## 架构约束
- 记忆检索保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立；`HybridRetriever` 只负责组装与融合。
- keyword 配置使用 `keyword_k` / `hybrid_keyword_weight`，不要恢复 `bigram_k` 或 `hybrid_bigram_weight`。
- `memory.raw_md_mode` 语义保持：`disabled` 关闭，`always` 主召回，`fallback_only` 仅在主召回不足或失败时补候选。
- memory rerank 使用统一的 `PointwiseMemoryReranker`，不要恢复旧的 provider-specific reranker/factory。
- 上下文主流程保持结构化，最终发送给 LLM 前由 `ContextRenderer` 渲染；调试 markdown/token 概览放在 `ContextInspector`，不要回流到 `RPGContext` 数据模型。
- SessionRoom context 用量只通过两路数据展示：`context-preview` 提供估算摘要，正常 `/turn` 或 `/stream` 的完成事件携带 provider usage 作为准确值；不要新增独立 usage 获取接口，不要持久化 usage。后端只传 token/context window/cache 等元数据，比例、阈值和 K/M 展示由 Play WebUI 计算。
- `当前场景` 是高优先级 scene 状态，应作为 user prefix 进入最终用户消息；不要把它当普通状态表放入 `STATUS_TABLES`。在 `rpg_data` 状态表架构中，scene 是 `status_kind="scene"` 的状态表，仍必须挂载到 story 才能被 session 感知。
- RP Modules 是 RP 业务模块占位，不是通用 skill 体系；骰子、战斗、物品等能力应围绕 RP 工具流程和受控状态读写设计。
- `text_output_format` 是默认启用的 fixed layer 输出格式约束，不进入 `RPModuleRegistry`，用 `<rp-narration>` 和 `<rp-character name="...">` 约束 assistant 正文。带标签全文是 assistant `content` 真源，必须原样进入 SSE、历史和数据库；不要把旁白/角色分段写入 message metadata，也不要恢复 `metadata.messageDisplay`。
- `rpg_data` catalog 模型保持：workspace -> stories -> sessions；`rpg_story_characters` / `rpg_story_lorebook_entries` 是 story 挂载表，允许同一角色卡或世界书条目挂载到多个 story，只禁止同一 story 重复挂载。
- Story 主数据字段保持：`summary` 是短摘要，`first_message` 是会话开场首条消息模板，`story_prompt` 是 story 专属固定系统提示词，会通过 fixed layer 参与上下文渲染。
- 玩家角色绑定状态只对外暴露 `bound | invalid`。缺失绑定、角色不存在、未挂载、snapshot 损坏或 snapshot mount/story 不匹配都视为 `invalid`；WebUI 进入 SessionRoom 后用不可取消弹窗补选，Agent 在普通 send/send_stream 进入 LLM 前强校验，invalid 时只返回固定编号角色列表，不写 user history、不调用 LLM。绑定成功且 main history 为空时，`SessionRoleService` 追加 story `first_message` 到 main 和 backup，且只追加一次。
- `rpg_data` 状态表采用 SQLite document 真源：模板表与会话表都在 SQL 行内保存封装后的 `document_json`，`status_kind` 只允许 `scene` / `normal`，不再维护状态表 type 表、workspace-relative 状态表文件路径或 CSV 内容源。`rpg_data` 对外返回 `StatusTableDocument` / `StatusTableRow` 等 dataclass，不暴露原始 JSON 字符串作为正文数据。
- 状态表模板通过 `rpg_story_status_tables` 挂载到 story。创建 session 时由 `CatalogService` 触发复制已挂载模板的 `document_json` 到 `rpg_session_status_tables`，`origin="template_copy"`；后续模板修改不影响已有 session 副本。会话原生运行时表直接写入 `rpg_session_status_tables`，`origin="session_native"`。
- `rpg_data` bootstrap 只 materialize workspace/story/session 运行目录并初始化缺失的 session 状态表副本；不要在 bootstrap 代码中硬编码 demo 或业务数据。默认不删除不在 SQL 索引中的 workspace/story/session 目录；只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才会执行启动清理，并确保日志能清楚输出删除/跳过结果。
- Play API 会话内接口集中在 `/play-api/v1/sessions/{session_id}/history|scene|commands|turn|stream|player-character`；workspace、characters、lorebook、status-tables、ops 等管理接口也归 Play API；旧 `chat.py`、`scene.py`、`commands.py` router 仅作占位，不要把它们恢复为主入口。

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
- `llm_service/llm.yaml` 管 LLM provider、模型、上下文窗口和超时等 LLM 强相关配置。
- 它们都支持 `base + profiles`；`local` / `test` / `prod` 是固定 profile 名称，同级 `settings.local.yaml` / `llm.local.yaml` 等覆盖文件会自动加载。
- `llm.yaml` 中 `kind: rerank` 的 biz 配置必须显式声明 `rerank_model_type`，当前允许 `qwen3_logit` 和 `chat_pointwise`。
- `session_id` 只能使用英文字母、数字、下划线，规则为 `^[A-Za-z0-9_]+$`。所有 session 创建入口都由 `rpg_data` 生成 ID；用户只允许指定 title。
- 工作区选择不要写回运行时状态。Telegram/CLI 通过 `channels/settings.yaml` 配置 `workspace_id + story_id`，API/WebUI 通过请求参数或 catalog session 反查上下文。
- `rpg_data` 只通过 `rpg_workspaces.root_path` 定位 workspace 根目录；workspace/story/session 运行目录使用 workspace-relative 路径时，经 `rpg_data.settings.resolve_workspace_relative_path()` 解析并校验不逃逸 workspace。

## 提交规范
- 提交信息使用 `feat:`、`fix:`、`refactor:`、`chore:` 等前缀，后接清晰中文说明。
- 一次提交只处理一个逻辑主题。
- 提交前确认没有误纳入 `data/` 运行文件。
- PR 说明应包含影响模块、行为变化、配置变更、测试结果，以及是否影响现有工作区数据结构。
