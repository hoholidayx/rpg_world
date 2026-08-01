# Story Pack 真实 LLM 验收

该目录提供 opt-in 的 `story-acceptance/1.0` 验收框架。它只把 Story Pack
导入 pytest 临时数据库与临时 Workspace，不构建或发布 Pack，也不修改设计工程
和正式运行数据。

## 运行

使用设计工程当前完整 Pack：

```bash
LIVE_LLM_TEST=1 uv run python -m pytest \
  rpg_core/tests/integration/test_live_story_acceptance.py \
  --story-project ../YQDesignProject \
  --story-profile tests/story_acceptance/profiles/yq-r000043.json \
  --story-suite full \
  --story-llm-timeout-seconds 120 \
  --story-report-dir logs/story-acceptance \
  -q -s
```

也可以用 `--story-pack <pack.json>` 指定 Pack。没有 sidecar 时必须提供
`--story-player-ref <character-stable-id>`；`smoke` 会运行通用导入、Context、
模式与 Plot 检查，`full` 还会让独立 LLM 从 Story 定义生成一份自然剧情流程，
并把有效流程保存为 `effective-profile.json`，供后续固化。

`--story-llm-timeout-seconds` 控制验收进程等待单次 LLM Service 请求的时间，
默认 60 秒；它不改变 Story step 的总超时，也不修改正式服务配置。

## Story 专属 sidecar

以 [YQ 示例](profiles/yq-r000043.json) 为模板。sidecar 必须绑定 Pack 的
`projectId + sourceRevision + sourceDigest`，并使用角色、Opening、状态表和 Plot
资源的 stable ref。每个 flow 使用独立 Session；同一 flow 的 steps 按顺序共享
状态。

step 可以声明：

- `mode` 与自然的 `input`；输入不得出现生产工具名、schema 或要求调用工具的测试话术。
- `requiredTools / forbiddenTools`：真实调用。
- `requiredExposedTools / forbiddenExposedTools`：Provider 实际收到的 schema。
- `context / status / plot / outcome / persistence`：确定性断言。
- `semanticRubric`：由当前 Codex 基于真实链路证据逐条裁定；验收运行本身不再调用
  额外的 verifier LLM。

确定性不变量失败为 `fail`，且不能被语义审阅覆盖。只要存在语义 rubric，首次
pytest 运行就会以 `Codex review required` 结束，并保持 `needs_review`；这不是新的
Provider 故障。网络、LLM Service 与请求超时为 `infrastructure_error`。

## Codex 两阶段审阅

真实链路结束后会生成：

- `semantic-review-queue.json`：绑定 run、Pack revision/digest、每个原始 rubric、
  正文、状态、Outcome、Plot 与 Provider call 范围。
- `codex-review-template.json`：绑定 queue 文件 SHA-256 的未完成模板，不能直接作为
  通过结论。

当前 Codex 阅读 `steps.jsonl`、`calls.jsonl` 和 queue 后，将模板补全为
`codex-review.json`。每条 pass/fail 必须引用结构化证据（artifact、flow/step 或
call index、field、原文 quote），finalizer 会确认 quote 确实存在于对应字段，并
确认每条 rubric 原文恰好出现一次：

```bash
uv run python -m tests.story_acceptance.codex_review finalize \
  --run-dir logs/story-acceptance/<pack-id>/<run-id>
```

finalizer 保留原始 `report.json / report.md`，另写
`final-report.json / final-report.md`。只有所有语义规则都是中/高置信 pass，且
确定性检查也全部通过时返回 0；高置信 fail 为 `fail`，低置信 pass、非高置信
fail、证据不足和被测 Provider 拒答均为 `needs_review`。

## 报告

每次运行写入 `<report-dir>/<pack-id>/<run-id>/`：

- `run.json`：Pack、revision/digest、环境、模型、token、缓存与耗时。
- `calls.jsonl`：脱敏后的完整 Provider messages、tools schema、可观察响应和异常；
  认证信息与 Provider 私有推理正文不会记录。
- `steps.jsonl`：输入、正文、状态/Plot 前后快照及持久化证据。
- `report.json / report.md`：五态结论、硬失败与人工复核项。
- `semantic-review-queue.json / codex-review-template.json`：Codex 审阅输入与绑定模板。
- `codex-review.json / final-report.json / final-report.md`：完成 Codex 审阅后才会有的
  审阅结论与最终报告。

发生失败时仍会继续其他 flow，并在最后统一令 pytest 失败；应先区分产品断言、
语义复核和基础设施错误，再决定是否调整 Story、运行时或 sidecar。
