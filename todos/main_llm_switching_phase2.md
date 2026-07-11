# 主 Agent LLM 动态切换二期

## 已锁定范围

- 选择优先级保持 `config default < story override < session override`，只展示 `agent.main.provider_option_keys` 白名单。
- Story 详情编辑页立即保存 story 默认；SessionRoom 在 context 圆环左侧立即保存 session 覆盖，`providerKey: null` 清除当前层。
- 生成中切换不取消当前 turn，从下一 turn 生效；切换模型不触发自动压缩。
- Story/Session 选择失败或存在 `invalidOverrides` 时回退到有效来源并重新拉取安全目录，不展示失效 key。

## Context 展示与门禁

- context 圆环始终使用 `context-preview.usageEstimate`，不含当前待发送 input；上一轮 provider usage 只显示在回复气泡和圆环详情，不覆盖圆环、不参与门禁、不持久化。
- WebUI 阈值配置为 `session.contextUsage.inputBlockThresholdRatio`，Core 兜底配置为 `agent.context_window_reject_threshold_ratio`，合法范围 `(0, 1]`，默认均为 `0.9`；WebUI 非法值回退 `0.9`，Core 非法值启动失败。
- 达到或超过阈值时禁止普通 send/retry/edit，但允许前导空白后以 `/` 开头的所有命令；提交前检查必须发生在历史截断之前。
- Core 在命令分发和角色校验之后、transaction/StatusSubAgent/LLM 之前检查相同的当前主 Context；拒绝错误码为 `MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED`。
- preview 或窗口未知时前端不误判阻止；Core 窗口未知时记录 warning 并放行。

## 手动压缩原则

- 达到阈值时保留正文草稿，提示 `/compact [压缩轮数] [保留轮数]` 或切换更大窗口模型。
- 不自动填入或执行 `/compact`，不因达到阈值或切换模型自动归纳。
- 不增加右上角自动压缩设置或 localStorage 偏好；现有自动压缩配置继续默认关闭。

## 验收

- 白名单顺序、三层继承、显式清除、失效覆盖和生成中切换符合上述语义。
- 圆环、展开详情、回复气泡分别使用正确 usage 来源。
- `ratio >= threshold` 时 WebUI/Core 均拒绝正文且命令可恢复；拒绝不写历史、不调用主/子 Agent、不提交状态。
- 模型切换、turn/命令完成、压缩、删除、清空、回滚和截断后 context-preview 会刷新并重新计算门禁。
