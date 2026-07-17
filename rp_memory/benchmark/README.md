# RP Memory recall benchmark

固定套件同时运行 LoCoMo full 与项目 RP Gold Seed。默认会探测 LLM Service，
并对当前启用且最小推理探测成功的 embedding、LLM query planner、reranker
逐 Provider 执行；未配置、禁用、服务不可达或探测失败时会明确记录跳过原因。

```bash
# 默认完整套件；可能调用远端 Provider，产生费用且结果可能非确定
uv run python -m rp_memory.benchmark suite

# 完整套件成功后，同时追加 Git 跟踪的精简历史
uv run python -m rp_memory.benchmark suite --record

# 不接触 LLM Service，只跑固定本地路径；缓存缺失时仍会下载 LoCoMo
uv run python -m rp_memory.benchmark suite --offline-only

# 仅准备数据
uv run python -m rp_memory.benchmark prepare
```

`--locomo-tier smoke` 仅供开发调试，`--record` 强制要求 `full`。目前指标只记录，
不作为阻断门禁。

## 固定路径矩阵

1. `offline.keyword_rule`：冻结的 jieba + keyword + Rule Planner 基线。
2. `offline.local_fallback`：keyword + 当前配置的 raw-md fallback。
3. `configured.embedding.<provider>`：vector + keyword + Rule Planner。
4. `configured.planner.<provider>`：keyword + LLM Planner（失败回退 Rule）。
5. `configured.rerank.<provider>`：keyword + Rule Planner + pointwise rerank。
6. `configured.effective`：默认 Provider 与当前开关形成的实际组合；能力异常时运行
   本地 fallback 并标记 `degraded_runtime_fallback`。

所有路径关闭 recency，因为临时索引时间不是数据集事实。报告记录 Planner →
keyword/vector/raw-md → fusion → rerank → Top-5 的完整链路、候选池、Tokenizer、
权重、Provider、模型、dimension、Planner source、扩展查询覆盖题数/变体数及其
用途。环境区同时记录 active profile、LLM Service 地址（凭据和 query 会被移除）、
Python/SQLite/jieba、Git revision/dirty 状态和所有数据/报告绝对路径。
hybrid/final score 只是单次查询内的相对排序信号，不是概率，也不能跨查询比较。

## 数据与结果

LoCoMo 固定到 commit
`3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`，原始文件 SHA-256 为
`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`，
许可为 CC BY-NC 4.0。下载器使用有限重试、size + SHA-256 校验和临时文件原子
替换；有效缓存不会联网。原始与转换数据、临时索引、完整结果均位于忽略的
`data/benchmarks/`，不会提交 Git。

- 每次运行完整报告：`data/benchmarks/results/<UTC>-<run-id>.md`
- `--record` 精简历史：`docs/benchmarks/rp-memory-recall-history.md`

完整报告保存所有失败、部分覆盖、无答案误报和 forbidden 污染案例的 Planner
trace、Top-5 evidence 与原始分数组件。LoCoMo 中有 4 个有答案但缺少 evidence
标注的问题，只计入 `unscored_cases`，不参与指标。RP Gold Seed 当前仍是
`seed_pending_two_person_review`，在双人独立审核前不能升级为 release gate。

状态值固定为：`executed`、`skipped_disabled`、`skipped_unconfigured`、
`skipped_service_unreachable`、`skipped_probe_failed`、
`degraded_runtime_fallback`、`failed`。
