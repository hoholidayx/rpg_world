# 数据模块与 Play WebUI MVP 重构计划

## 0. 背景与目标

当前方向调整为：**Play WebUI 作为唯一 Web 主体验**，同时承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口；Dashboard API 和 Dashboard WebUI 已删除，后续不要恢复依赖。

本计划以“最小 MVP 但直接面向目标架构”为原则，不做旧文件存量数据兼容，也不迁移 `data/` 下已有测试数据。新的数据源从第一版开始即以 SQLite 数据库为权威来源，文件系统仅保留配置、记忆原文/导入导出文件、临时运行产物和后续备份用途。

### 0.1 MVP 成功标准

- 启动 `run_agent.py` 与 `run_play_api.py` 后，Play WebUI 可以从真实数据库读取故事、会话、角色、世界书、状态、场景与最近会话。
- Play WebUI 可以创建故事、创建会话、进入 Play Room、发送一轮消息并看到 SSE 流式结果。
- 一轮消息会在数据库中形成完整的 `session -> turn -> messages -> turn_events` 记录。
- 场景 HUD、角色列表、已 pin 状态和调试事件可以从数据库刷新。
- Dashboard API/WebUI 不再作为 MVP 依赖。
- `data/` 下旧 `history.jsonl`、`session.json`、角色 JSON、世界书 JSON、状态 CSV 测试数据不需要迁移，也不要求兼容。

### 0.2 非目标

- 不做多用户账号体系，只预留 `owner_id` / `player_id` 字段。
- 不做远程 DB / PostgreSQL，MVP 使用 SQLite。
- 不做旧 Dashboard 功能完整平移后再启动 MVP；Play WebUI 只实现最小必要管理能力。
- 不做旧 JSON/CSV/JSONL 数据导入迁移。
- 不合并 `rp_memory` 的向量索引数据库；记忆检索仍保持独立。
- 不引入独立 Data Service 进程；先使用共享无状态数据模块。

## 1. 架构决策

### 1.1 选择：共享无状态数据模块

新增一个无状态、无框架依赖的数据模块，建议命名为 `rpg_data`：

```text
rpg_data/
  __init__.py
  db.py
  settings.py
  migrations/
  repositories/
  services/
  schemas/
  tests/
```

`rpg_data` 的职责：

- 统一 SQLite 连接创建与事务管理。
- 维护 schema migration。
- 提供 repository / service 层给 Agent 进程和 Play API 进程复用。
- 定义数据库 DTO / Pydantic schema / dataclass。
- 提供测试用临时数据库 fixture。

`rpg_data` 不做：

- 不持有 `AgentManager` / `RPGGameAgent`。
- 不调用 LLM。
- 不包含 FastAPI、Telegram、CLI、Next.js 细节。
- 不保存进程内业务状态。
- 不用全局单例缓存 repository 数据。

### 1.2 进程职责边界

```text
play_webui
  -> play_api
      -> DataManagerBackend: 读写故事/角色/世界书/状态/会话元数据/UI 状态
      -> AgentBackend: 发送消息、SSE、retry、rollback、fork 等运行时操作

agent_service
  -> RPGGameAgent / AgentManager
      -> rpg_data: turn/history/event/scene/status runtime 写入
      -> rp_memory: 独立记忆索引与召回
```

核心原则：

- `play_api` 可以直接通过 `rpg_data` 管理**配置类与产品类数据**。
- `agent_service` 负责**会影响 Agent 内存态的运行时写入**。
- Play WebUI 的一次发送消息必须走 Agent backend，不允许 DataManager backend 直接插入 active message。
- 数据一致性不靠 `rpg_data` 的内存状态，而靠事务、版本字段、更新时间、Agent runtime 刷新策略和必要的事件记录维护。

### 1.3 Play API 双 backend 设计

当前 `play_api/backends` 只有面向 chat 的 `PlayBackend` 抽象。MVP 需要拆成两个职责：

