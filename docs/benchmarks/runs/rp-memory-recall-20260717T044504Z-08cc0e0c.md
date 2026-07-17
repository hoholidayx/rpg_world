<!-- run-id:20260717T044504Z-08cc0e0c -->
# RP Memory 召回基准总结

- Run ID：`20260717T044504Z-08cc0e0c`
- 开始时间（UTC）：`2026-07-17T04:45:04.288731Z`
- Git revision：`c21e888cc0ae6bec3ee53c72267260466f276354`（dirty：`true`）
- 执行命令：`uv run python -m rp_memory.benchmark suite --record`
- 本地完整报告：`/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/results/20260717T044504Z-08cc0e0c.md`
- 门禁状态：仅记录，不阻断变更或发布。
- 说明：这是同分排序修复前的记录；它暴露了 FTS 同分结果受路径影响的问题，后续已在 `324dfcf` 固定 benchmark evidence ID，请使用下一次记录作为可复现基线。

## 能力矩阵

服务探测：`skipped_service_unreachable` — LLM Service 不可达。

| 能力 | 状态 | 说明 |
|---|---|---|
| embedding | `skipped_service_unreachable` | LLM Service 连接失败，未包含向量召回结果。 |
| planner | `skipped_disabled` | `memory.query_planner_enabled=false`，未运行 LLM 查询扩展。 |
| reranker | `skipped_disabled` | `memory.rerank_enabled=false`，未运行重排。 |

## 核心指标

| 路径 | 状态 | 数据集 | 题数 | Hit@1 | Recall@5 | MRR | nDCG | Coverage | No-answer | Forbidden@1 | Forbidden@5 | Before-gold |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `offline.keyword_rule` | `executed` | locomo | 1986 | 0.335015 | 0.571645 | 0.424655 | 0.436174 | 0.527080 | - | - | - | - |
| `offline.keyword_rule` | `executed` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |
| `offline.local_fallback` | `executed` | locomo | 1986 | 0.337538 | 0.570636 | 0.427296 | 0.438085 | 0.526954 | - | - | - | - |
| `offline.local_fallback` | `executed` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |
| `configured.effective` | `degraded_runtime_fallback` | locomo | 1986 | 0.337538 | 0.570636 | 0.427338 | 0.437987 | 0.526701 | - | - | - | - |
| `configured.effective` | `degraded_runtime_fallback` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |

RP Gold 污染题：`contradiction:q1`、`epistemic:q1`、`identity:q1`、`item:q1`。

## 名词解释

| 名词 | 解释 |
|---|---|
| Hit@1 | 第一名结果命中任一 gold evidence 的题目比例。 |
| Recall@K / Recall@5 | 前 K 个结果至少命中一个 gold evidence 的题目比例；当前 K=5。 |
| MRR | 首个正确 evidence 排名倒数的平均值。 |
| nDCG | 考虑多个正确 evidence 及其排序位置的归一化指标。 |
| Evidence Coverage | 前 K 个结果覆盖全部 gold evidence 的平均比例。 |
| No-answer Accuracy | 无答案题没有返回候选的比例。 |
| Forbidden@1 / Forbidden@K | 第一名或前 K 名出现明确禁止 evidence 的比例，越低越好。 |
| Forbidden-before-gold | 禁止 evidence 排在首个正确 evidence 前面的比例。 |
| embedding / vector retrieval | 文本向量编码能力及其向量相似度召回路径。 |
| keyword retrieval | 按关键词或全文索引召回候选。 |
| raw-md fallback | 从原始 Markdown 文件补充候选的本地兜底路径。 |
| query planner / expanded query | 查询规划器及其生成的查询变体。 |
| hybrid fusion / candidate pool | 多路候选的融合过程及进入融合或重排的候选集合。 |
| rerank | 对候选再次相关性评分并调整排序。 |
| runtime fallback | 能力执行异常后退回本地路径。 |
| Provider | LLM Service 暴露的具体模型后端选项。 |
| query-local score | 只在同一次查询候选之间有相对意义的分数。 |
