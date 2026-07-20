# `rpg_data` 数据访问架构规范

本文定义 `rpg_data` 与业务模块之间的长期稳定边界。它是后续新增或整改数据访问代码时的正式约束；`todos/` 下的重构计划只记录实施历史与待办顺序，不作为架构规范真源。

## 核心原则

> `rpg_data` 决定数据如何可靠、高效、原子地存取；业务模块决定为什么、何时以及写什么。

“数据层”不等于简单 CRUD。复杂关联查询、分页、批量写入、CAS、数据库级原子操作和高效 read model 应留在 `rpg_data`，避免业务层拼装 SQL 语义、制造 N+1 查询或破坏并发正确性。与此同时，数据层不得决定产品行为、状态机下一步或跨聚合业务流程。

## 依赖方向

```text
Service / Process Composition Root
                │
                ├── DataServiceGateway（数据库生命周期 + Service 注册表）
                │        │
                │        └── 取得具体 Data Service
                │
                ▼
Domain / Application Service（业务规则与用例编排）
                │
                ▼
Narrow Data Port / Data Service（类型化持久化边界）
                │
                ▼
Repository / Peewee Record（仅 rpg_data 内部）
                │
                ▼
              SQLite
```

必须保持以下单向关系：

- `rpg_data` 不导入 `rpg_core`、`rp_memory`、`rpg_media`、`rpg_tts`、接入层、事件发布器或 UI 模块。
- 业务代码可以依赖 `rpg_data.model.*` 的存储契约，以及自己定义的窄 Data Port。
- 业务代码不得导入 `rpg_data.repositories`、Peewee Record 或数据库查询对象。
- Repository 不作为跨模块 API；数据库实现变化必须被 Data Service 边界吸收。

## 各层职责

### Composition Root

进程入口、`RPGGameAgent` 等明确的组装边界负责：

- 获取 `DataServiceGateway`；
- 从注册表取得具体 Data Service；
- 创建 application/domain service 并逐项注入依赖；
- 绑定进程级生命周期、worker、HTTP adapter 和通知 adapter。

Composition Root 可以看见 Gateway，但不得把 Gateway 继续向业务对象传递。

### `DataServiceGateway`

Gateway 是合法的数据库生命周期管理器和 Service 注册表，负责：

- 解析数据库路径、连接、migration 和 bootstrap；
- 懒创建并缓存公开 Service；
- 确保当前线程连接已绑定；
- 统一关闭连接并清空已注册实例。

Gateway 不是业务 service locator。领域/application service 不得保存 Gateway，也不得在方法内部调用全局 getter。现存非组装层 lookup 或整 Gateway 注入只能保留在架构测试的显式 allowlist 中；allowlist 是待收口边界，不是新增先例。

### Domain / Application Service

业务模块负责：

- 默认选择、资格判断和产品策略；
- 调度、抽样、优先级、冷却与重试策略；
- 状态机状态迁移和生命周期推进；
- Session 派生、重置、删除等跨聚合用例；
- Prompt、模板渲染、玩家文案和渠道无关的业务结果；
- 决定事务中执行哪些数据动作及其顺序。

业务对象应在自身模块定义最窄可用的 `Protocol`。Protocol 只声明当前用例所需能力，不暴露整个数据目录。

### Data Service

Data Service 是 `rpg_data` 的公开类型化持久化边界，可以负责：

- 单表与复杂关联查询；
- 分页、排序、过滤、聚合和高效 read model；
- 类型化 CRUD、批量插入、批量复制与批量删除；
- 乐观锁、CAS、条件 claim/update/delete；
- 数据库级原子操作和无业务语义的 transaction/unit-of-work；
- 外键、唯一性、归属、非空、范围和可序列化校验；
- 存储 DTO 与数据库行之间的转换；
- 将数据库异常转换为通用数据错误。

Data Service 只能执行调用方已经明确给出的动作、过滤条件和目标值。方法名与参数不得偷偷固化“默认 Opening”“只复制 triggered”“失败后重试”等业务选择。

### Repository

Repository 是 `rpg_data` 内部的 Peewee 实现细节，负责查询表达式、Record 操作和 SQL 优化。它可以实现复杂查询与数据库原子语义，但不能承载产品决策。

如果 Data Service 只是无差别转发 Repository，且没有提供公开类型、事务、错误转换或聚合边界价值，应合并无价值层级；不要为了形式统一保留重复 facade。简单 Character/Lorebook CRUD 可以继续使用清晰的 `*ReadService` / `*ManagementService`，不机械复制 application service、adapter 和 DTO 转换层。

## Service 命名与聚合粒度

- 公开类型化持久化入口统一使用 Service 语义。
- Session、Plot、Dream/Memory 等大业务聚合入口使用 `*DataService`。
- 一个聚合 Data Service 可以组合本业务所需的多个 Repository 或既有数据组件，但不得向调用方暴露这些内部协作者。
- 不以缩短文件、消灭所有现有 Service 或统一后缀为重构目标。
- 只有发现真实业务决策越界、依赖范围过宽、事务语义泄漏或明显查询低效时，才新增或调整层次。

