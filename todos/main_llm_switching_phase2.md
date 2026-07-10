# 主 Agent LLM 动态切换二期 TODO

## 范围

二期只接入 Play WebUI 交互，不改变本期后端优先级和运行时语义：

- 选择优先级保持 `config default < story override < session override`。
- 只允许选择 `agent.main.provider_option_keys` 白名单中的 provider。
- 只切换主 Agent；StatusSubAgent、MemorySubAgent 等继续使用各自独立 biz 配置。
- 切换发生在生成中时不取消当前 turn，从下一 turn 起生效。

## 模型选择交互

- 接入 `GET /play-api/v1/llm/main-agent/options`，展示后台返回的安全模型目录，不读取或展示 API key、环境变量名、base URL、完整本地模型路径。
- Story 设置接入 `GET/PATCH /play-api/v1/workspaces/{workspace_id}/stories/{story_id}/main-llm`。
- Session 设置接入 `GET/PATCH /play-api/v1/sessions/{session_id}/main-llm`。
- 用 `providerKey: null` 显式清除当前层覆盖；UI 要展示当前有效 provider 及来源 `config | story | session`。
- Story 设置变化后刷新受影响 session 的有效选择；Session 设置只更新当前 session。
- 对 404、422 和 `invalidOverrides` 提供可恢复状态，并重新拉取 options/selection，不能把失效 key 继续作为可选项。

## 窗口缩小处理

采用简单前端门禁，不增加后端拒绝、自动压缩或历史改写：

- 进入 SessionRoom、切换有效 provider、正常 turn 完成、历史截断或压缩完成后，重新请求现有 `context-preview`。
- 只使用 `usageEstimate.usedTokens` 与 `usageEstimate.contextLimit` 判断；不新增独立 usage API，不持久化 usage。
- 当 `contextLimit` 为正数且 `usedTokens > contextLimit` 时，输入区进入“估算超窗”状态。
- 估算超窗时阻止提交普通正文，但允许去除前导空白后以 `/` 开头的命令，确保 `/compact` 等恢复命令始终可执行。
- 不清空用户已输入正文；切回更大窗口或 context preview 回落到窗口内后自动恢复普通发送。
- `contextLimit` 缺失时不启用门禁；context preview 请求失败时显示非阻塞错误，不把失败误判为超窗。
- 发送前再次按当前输入内容判定，避免按钮状态与快捷键提交路径不一致；流式与非流式入口复用同一规则。

## 二期测试

- options 只渲染后台白名单并保持后台顺序。
- Story/Session 覆盖、显式清空和三层优先级显示正确。
- 切换到更小窗口后立即刷新 context preview，当前生成不被取消，下一 turn 使用新选择。
- `usedTokens > contextLimit` 时正文按钮、Enter 提交均被阻止，`/compact` 和其它斜杠命令仍可提交。
- `usedTokens == contextLimit`、窗口未知、preview 失败、切回更大窗口等边界行为符合上述规则。
- 桌面和移动端输入区均无布局溢出，选择器和超窗状态不会遮挡命令输入。
