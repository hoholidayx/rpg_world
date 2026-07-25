# Story DesignProject 交接

本目录是一个完整、可移动、单 Story 的设计工作区。它不依赖 RPG World
源码或任何 `rpg_*` Python 模块；唯一外部边界是安装到 `PATH` 的
`rpg-world-mcp` 命令。

## 已交付

- workspace `AGENTS.md`：强制 Story 设计任务持续读取并遵守本地 Skill。
- `.agents/skills/rpg-story-authoring/`：Codex 可自动发现的 workspace 级
  Skill，负责脑暴、决策、持久化、checkpoint、Story Pack 与运行时同步。
- `design/current.json`、不可变 `design/revisions/` 和命名
  `design/checkpoints/`。
- 中立 JSON Schema 与 MCP 工具契约。
- `schemas/story-authoring-rules-v1.json` 字段语义单一真源；Schema
  description/example、Skill 分域 references、Viewer 字段指南与结构化诊断
  均由它生成。
- 完整包和按 section 小包的产物目录。
- RPG World 同步结果与报告目录。
- `.codex/config.toml`：只引用命令名，不引用原仓库绝对路径。

## 首次使用

在 RPG World 源码仓库根目录，把命令安装到用户环境：

```text
uv tool install --editable .
```

随后可将本目录整体移动到任意位置，作为新的 Codex workspace 打开。
启动后先运行：

```text
story_design_doctor
story_design_get_resume_context
story_design_validate profile=draft
```

已提交的 `.codex/config.toml` 默认使用 `--mode design`，因此日常脑暴不会
初始化 RPG World 数据库。准备比较、预览或导入时，把其中的 mode 改为
`all` 并重启 MCP；完成运行时操作后可以再改回 `design`。不要同时注册两个
包含同名 design 工具的 server。

若开发安装指向的 RPG World 源码也被移动，需要重新安装命令；DesignProject
内的数据不需要修改。

## MCP 交付形态

统一入口：

```text
rpg-world-mcp --mode design|runtime|all
```

- `design`：只操作本目录文件，不加载 RPG runtime。
- `runtime`：只操作 RPG World 数据库。
- `all`：同时提供设计工具、运行时工具和双向比较/同步工具。

默认使用 stdio。仅本机 Inspector 可使用
`--transport streamable-http --host 127.0.0.1`；非 loopback 会拒绝启动。
ChatGPT App 通过 OpenAI Secure MCP Tunnel 连接同一个本地命令，并把本目录
设置为 working directory/project root。每个需要工具的新 ChatGPT 会话仍需
选择该 developer App；App 不会自动读取完整聊天历史。

## 本地可视化浏览器

本目录自带一个无外部依赖、只读的 Story Design Viewer。它会格式化展示当前
设计、不可变 revision、版本差异、两份 Schema 和已经生成的 Story Pack，并
在 `design-project.json.currentRevision` 原子切换后自动刷新。

在本目录运行：

```text
python3 viewer/serve.py
```

随后访问 `http://127.0.0.1:8787/`。可使用 `--open` 自动打开浏览器，或通过
`--port` 更换本机端口。字段指南页会展示完整字段职责、示例、运行时影响，
并可切换 draft/package profile 查看所选 revision 的结构化诊断。Viewer
只监听 loopback，不提供任何写接口；它不是
`story_design_patch`、Story Pack preview/apply 或 MCP 的替代入口。查看历史
revision 时若产生新版本，页面会保留当前阅读位置并提示切换到最新版。

## 持久化与恢复

每次确认的设计决策应立即调用 `story_design_patch`，并携带当前 revision
作为 expected-head CAS。会话压缩、新会话或断线后用
`story_design_get_resume_context` 精确恢复，不依赖聊天记录。

revision 和 checkpoint 都不可覆盖。恢复旧版本会创建一个新 revision。
项目只保存结构化设计、决策摘要和来源，不保存完整对话。