```text
play_api/backends/agent_backend.py
  - send / stream
  - commands
  - retry / rollback / fork / snapshot restore
  - Agent runtime 写操作

play_api/backends/data_manager_backend.py
  - workspace / story / session metadata
  - character / lorebook / status CRUD
  - scene read / UI state read
  - pins / favorites / journal
  - room-state aggregation
```

推荐接口：

```python
class PlayAgentBackend(Protocol):
    async def send(...): ...
    async def stream(...): ...
    async def list_commands(...): ...
    async def retry_turn(...): ...
    async def rollback_to_turn(...): ...
    async def fork_session(...): ...

class PlayDataManagerBackend(Protocol):
    async def list_stories(...): ...
    async def create_story(...): ...
    async def list_sessions(...): ...
    async def create_session(...): ...
    async def get_room_state(...): ...
    async def list_characters(...): ...
    async def upsert_character(...): ...
    async def list_lorebook_entries(...): ...
    async def upsert_status_row(...): ...
    async def patch_scene(...): ...
```

### 1.4 数据一致性策略

`rpg_data` 是无状态模块，所以一致性不依赖“共享 Python 对象”，而依赖以下规则：

1. **单轮 Agent 写入事务**：一次 turn 结束时，至少保证 `turns/messages/turn_events/scene_patches` 写入一致。
2. **Agent 热缓存刷新**：Agent 在每轮开始前读取必要的角色/世界书/状态版本；发现版本变化则刷新 manager/cache。
3. **版本字段**：核心表带 `version INTEGER NOT NULL DEFAULT 1` 与 `updated_at`。
4. **运行时写入归属**：Play API 不直接写 active turn/message；需要通过 Agent backend。
5. **UI 聚合读取可最终一致**：Play Room 的 `room-state` 可以在 `turn.done` 后刷新；流式过程中依赖 SSE events。
6. **SQLite WAL**：启用 WAL、foreign keys、busy timeout，支持 agent_service 与 play_api 多进程读写。

## 2. 数据库存储范围

### 2.1 SQLite 作为权威来源的数据

MVP 中以下数据直接以数据库为权威：

- workspace / story / story settings。
- session metadata。
- turns / messages / turn events。
- scene runtime。
- characters / character details / relations。
- lorebook entries。
- status types / tables / rows / pinned status。
- favorites / journal / recent sessions。
- debug events / tool events。
- snapshots / branch metadata 的最小结构。

### 2.2 文件系统保留的数据

- `rpg_core/settings.yaml`、`agent_service/settings.yaml`、`play_api/settings.yaml` 等进程配置。
- `llm_service/llm.yaml`。
- 记忆原文、导入导出包、手工备份。
- `rp_memory` 自己维护的向量索引或 FTS 数据库。
- SQLite WAL/SHM 运行文件。

### 2.3 不兼容的 legacy 数据

MVP 不读取、迁移或兼容以下旧数据：

- `data/<workspace>/sessions/<session_id>/history.jsonl`。
- `history_cold.jsonl`。
- `session.json`。
- `rpg_summaries.json` / `persistent_memory.json`。
- `character/*.json`。
- `lorebook/*.json`。
- `status/**/*.csv`。

这些旧路径可以在后续清理，但 MVP 实现时不要为了兼容它们增加分支逻辑。

## 3. MVP 数据模型草案

### 3.1 命名约定

- 主键统一使用 TEXT id，MVP 可用 `uuid4().hex`。
- 表中保留 `workspace_id`、`story_id`、`session_id` 便于查询。
- 所有核心表包含 `created_at`、`updated_at`。
- 可编辑表包含 `version`。
- JSON 扩展字段使用 `metadata_json` 或 `payload_json` TEXT。

### 3.2 Core tables

```sql
CREATE TABLE workspaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE stories (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  summary TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  cover_asset_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  current_turn_id INTEGER NOT NULL DEFAULT 0,
  forked_from_session_id TEXT,
  forked_from_turn_id INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
```

### 3.3 World config tables

```sql
CREATE TABLE characters (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  story_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'npc',
  summary TEXT,
  avatar_asset_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(story_id, name)
);

CREATE TABLE character_details (
  id TEXT PRIMARY KEY,
  character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  content TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE lorebook_entries (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  story_id TEXT NOT NULL,
  name TEXT NOT NULL,
  content TEXT NOT NULL,
  keywords_json TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(story_id, name)
);
```

