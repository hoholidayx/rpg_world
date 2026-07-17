# RP Memory 召回基准记录

本目录只跟踪显式执行 `suite --record` 后产生的精简总结。每次运行的完整逐题诊断
保存在已被 Git 忽略的 `data/benchmarks/results/`。指标目前仅用于观察和比较，不作为
CI 或发布门禁。

混合融合与重排分数只表示单次查询内部的相对顺序，不是概率，也不能跨查询比较。

结果判读依据本次实际执行的路径生成：embedding 路径未成功执行时说明离线关键词基线的
能力边界；存在成功执行的向量路径时，优先列出并关注该路径指标。横向回归应比较相同路径，
只有对应能力状态为 `executed` 时，才能评价该模型能力的效果。

<!-- benchmark-runs:start -->
| 开始时间（UTC） | Run ID | Git revision | 工作区 | 数据集核心指标 | 能力状态 | 报告 |
|---|---|---|---|---|---|---|
| `2026-07-17T06:04:13.067575Z` | `20260717T060413Z-e12c7ecd` | `abccb93f0b71` | dirty | locomo: H1 0.335015, R5 0.572149; rp-gold: H1 0.709091, R5 0.981818 | `planner=skipped_disabled, reranker=skipped_disabled, embedding=skipped_service_unreachable` | [查看](runs/rp-memory-recall-20260717T060413Z-e12c7ecd.md) |
| `2026-07-17T06:01:56.037039Z` | `20260717T060156Z-2e8f8f0b` | `abccb93f0b71` | dirty | locomo: H1 0.335015, R5 0.572149; rp-gold: H1 0.709091, R5 0.981818 | `embedding=skipped_disabled, planner=skipped_disabled, reranker=skipped_disabled` | [查看](runs/rp-memory-recall-20260717T060156Z-2e8f8f0b.md) |
| `2026-07-17T04:54:25.289499Z` | `20260717T045425Z-e5690bb6` | `2611e827401f` | dirty | locomo: H1 0.335015, R5 0.572149; rp-gold: H1 0.916667, R5 1.000000 | `embedding=skipped_service_unreachable, planner=skipped_disabled, reranker=skipped_disabled` | [查看](runs/rp-memory-recall-20260717T045425Z-e5690bb6.md) |
| `2026-07-17T04:45:04.288731Z` | `20260717T044504Z-08cc0e0c` | `c21e888cc0ae` | dirty | locomo: H1 0.335015, R5 0.571645; rp-gold: H1 0.916667, R5 1.000000 | `embedding=skipped_service_unreachable, planner=skipped_disabled, reranker=skipped_disabled` | [查看](runs/rp-memory-recall-20260717T044504Z-08cc0e0c.md) |
<!-- benchmark-runs:end -->