历史 revision、本地 source 文件或会话导出都不等于已发布内容，也不会因被
放入目录而获得导入授权。必须重新选择、编写并由用户确认到当前 revision，
Story Pack 也只能从当前 revision 构建。

revision 提交使用临时事务日志跨文件落盘。若进程在 revision、current 和
manifest 之间退出，下次启动 MCP 会在锁内完成同一笔提交；独立 doctor
发现残留日志时只报告，不擅自改写。

## 导入与确认

Story Pack v2 每包只包含一个 Story，支持按 section 拆包，采用 merge-only
且不会因遗漏而删除运行时资源。角色、世界书和状态表都直接归 Story 所有；
视觉规格只归档，不创建媒体任务或图片。

角色一级叙事字段只有 `name + description`；description 只写身份、经历和客观
事实，性格、说话方式、行为倾向与心理必须放入二级详情。演绎详情使用内置
`kind:personality | kind:speech | kind:behavior | kind:psychology`，并自动携带
`scope:npc_portrayal`。`message_mode` 是配置为空、提示词由运行时代码内置的
RP Module，模式固定为 `neutral | ic | ooc | gm`，不再设计 Workspace mode。
Design/Pack/Project/MCP 契约均硬切 2.0，v1 输入直接拒绝且无转换器。

`authoringRulesVersion=1.1` 与 Story Pack `contractVersion=2.0` 独立演进。
日常迭代调用 `story_design_validate(profile="draft")`；准备 checkpoint 或
构建包时调用 `profile="package"`。`diagnostics` 固定包含
`ruleId/severity/path/message/suggestion/runtimeEffect`。error 是确定性门禁；
warning 表示字段职责或创作质量需要复核。`story_design_patch` 只返回受本次
修改路径影响的 advisory diagnostics，构建 Story Pack 会自动再次执行
package profile。

## 字段规则资产升级

安装的新 MCP 若检测到本项目的规则、Schema、Skill 或生成 references 过期，
必须使用两步刷新：

1. `story_design_preview_authoring_rules_refresh`
2. 用户确认列出的文件变化后，调用
   `story_design_apply_authoring_rules_refresh(operation_id)`
3. 再运行 `story_design_doctor`

刷新只允许改写受管规则资产和 `design-project.json` 中对应版本/摘要。它不得
修改 `design/current.json`、任一 revision/checkpoint、既有 Story Pack 或
`integrations/`。v1 项目在 preview/apply 前即拒绝，保证零写入；不提供
v1→v2 转换器。

同一 revision、section 与 runtime target 重复构建会复用完全相同的不可变
Story Pack；不同 target 会生成不同 pack ID。Story 的时间背景、logline、
主题和边界会通过保留 metadata 往返，不会因为 runtime 缺少独立列而丢失。
叙事风格的挂载版本和基础风格状态也参与漂移判断。

运行时写入必须分两步：

1. preview 返回持久化 operation ID 和逐项变更。
2. 用户明确确认后，调用 apply 并只传 operation ID。

apply 不提供 `confirmed=true` 之类的形式参数。数据库事务先提交，再更新本
目录的 integration/report 文件。若文件阶段失败，状态为
`applied_with_local_sync_pending`；修复 project root 后，用同一 operation
ID 重试 apply，只补文件，不重复数据库业务写入。

operation ID 与 preview lane 绑定，`story_pack`、`changes` 和
`runtime_sync` 必须使用各自对应的 apply 工具。状态表小包若引用未包含的
角色，preview 只接受目标 Story 中已经存在且属于同一 DesignProject 的稳定
角色绑定。

## 移动后的检查

```text
python3 .agents/skills/rpg-story-authoring/scripts/portable_doctor.py \
  --project-root .
```

检查通过后再连接 MCP。若 Secure MCP Tunnel 仍指向旧目录，只更新 Tunnel
working directory；不要改写 revision 或 Story Pack。
