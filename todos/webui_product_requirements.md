# RPG World Play WebUI 产品需求

## 当前结论

Play WebUI 是唯一 Web 主体验，承担沉浸式 RP、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口。Dashboard API 和 Dashboard WebUI 已删除，后续不要恢复或新增依赖。

Telegram 保持轻量入口、推送通知、快速回复与兜底交互；CLI 保持开发调试入口。所有 Web 能力通过 Play WebUI + Play API 演进。

## P0：可稳定游玩

- 启动 `run_agent.py` 与 `run_play_api.py` 后，Play WebUI 可以选择工作区和会话。
- 玩家可以进入会话房间，发送输入并看到 SSE 流式剧情。
- 剧情流、场景 HUD、输入区在桌面和移动端都可用。
- stream error 不清空已输出内容，并允许复制本轮文本。
- Play WebUI 不直接访问 `data/`，只调用 Play API。

## P1：最小数据管理

- Play WebUI 内提供角色、世界书、状态、场景的最小维护入口。
- 数据管理请求统一走 Play API 和 `rpg_data`，不要复制核心业务规则到前端。
- 工作区、会话、故事数据使用同一套语义，避免渠道间故事分裂。
- 不跳转旧 Dashboard，不保留 `/dashboard_api` 兼容入口。

## P2：剧情日志、回滚与分支

- 新增 typed stream event schema，区分 narration、dialogue、tool、scene patch、system status 等事件。
- 支持 turn 列表、重试指定 turn、删除后续、fork session。
- 明确 snapshot 边界：history、scene、status/module state 必须一致。
- 调试面板默认隐藏，只在开发或显式开启时展示。

## P3：沉浸式增强

- 增加快捷行动、角色状态提示、关系/物品/任务等轻量 RP Module UI。
- 可选增加视觉小说式背景、角色表情和过场效果，但业务状态仍由 React + 后端管理。
- 不在 Telegram 中实现复杂地图、战斗面板、状态表编辑器等重 UI。

## 验收命令

```bash
uv run python -m pytest play_api/tests rpg_data/tests -q
cd play_webui && npm run build
```
