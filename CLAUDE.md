# rpg_world

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。

## 启动

```bash
# API 开发服务器（端口 8000，自动重载）
cd rpg_world/api && bash run_dev.sh

# WebUI 开发服务器（端口 5173，代理 /api → 后端）
cd rpg_world/webui && npx vite

# 独立 Agent CLI（无 API，直接 LLM 对话）
uv run python -m rpg_world.rpg_core.agent.cli [--model gpt-4o] [--session-id mygame]

# 验证导入
uv run python3 -c "from rpg_world.rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── rpg_core/                    # 核心逻辑（无框架依赖）
│   ├── agent/                   # LLM Agent 引擎
│   │   ├── agent.py             #   RPGGameAgent — 主入口
│   │   ├── cli.py               #   REPL 命令行
│   │   ├── loop.py              #   chat loop（LLM 往返 + tool calling）
│   │   ├── openai_provider.py   #   LLM 调用封装
│   │   ├── prompt.py            #   系统提示词
│   │   ├── memory_sub_agent.py  #   记忆子 Agent（总结/召回）
│   │   └── tools/               #   工具系统
│   │       ├── base.py          #     BaseTool 抽象
│   │       ├── registry.py      #     工具注册中心
│   │       └── file_tools.py    #     文件读写/搜索工具
│   ├── scene/                   # 场景状态（当前时间/地点/属性）
│   │   ├── tracker.py           #   SceneTracker — 纯内存状态 + CSV 持久化
│   │   └── tools.py             #   set_time / set_attr / delete_attr
│   ├── context/                 # 5 层 RPG 上下文构建
│   │   ├── builder.py           #   RPGContextBuilder
│   │   ├── rpg_context.py       #   RPGContext 容器
│   │   ├── factory.py           #   组装全栈
│   │   └── config.py            #   上下文配置
│   ├── character/               # 角色卡（JSON）
│   ├── lorebook/                # 世界书（JSON）
│   ├── status/                  # 状态表（CSV）
│   ├── milestone/               # 里程碑（JSON）
│   ├── memory/                  # 记忆存储
│   │   ├── persist_memory.py    #   常驻记忆（persistent_memory.md）
│   │   ├── story_memory.py      #   剧情记忆（story_memory/）
│   │   └── recalled_memory.py   #   召回记忆（运行时注入）
│   ├── summary/                 # 对话摘要
│   ├── jinja/                   # Jinja2 模板
│   ├── models/                  # Pydantic 数据模型
│   ├── settings.py              # Settings 单例（读取 settings.json）
│   └── utils/
│       ├── manager_base.py      #   BaseManager（注册 FileWatcher）
│       ├── watcher.py           #   FileWatcher（watchdog 文件监控）
│       └── path_utils.py        #   路径解析
├── api/                         # FastAPI 应用
│   ├── main.py                  #   入口 + CORS + 路由注册
│   ├── deps.py                  #   管理器单例 + watcher 启动
│   └── routers/                 #   CRUD 路由
├── webui/                       # Vue 3 SPA
│   └── src/
│       ├── api/                 #   Axios 客户端
│       ├── views/               #   管理页面
│       └── composables/         #   useCRUD 等
└── data/                        # 数据文件（git 跟踪）
    └── 非公开行程/               #   工作区
```

## 关键设计

### 5 层 RPG 上下文（`context/builder.py` → `rpg_context.py`）

LLM 调用时的消息构建顺序，按变更频率排列以优化 prefix cache：

| 层 | role | 内容 | 变更频率 |
|---|---|---|---|
| [0] Fixed | system | 系统提示 + 世界书 + 角色卡 | ★ 几乎不变 |
| [1] Persistent Memory | system | 常驻记忆（persistent_memory.md） | ★ 离线更新 |
| [2] Summary | system | 历史摘要（条件触发） | ★☆ 少量 |
| [3..N] Hot History | mixed | 最近 N 轮对话 | ★★☆ 每轮追加 |
| [N+1] Milestones | system | 活跃里程碑 | ★★☆ 剧情驱动 |
| [N+2] Story Memory | system | 剧情细节 | ★★☆ 累积 |
| [N+3] Recalled Memory | system | 动态召回 | ★★★ 动态注入 |
| [N+4] Status Tables | system | 游戏状态 CSV 表 | ★★★★ 高频变化 |
| [N+5] User Message | user | `[scene]` + 用户输入 + 前后缀 | 总是新的 |

### Loader + Manager + BaseManager 模式

每个数据域（character/lorebook/status/milestone）遵循：

1. **Loader** — 纯文件 I/O，无缓存无业务逻辑
2. **Manager** — 继承 `BaseManager`，持有 `self.data` 缓存，实现 `reload()` / `_data_dir()`
3. **BaseManager** — 构造时向 `FileWatcher` 注册数据目录，文件变更自动调用 `reload()`
4. **FileWatcher** — watchdog Observer，500ms 防抖，启动由 `deps.py` 控制

### 场景状态模块（`scene/`）

`SceneTracker` 管理"当前场景"的时间、地点、属性，数据持久化到 `status/全局状态/当前场景.csv`。

- 纯内存状态 + CSV 持久化（复用 StatusManager）
- `[scene]` 渲染后嵌入用户消息（`agent.send()` 写入 `_history` 和 JSONL）
- 使 MemorySubAgent 在总结归纳时可见（不依赖 system 角色消息）
- Builder 组装通用状态表时排除 scene table 避免重复

### 路径解析（`utils/path_utils.py` / `settings.py`）

- 绝对路径 → 原样返回
- 相对路径 → 以 `rpg_world/` 为根解析
  - 有 `active_workspace`（如 `data/非公开行程`）→ `rpg_world/{workspace}/{path}`
  - 无 workspace → `rpg_world/data/{path}`

### Agent 数据流

```
agent.send(user_input)
  → SceneTracker.get_context() → [scene] 嵌入 user message
  → _build_transformed_context() → builder.build() → RPGContext.to_messages()
  → run_chat_loop(provider, tool_registry, messages)
  → LLM 可能调工具（scene.set_time / set_attr / file tools）
  → 回复写入 _history + JSONL
```

### REST API（`api/routers/`）

```
GET    /api/v1/{resource}           — 列表
POST   /api/v1/{resource}           — 创建
GET    /api/v1/{resource}/{name}     — 详情
PUT    /api/v1/{resource}/{name}     — 更新
DELETE /api/v1/{resource}/{name}     — 删除
```

错误码：400（校验）、404（不存在）、409（冲突）。

### 前端注意事项

- `useCRUD` composable 适用于 character/lorebook/milestone 的 CRUD 页面
- `StatusManagement` 是自定义 CSV 表格编辑器（不共用 useCRUD）
- 中文路径须在前端 axios 层用 `encodeURIComponent()` 编码，后端 FastAPI 自动解码
- 暗色模式：`data-theme` 属性控制，Pinia store 持久化

### 数据格式

- **Character/Lorebook/Milestone**: JSON 文件（name, enable, content, tags, 自定义字段）
- **Status**: CSV 文件，UTF-8 BOM (`utf-8-sig`) 编码，Excel 兼容
- **场景状态**: CSV（两列 key-value 格式，属性名/值）
- **持久化路径**: worktree 构造时从 `settings.json` 读取路径配置
