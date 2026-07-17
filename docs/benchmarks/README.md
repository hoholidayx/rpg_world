# RP Memory 召回基准记录

本目录只跟踪显式执行 `suite --record` 后产生的精简总结。每次运行的完整逐题诊断
保存在已被 Git 忽略的 `data/benchmarks/results/`。指标目前仅用于观察和比较，不作为
CI 或发布门禁。

混合融合与重排分数只表示单次查询内部的相对顺序，不是概率，也不能跨查询比较。

<!-- benchmark-runs:start -->
| 开始时间（UTC） | Run ID | Git revision | 工作区 | 数据集核心指标 | 能力状态 | 报告 |
|---|---|---|---|---|---|---|
| `2026-07-17T04:54:25.289499Z` | `20260717T045425Z-e5690bb6` | `2611e827401f` | dirty | locomo: H1 0.335015, R5 0.572149; rp-gold: H1 0.916667, R5 1.000000 | `embedding=skipped_service_unreachable, planner=skipped_disabled, reranker=skipped_disabled` | [查看](runs/rp-memory-recall-20260717T045425Z-e5690bb6.md) |
| `2026-07-17T04:45:04.288731Z` | `20260717T044504Z-08cc0e0c` | `c21e888cc0ae` | dirty | locomo: H1 0.335015, R5 0.571645; rp-gold: H1 0.916667, R5 1.000000 | `embedding=skipped_service_unreachable, planner=skipped_disabled, reranker=skipped_disabled` | [查看](runs/rp-memory-recall-20260717T044504Z-08cc0e0c.md) |
<!-- benchmark-runs:end -->
