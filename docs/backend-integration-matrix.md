# Backend Integration Test Matrix

后端测试分成三层：模块单元/契约测试、进程内 Core integration、真实本地 HTTP service integration。外部模型、Telegram SDK 和公网请求始终使用 deterministic fake；service integration 只访问随机 loopback 端口。

| 核心路径 | Core integration | Service integration | 关键断言 |
| --- | --- | --- | --- |
| Catalog Session 与角色绑定 | `test_agent_runtime`、`test_agent_service` | Play 查询真实 Session | 全局 `session_id`、invalid 门禁、首次绑定开场消息幂等 |
| 同步 turn | `test_agent_smoke` | Play → Agent → LLM | 固定层、RP 标签真源、usage、正数 turn/seq、主历史与冷备一致 |
| 流式 turn | `test_agent_smoke`、`test_agent_transactions` | Play SSE → Agent SSE → LLM SSE | DONE 只在 commit 后出现，最终正文与 `committedTurnId` 完整 |
| 失败与取消事务 | `test_agent_transactions`、`test_agent_service` | LLM 停机映射 | provider/缺失 DONE/取消均 discard，不留下部分消息、状态或裁定 |
| Mailbox 与并发 | `test_agent_runtime`、`test_agent_service` | 独立 Agent 进程 | 同 Session FIFO、活动/排队 requestId 停止、不同 Session 可并发 |
| Context 与模型选择 | `test_agent_runtime`、`test_agent_service` | Play context-preview | `summary_processed` 投影、门禁、config/story/session 优先级和切换快照 |
| Outcome、scene、普通状态 | `test_agent_transactions` | 经真实 chat 链路冒烟 | 预裁定、目标隔离、事务提交/回滚、scene 只改已有 key |
| Deferred 状态 | `test_agent_runtime` | — | 回复交付后、下一 mailbox 项前执行；批次失败隔离；值与进度原子提交 |
| Memory | `test_agent_runtime` | Agent → LLM embedding | 初始化不访问远端；首次 recall 懒解析；失败本地 fallback；后续重试 |
| Summary 与 Story Memory | `test_agent_runtime` | — | commit 后执行，失败不回滚；处理标记是真源且不截断历史 |
| `/clear` | `test_agent_runtime` | — | 清消息/状态/记忆/运行目录/Session 媒体引用，保留身份、配置、冷备和 Workspace Asset/Blob |
| 永久删除 | `test_agent_service` | Play → Agent → SQLite/runtime | 先关闭活动与排队 turn；完整级联删除；DB 失败恢复 runtime；删除后 404 |
| LLM Service | `llm_service/tests` | 真实 HTTP catalog/chat/stream/embed/rerank | health 免鉴权、业务鉴权、typed codec、远端不可用映射与 degraded health |
| Media 生成 | `rpg_media/tests`、`media_service/tests` | Play → Media → worker → 文件 | 来源指纹、VisualBrief、持久 job、Gallery、魔数存储、内容流式转发 |
| Media 背景与删除 | `media_service/tests` | 真实 Play/Media HTTP | 背景引用阻止 Asset 删除；媒体故障返回 503 且不影响聊天 |
| 服务生命周期 | 各 service lifespan 契约 | 四个独立子进程 | 随机端口、共享临时 SQLite、连接池 loop 归属、优雅关闭和无残留 |

## Commands

```bash
# 全后端单元与契约基线
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests -q

# 真实 SQLite + RPGGameAgent + Agent Service ASGI
INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q

# 独立 LLM / Agent / Media / Play 进程与真实 HTTP/SSE
SERVICE_INTEGRATION_TEST=1 uv run python -m pytest tests/integration -m service_integration -q

# 真实模型只做显式人工验证，不进入 PR 门禁
LIVE_LLM_TEST=1 INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration/test_live_llm.py -q
```

新增或调整跨模块核心行为时，应先更新本矩阵，再选择最低且足以覆盖真实边界的测试层。不要用 service integration 重复纯 schema、校验分支或 Provider 内部算法测试。