当前可参考的聚合入口包括：

- `SessionDataService`：Session/profile、角色与 Opening read model、派生账本、调用方指定的复制/删除和 Session 级原子边界；
- `PlotSchedulingDataService`：Plot 定义、Session 覆盖、决策账本和分页 read model；
- `DreamMemoryDataService`：Dream/Persistent Memory 账本、CAS、批量与 `IMMEDIATE` 事务；
- `StoryMemoryDataService`：Story Memory/Evidence 的查询、分页与类型化写入。

## Gateway 与窄依赖的标准写法

业务模块定义自己的 Port：

```python
from typing import ContextManager, Protocol

from rpg_data.model.session import SessionDerivationJob


class SessionDerivationDataPort(Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def get_derivation_job(
        self,
        job_id: str,
    ) -> SessionDerivationJob | None: ...
```

Composition Root 负责绑定具体实现：

```python
gateway = get_data_service_gateway()
derivation_service = SessionDerivationService(gateway.sessions)
```

禁止在 `SessionDerivationService` 内保存 Gateway，或在业务方法中临时调用 `get_data_service_gateway()`。

## 事务与并发语义

事务所有权分为两部分：

1. 业务层决定一个用例需要执行哪些动作、顺序和失败语义。
2. 数据层提供可靠的事务、CAS、条件更新、批量写入或单条原子 SQL 实现。

具体约束：

- 跨多次操作需要共同提交时，Data Service 暴露无业务语义的 context manager 或类型化 bulk primitive。
- 能由数据库一次完成的竞争检查与写入，不拆成业务层的“先查再写”。
- 为避免 N+1 而设计的 join/read model 属于数据层，不要求业务层逐行组装。
- 数据库事务不得覆盖远端 LLM、HTTP、文件生成等长耗时 I/O。
- application service 不直接访问 `gateway.database.atomic()`；需要的事务模式应成为 Data Port 的明确能力。

## 类型所有权

- 数据库行 DTO、写入 payload、分页结果、稳定存储值和 read model 归 `rpg_data.model.*`。
- 业务命令、策略输入/结果、状态机枚举和领域错误归对应业务模块。
- 跨层返回值优先使用 dataclass、枚举或其它明确类型，不使用约定字符串 key 的裸 `dict`。
- Session 与 Memory 的 canonical 存储契约位于 `rpg_data.model.session` 和 `rpg_data.model.memory`。
- `rpg_data.models` 暂时兼容重导出已迁移类型；新代码优先从 canonical 模块导入，不再向巨型兼容模块增加新的跨域类型。
- Status、Media、TTS 等类型只有在对应业务域发生真实整改时再迁移，不为目录整齐进行批量搬运。

稳定的数据库枚举值可以由数据层定义，但“下一状态是什么、何时允许迁移”必须由领域状态机决定。

## 错误边界

数据层错误只描述数据事实，例如：

- not found；
- integrity/ownership violation；
- unique conflict；
- CAS/conditional update failed；
- serialization 或数据格式无效。

领域错误码、HTTP 状态、玩家提示和重试策略由上层映射。Data Service 不返回 HTTP schema，不拼接玩家文案，也不发布 WebUI/后台事件。

## 静态架构守卫

`rpg_data/tests/test_architecture_boundaries.py` 固定检查：

- `rpg_data` 不反向导入业务或接入模块；
- Repository/Record 不泄漏到 `rpg_data` 外的生产代码；
- 已整改 application service 不依赖 Gateway；
- Gateway getter 使用面不超出显式 allowlist；
- 整 Gateway 类型引用与构造注入不超出独立的显式 allowlist；
- 新聚合持久化入口采用 `*DataService` 命名；
- `rpg_data.models` 的兼容重导出与 canonical 类型保持同一身份。

新增架构例外时，不应直接扩展 allowlist。必须先说明无法使用 Composition Root 注入或窄 Port 的原因，并评估它是否揭示了新的组装边界。

## Review 清单

涉及数据访问的变更至少确认以下问题：

1. 这段代码是在决定“如何存取”，还是在决定“为什么、何时、写什么”？
2. 业务 service 是否只依赖实际需要的窄 Protocol？
3. Gateway lookup 是否只发生在明确的 Composition Root？
4. 是否把 Repository、Record、查询对象或原始 JSON 泄漏给业务代码？
5. 复杂查询、分页、批量、CAS 或原子 SQL 是否仍留在数据层？
6. 是否为了形式统一新增了没有边界价值的转发层？
7. 类型属于存储契约还是领域策略，是否放在正确 owner？
8. 数据错误是否夹带领域错误码、HTTP 状态或玩家文案？
9. 事务是否只包围数据库短操作，并保持原有并发语义？
10. 是否补充或更新了架构守卫与对应 owner 的测试？

后续整改以迁出真实业务决策为标准，不以减少 `rpg_data` 行数、消灭 Service 或追求目录形式一致为目标。