### 3.4 Status and scene tables

```sql
CREATE TABLE status_types (
  id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(story_id, name)
);

CREATE TABLE status_tables (
  id TEXT PRIMARY KEY,
  status_type_id TEXT NOT NULL REFERENCES status_types(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  columns_json TEXT NOT NULL DEFAULT '[]',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(status_type_id, name)
);

CREATE TABLE status_rows (
  id TEXT PRIMARY KEY,
  status_table_id TEXT NOT NULL REFERENCES status_tables(id) ON DELETE CASCADE,
  row_json TEXT NOT NULL,
  pinned INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE scene_states (
  session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  location TEXT,
  scene_time TEXT,
  weather TEXT,
  mood TEXT,
  present_characters_json TEXT NOT NULL DEFAULT '[]',
  attrs_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE scene_patches (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER,
  patch_json TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

### 3.5 Turn and event tables

```sql
CREATE TABLE turns (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'play_webui',
  input_mode TEXT NOT NULL DEFAULT 'IC',
  status TEXT NOT NULL DEFAULT 'completed',
  snapshot_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(session_id, turn_id)
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER NOT NULL,
  seq_in_turn INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  visible_content TEXT,
  source TEXT NOT NULL DEFAULT 'play_webui',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(session_id, turn_id, seq_in_turn)
);

CREATE TABLE turn_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE(session_id, turn_id, seq)
);
```

### 3.6 UI tables

```sql
CREATE TABLE recent_sessions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  story_id TEXT NOT NULL,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  last_opened_at TEXT NOT NULL,
  UNIQUE(workspace_id, session_id)
);

CREATE TABLE favorites (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER,
  message_id TEXT,
  label TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE journal_entries (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  turn_id INTEGER,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

## 4. Backend 方案细化

### 4.1 `rpg_data.db`

MVP 功能：

- `connect(db_path: Path) -> sqlite3.Connection`。
- 启用 `PRAGMA foreign_keys = ON`。
- 启用 `PRAGMA journal_mode = WAL`。
- 设置 `PRAGMA busy_timeout = 5000`。
- Row factory 使用 `sqlite3.Row`。
- 提供 `transaction(conn)` context manager。

### 4.2 `rpg_data.settings`

MVP 功能：

- 从 `RPG_WORLD_DB_PATH` 读取 DB 路径。
- 默认路径为 `data/.runtime/rpg_world.sqlite3`。
- 不解析复杂 YAML，避免新增配置面。

### 4.3 Migration

MVP 功能：

- `schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)`。
- `rpg_data.migrations.run_migrations(conn)`。
- 每个 migration 是 `.sql` 文件。
- 测试中可以在临时 DB 上重复运行 migration，确保幂等。

### 4.4 Repository

MVP repository 列表：

```text
WorkspaceRepository
StoryRepository
SessionRepository
CharacterRepository
LorebookRepository
StatusRepository
SceneRepository
TurnRepository
RoomStateRepository
```

原则：

- repository 只接受 `sqlite3.Connection`。
- repository 不自己持有全局连接。
- service 可以组合多个 repository。
- 所有写方法要求调用方已在事务里，或者内部用短事务。

### 4.5 DataManagerBackend

新增：

```text
play_api/backends/data_manager.py
play_api/deps.py 或 play_api/backends/factory.py 中提供 get_data_manager_backend()
```

MVP 方法：

- `list_stories(workspace_id)`。
- `create_story(workspace_id, title, summary)`。
- `list_sessions(story_id)`。
- `create_session(story_id, title)`。
- `get_room_state(session_id)`。
- `list_characters(story_id)`。
- `list_lorebook_entries(story_id)`。
- `list_status_overview(story_id, session_id)`。
- `get_scene(session_id)`。
- `patch_scene(session_id, patch)`。

### 4.6 AgentBackend

保留现有 AgentClient 调用，但重命名职责：

- `send()`。
- `stream()`。
- `list_commands()`。
- 后续扩展 `retry_turn()` / `fork_session()` / `rollback_to_turn()`。

Play API route 根据操作选择 backend：

- 读故事/角色/状态/room-state：DataManagerBackend。
- 发消息/流式：AgentBackend。
- turn 完成后：前端刷新 DataManagerBackend 的 room-state。

## 5. Agent 侧改造

### 5.1 SessionManager 目标

MVP 不再写 `history.jsonl`，直接写 DB。

目标接口：

```python
class SessionManager:
    def begin_turn(self) -> int: ...
    def append(role, content, turn_id, seq_in_turn=None, metadata=None): ...
    def end_turn(turn_id): ...
    def history(self) -> list[Message]: ...
    def load(self): ...
```

实现变化：

- `load()` 从 `messages` 表读取。
- `append()` 写 `messages` 表。
- `begin_turn()` 写 `turns` 表或预创建 pending turn。
- `end_turn()` 更新 turn status 和 session current_turn_id。
- 不再维护 JSONL / cold JSONL。

### 5.2 SceneTracker 目标

MVP 不再写 `status/全局状态/当前场景.csv`。

目标：

- `SceneTracker.get_context()` 从 `scene_states` 渲染。
- `scene_time`、`scene_attr`、`scene_del_attr` 写 `scene_states` 和 `scene_patches`。
- 保持 scene 作为 user prefix 的语义。

### 5.3 Character/Lorebook/Status manager 目标

MVP 可先做 DB-backed manager，保留类名，减少 Agent 上下文构建改动。

- `CharacterManager` 从 `characters/character_details` 读取。
- `LorebookManager` 从 `lorebook_entries` 读取。
- `StatusManager` 从 `status_*` 表读取普通状态。
- 旧 JSON/CSV loader 可删除或不再接入新路径。

### 5.4 Turn events

Agent stream 过程中将事件写入 DB：

- `round_start`。
- `thinking`。
- `tool_call`。
- `tool_result`。
- `text_delta` 或最终 assistant message。
- `done`。
- `error`。

MVP 可以先在 stream 结束时批量写事件，避免流式过程中频繁锁 DB；后续再做实时 event persistence。

## 6. Play WebUI MVP 页面与 API

### 6.1 首页

数据来源：DataManagerBackend。

需要 API：

- `GET /play-api/v1/stories`。
- `POST /play-api/v1/stories`。
- `GET /play-api/v1/recent-sessions`。

### 6.2 Story 详情

需要 API：

- `GET /play-api/v1/stories/{story_id}`。
- `GET /play-api/v1/stories/{story_id}/sessions`。
- `POST /play-api/v1/stories/{story_id}/sessions`。
- `GET /play-api/v1/stories/{story_id}/characters`。
- `GET /play-api/v1/stories/{story_id}/lorebook`。
- `GET /play-api/v1/stories/{story_id}/status-overview`。

### 6.3 Play Room

需要 API：

- `GET /play-api/v1/sessions/{session_id}/room-state`。
- `GET /play-api/v1/sessions/{session_id}/turns`。
- `POST /play-api/v1/sessions/{session_id}/turn`。
- `POST /play-api/v1/sessions/{session_id}/turn/stream`。
- `PATCH /play-api/v1/sessions/{session_id}/scene`。

Room state 返回：

```ts
type RoomState = {
  session: SessionSummary;
  story: StorySummary;
  scene: SceneState;
  characters: CharacterSummary[];
  pinnedStatus: StatusCard[];
  recentTurns: TurnSummary[];
  debugEvents: TurnEvent[];
  quickActions: QuickAction[];
};
```

### 6.4 角色/状态总览

需要 API：

- `GET /play-api/v1/stories/{story_id}/characters`。
- `POST /play-api/v1/stories/{story_id}/characters`。
- `PUT /play-api/v1/characters/{character_id}`。
- `GET /play-api/v1/stories/{story_id}/status`。
- `POST /play-api/v1/stories/{story_id}/status/tables`。
- `POST /play-api/v1/status/tables/{table_id}/rows`。
- `PUT /play-api/v1/status/rows/{row_id}`。

## 7. 实施步骤与可复制 Codex 提示词

以下步骤尽量拆到可单独执行、可测试、可回滚。每一步的提示词都假设在 `/workspace/rpg_world` 仓库内执行。

### Step 1：新增 `rpg_data` 基础包与 SQLite 连接

目标：创建无状态数据模块，提供连接、事务、settings。

Codex 提示词：

```text
请在 /workspace/rpg_world 中实现数据模块 MVP 的第一步：新增无框架依赖的 rpg_data 包。
要求：
1. 新增 rpg_data/__init__.py、rpg_data/settings.py、rpg_data/db.py。
2. settings.py 提供 get_database_path()，优先读取 RPG_WORLD_DB_PATH，默认 data/.runtime/rpg_world.sqlite3。
3. db.py 提供 connect(db_path=None) 和 transaction(conn) context manager。
4. connect 需要创建父目录，启用 foreign_keys、WAL、busy_timeout，并设置 row_factory=sqlite3.Row。
5. 不要引入 FastAPI，不要依赖 agent_service/play_api。
6. 增加 rpg_data/tests/test_db.py，验证默认路径可覆盖、连接可创建表、transaction 成功提交和异常回滚。
7. 运行 uv run python -m pytest rpg_data/tests -q。
完成后提交一个 commit，提交信息使用 chore: 新增 rpg_data 数据模块基础。
```

### Step 2：新增 migration 框架和初始 schema

目标：建立 schema 管理能力和 MVP 表。

Codex 提示词：

```text
继续实现 rpg_data migration 框架。
要求：
1. 新增 rpg_data/migrations/__init__.py、rpg_data/migrations/runner.py、rpg_data/migrations/0001_initial.sql。
2. runner.py 提供 run_migrations(conn)，维护 schema_migrations 表。
3. 0001_initial.sql 包含 workspaces、stories、sessions、characters、character_details、lorebook_entries、status_types、status_tables、status_rows、scene_states、scene_patches、turns、messages、turn_events、recent_sessions、favorites、journal_entries。
4. 所有表包含必要外键、created_at/updated_at，核心可编辑表包含 version。
5. migration 重复运行必须幂等。
6. 增加 rpg_data/tests/test_migrations.py，验证所有表创建成功、重复运行不重复应用。
7. 运行 uv run python -m pytest rpg_data/tests -q。
完成后提交 commit，提交信息：feat: 新增 rpg_data 初始数据库 schema。
```

### Step 3：实现基础 Repository 与种子数据 service

目标：可以创建 workspace、story、session，并读回。

Codex 提示词：

```text
实现 rpg_data 的基础 repository。
要求：
1. 新增 rpg_data/repositories/workspace_repo.py、story_repo.py、session_repo.py。
2. 新增 rpg_data/services/bootstrap.py，提供 ensure_default_workspace_and_story(conn)。
3. repository 使用 sqlite3.Connection，不持有全局状态。
4. 支持 create/list/get/update_timestamp 基础方法。
5. 默认 workspace id 使用 default，默认 story 可命名为 默认故事。
6. 增加 rpg_data/tests/test_repositories.py，验证创建 workspace/story/session、按 workspace/story 查询 session。
7. 运行 uv run python -m pytest rpg_data/tests -q。
完成后提交 commit，提交信息：feat: 添加故事与会话数据仓库。
```

### Step 4：实现角色、世界书、状态、场景 repository

目标：Play API 能读取管理数据。

Codex 提示词：

```text
继续补齐 rpg_data repository。
要求：
1. 新增 CharacterRepository、LorebookRepository、StatusRepository、SceneRepository。
2. CharacterRepository 支持 list_by_story/create/update/list_details/add_detail。
3. LorebookRepository 支持 list_by_story/create/update。
4. StatusRepository 支持创建 status_type/status_table/status_row，列出 status overview，支持 pinned 字段。
5. SceneRepository 支持 get_or_create_by_session、patch_scene，并写 scene_patches。
6. 所有 JSON 字段用 json.dumps/json.loads 封装，不把原始字符串泄漏给上层。
7. 增加对应 rpg_data/tests/test_world_repositories.py。
8. 运行 uv run python -m pytest rpg_data/tests -q。
完成后提交 commit，提交信息：feat: 添加世界配置与场景数据仓库。
```

### Step 5：Play API 增加 DataManagerBackend

目标：Play API 可以从 DB 返回故事/会话/房间聚合数据。

Codex 提示词：

```text
在 play_api 中新增 DataManagerBackend，并保持 AgentBackend 只负责发送和流式。
要求：
1. 新增 play_api/backends/data_manager.py，内部使用 rpg_data connect/run_migrations/repositories。
2. 新增或调整 play_api/backends/factory.py，提供 get_data_manager_backend() 和 get_agent_backend()，不要混淆职责。
3. DataManagerBackend 实现 list_stories、create_story、list_sessions、create_session、get_room_state、get_scene、patch_scene。
4. room-state 聚合 session、story、scene、characters、pinnedStatus、recentTurns、debugEvents，MVP 中没有数据时返回空数组。
5. 不要让 DataManagerBackend 调用 AgentClient，也不要让它直接发送消息。
6. 增加 play_api/tests/test_data_manager_backend.py，使用临时 RPG_WORLD_DB_PATH。
7. 运行 uv run python -m pytest play_api/tests rpg_data/tests -q。
完成后提交 commit，提交信息：feat: 为 Play API 增加数据管理 backend。
```

### Step 6：Play API 新增故事、会话、room-state 路由

目标：前端首页和 Play Room 可以接真实 DB API。

Codex 提示词：

```text
为 Play API 新增真实数据路由。
要求：
1. 新增 play_api/routers/stories.py，提供 GET/POST /stories，GET /stories/{story_id}，GET/POST /stories/{story_id}/sessions。
2. 新增 play_api/routers/room.py，提供 GET /sessions/{session_id}/room-state。
3. 调整 play_api/main.py include_router。
4. 保留现有 chat/stream 路由，但发送消息仍走 Agent backend。
5. Pydantic response model 使用 camelCase alias，兼容 Play WebUI。
6. 增加 play_api/tests/test_story_room_routes.py。
7. 运行 uv run python -m pytest play_api/tests rpg_data/tests -q。
完成后提交 commit，提交信息：feat: 增加 Play API 故事与房间状态接口。
```

### Step 7：Agent service 增加 DB-backed turn 写入最小路径

目标：发送一轮消息后 DB 里有 turn/message/event。

Codex 提示词：

```text
改造 Agent 侧最小 turn 持久化到 rpg_data 数据库。
要求：
1. 不再为新路径写 history.jsonl；SessionManager 从 rpg_data messages 表 load/append。
2. SessionManager 初始化时确保 workspace/story/session 存在；MVP 可用 default workspace/default story，session_id 对应 sessions.id 或 metadata 中的 public id。
3. begin_turn 创建 turns 记录，append 写 messages，end_turn 更新 session current_turn_id 和 turn status。
4. 流式事件可先在 turn done 时批量写 turn_events；至少写 done/error/tool_call/tool_result 的事件。
5. 保持现有 AgentClient send/stream API 不破坏。
6. 增加 rpg_core/tests/test_session_manager_db.py 或 agent_service/tests 覆盖 append/load/begin/end。
7. 运行 uv run python -m pytest rpg_data/tests rpg_core/tests/test_session_manager_db.py agent_service/tests -q。
完成后提交 commit，提交信息：feat: 将 Agent 会话历史写入数据库。
```

### Step 8：DB-backed SceneTracker

目标：场景 HUD 与 Agent scene prefix 使用同一 DB 数据。

Codex 提示词：

```text
将 SceneTracker 改为使用 rpg_data SceneRepository，而不是 CSV 当前场景文件。
要求：
1. SceneTracker.get_context() 从 scene_states 读取并渲染，保持原有 [scene] user prefix 语义。
2. scene_time/scene_attr/scene_del_attr 工具写 scene_states，并追加 scene_patches。
3. Play API 的 PATCH scene 与 Agent scene tools 写同一张表。
4. 删除或旁路新路径中的 当前场景.csv 依赖，不做 legacy 兼容。
5. 增加 rpg_core/tests/test_scene_tracker_db.py 与 play_api/tests 覆盖场景读写一致性。
6. 运行 uv run python -m pytest rpg_data/tests rpg_core/tests/test_scene_tracker_db.py play_api/tests -q。
完成后提交 commit，提交信息：feat: 将场景运行态迁移到数据库。
```

### Step 9：DB-backed Character/Lorebook/Status manager

目标：Agent 构建上下文和 Play API 管理界面读取同一 DB。

Codex 提示词：

```text
将角色、世界书、状态管理改为 DB-backed 新路径。
要求：
1. CharacterManager 从 rpg_data CharacterRepository 读取 enabled characters/details。
2. LorebookManager 从 LorebookRepository 读取 enabled entries。
3. StatusManager 从 StatusRepository 读取普通状态表。
4. 新路径不再读取 character/*.json、lorebook/*.json、status/*.csv。
5. ContextBuilder 调用方式尽量不变，减少 Agent 改动面。
6. Play API 增加角色/世界书/状态 CRUD route，使用 DataManagerBackend。
7. 增加 rpg_core/tests/test_context_builder_db_data.py、play_api/tests/test_world_config_routes.py。
8. 运行 uv run python -m pytest rpg_data/tests rpg_core/tests play_api/tests -q。
完成后提交 commit，提交信息：feat: 将世界配置数据迁移到数据库。
```

### Step 10：Play WebUI 接入真实故事首页

目标：首页展示 DB stories/recent sessions，不再使用 mock。

Codex 提示词：

```text
改造 play_webui 首页接入真实 Play API 数据。
要求：
1. 检查 play_webui 当前结构，找到首页/故事卡/最近会话组件。
2. 新增或更新 API client，调用 GET /play-api/v1/stories 和 GET /play-api/v1/recent-sessions（如果 recent-sessions 未实现，可先从 stories + sessions 聚合）。
3. 首页支持新建故事，调用 POST /play-api/v1/stories。
4. 移除首页 mock 数据依赖或改为 dev fallback，但默认使用真实 API。
5. 增加必要 loading/error/empty 状态。
6. 运行 cd play_webui && npm run build。
完成后提交 commit，提交信息：feat: Play WebUI 首页接入数据库故事数据。
```

### Step 11：Play Room 接入 room-state 与真实 stream

目标：进入房间后读 DB room-state，发送消息走 Agent stream，完成后刷新 room-state。

Codex 提示词：

```text
改造 Play Room 页面接入真实 room-state 与 Agent stream。
要求：
1. 页面加载时调用 GET /play-api/v1/sessions/{session_id}/room-state。
2. 左侧 Scene HUD、角色卡、右侧 pinned status、debug events 均来自 room-state。
3. 发送消息调用现有 stream API 或新的 /sessions/{session_id}/turn/stream，流式渲染 timeline。
4. 收到 done/error 后重新拉取 room-state 与 turns。
5. 保留 IC/OOC/GM/Slash 模式 UI，并把 mode 传给后端。
6. 移除默认 mock timeline，空状态时显示引导。
7. 运行 cd play_webui && npm run build。
完成后提交 commit，提交信息：feat: Play Room 接入真实房间状态与流式消息。
```

### Step 12：新增最小数据管理页面

目标：Play WebUI 提供 MVP 管理能力。

Codex 提示词：

```text
为 Play WebUI 新增最小数据管理页面。
要求：
1. 新增故事详情页或管理页，包含角色、世界书、状态三个 tab。
2. 角色 tab 支持 list/create/edit 基础字段。
3. 世界书 tab 支持 list/create/edit name/content/keywords/enabled。
4. 状态 tab 支持 list/create status table 和 row，支持 pin/unpin。
5. 所有请求调用 Play API 新增的角色/世界书/状态 CRUD。
6. 不跳转任何旧 Dashboard 入口。
7. 运行 cd play_webui && npm run build。
完成后提交 commit，提交信息：feat: Play WebUI 增加最小数据管理页面。
```

### Step 13：清理旧 Web 依赖

目标：Play WebUI MVP 不依赖 Dashboard。

Codex 提示词：

```text
清理 Play MVP 对 Dashboard WebUI 的依赖。
要求：
1. 搜索代码和文档中 Play 流程跳转旧 Web 入口的位置，改为 Play WebUI 内部页面或 TODO 标记。
2. 确认没有 `/dashboard_api`、`dashboard_api`、`dashboard_webui` 或 `run_dashboard_api` 依赖。
3. 更新 CLAUDE.md 和 todos/webui_product_requirements.md，使其符合 Play WebUI 统一承载数据管理的目标。
4. 运行 uv run python -m pytest play_api/tests rpg_data/tests -q，以及 cd play_webui && npm run build。
完成后提交 commit，提交信息：chore: 清理旧 Web 依赖。
```

### Step 14：端到端 MVP 验收测试

目标：前后端串通。

Codex 提示词：

```text
实现并运行最小 MVP 验收。
要求：
1. 增加后端集成测试：创建 story/session/character/scene，发送一轮 mock agent 消息，验证 turns/messages/turn_events/room-state。
2. Play API 测试使用 mock Agent backend，避免真实 LLM。
3. 如果项目已有前端测试框架，增加 Play WebUI smoke test；否则至少保证 npm run build 通过。
4. 验证 data/.runtime/rpg_world.sqlite3 在测试中使用临时路径，不污染仓库 data/。
5. 运行：uv run python -m pytest rpg_data/tests play_api/tests agent_service/tests rpg_core/tests -q。
6. 运行：cd play_webui && npm run build。
完成后提交 commit，提交信息：test: 增加 Play 数据化 MVP 验收覆盖。
```

## 8. 推荐实施顺序

最小可运行顺序：

1. `rpg_data` 基础包。
2. migration + schema。
3. story/session repository。
4. world config / scene / turn repository。
5. Play API DataManagerBackend。
6. Play API stories/room-state routes。
7. Play WebUI 首页接真实数据。
8. Agent SessionManager 写 DB。
9. Play Room stream + room-state 刷新。
10. DB-backed SceneTracker。
11. DB-backed Character/Lorebook/Status。
12. Play WebUI 最小数据管理页。
13. Dashboard deprecated 文档更新。
14. MVP 验收测试。

## 9. 风险与取舍

### 9.1 最大风险：多进程一致性

Agent 进程和 Play API 进程共享 DB，但不共享内存。解决方式：

- Agent runtime 相关写操作归 Agent 服务。
- Play API 配置写操作更新 version。
- Agent 每轮开始前检查版本并刷新。
- Play WebUI 在 turn done 后刷新 room-state。

### 9.2 最大改动：SessionManager 与 SceneTracker

这两个模块是历史文件化最核心的地方。MVP 可以先只支持 DB 新路径，不做 legacy fallback，降低复杂度。

### 9.3 SQLite 锁

MVP 使用短事务，stream 过程中尽量减少写锁。turn events 可先缓存，done 时批量写。后续如果需要实时调试事件持久化，再优化为队列写入。

### 9.4 测试数据不迁移

旧 `data/` 测试数据不迁移，避免为了临时样例拖慢目标架构。需要演示数据时，写 seed service 或前端创建流程。

## 10. 最终目标目录形态

```text
rpg_world/
  rpg_data/                 # 新共享数据模块
  rpg_core/                 # Agent/Core，使用 rpg_data repository
  agent_service/            # Agent runtime owner
  play_api/                 # Play WebUI 聚合 API：DataManagerBackend + AgentBackend
  play_webui/               # 唯一 Web 主体验
  rp_memory/                # 独立记忆检索/索引
  data/
    .runtime/
      rpg_world.sqlite3
      rpg_world.sqlite3-wal
      rpg_world.sqlite3-shm
```
