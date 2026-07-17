<!-- run-id:20260717T060413Z-e12c7ecd -->
# RP Memory 召回基准总结

- Run ID：`20260717T060413Z-e12c7ecd`
- 开始时间（UTC）：`2026-07-17T06:04:13.067575Z`
- Git revision：`abccb93f0b714a01bd280788a49ad9830358aebd`（dirty：`true`）
- 执行命令：`uv run python -m rp_memory.benchmark suite --record`
- 本地完整报告：`/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/results/rp-memory-recall-full-20260717T060413Z-e12c7ecd.md`
- 门禁状态：仅记录，不阻断变更或发布。
- Provider 提示：配置路径可能产生费用且结果可能非确定。

## 测试环境与路径

| 字段 | 值 |
|---|---|
| Python | `3.12.10 (v3.12.10:0cc81280367, Apr 8 2025, 08:46:59) [Clang 13.0.0 (clang-1300.0.29.30)]` |
| SQLite / jieba | `3.49.1` / `0.42.1` |
| RPG profile | `local` |
| LLM Service | `http://127.0.0.1:8012/llm/v1` |
| 仓库 | `/Users/hoholiday/Projects/Pycharm/rpg_world` |
| 完整报告 | `/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/results/rp-memory-recall-full-20260717T060413Z-e12c7ecd.md` |
| `locomo_full` | `/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/locomo/locomo.full.jsonl` |
| `locomo_raw` | `/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/locomo/locomo10.3eb6f2c5.json` |
| `rp_gold` | `/Users/hoholiday/Projects/Pycharm/rpg_world/rp_memory/benchmark/rp_gold.json` |

## 数据集来源

| 数据集 | 固定来源 | 完整性 / 审核 | 许可 |
|---|---|---|---|
| LoCoMo | commit `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`；`https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json` | size `2805274`；SHA-256 `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` | [CC BY-NC 4.0](https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/LICENSE.txt) |
| RP Gold Seed | 仓库内维护 `/Users/hoholiday/Projects/Pycharm/rpg_world/rp_memory/benchmark/rp_gold.json` | `seed_pending_two_person_review` | project-maintained |

## 能力矩阵

服务探测：`skipped_service_unreachable` — LLM service unavailable: All connection attempts failed

| 能力 | 状态 | Provider | Backend / 模型 | Dimension | 原因 |
|---|---|---|---|---:|---|
| planner | `skipped_disabled` | `-` | `-` / `-` | - | memory.query_planner_enabled is false |
| reranker | `skipped_disabled` | `-` | `-` / `-` | - | memory.rerank_enabled is false |
| embedding | `skipped_service_unreachable` | `-` | `-` / `-` | - | LLM service unavailable: All connection attempts failed |

## 核心指标

| 路径 | 状态 | 数据集 | 总题数 | 计分 | 未计分 | Hit@1 | Recall@5 | MRR | nDCG | Coverage | No-answer | Forbidden@1 | Forbidden@5 | Before-gold |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `offline.keyword_rule` | `executed` | locomo | 1986 | 1982 | 4 | 0.335015 | 0.572149 | 0.424908 | 0.436402 | 0.527433 | - | - | - | - |
| `offline.keyword_rule` | `executed` | rp-gold | 60 | 60 | 0 | 0.709091 | 0.981818 | 0.839394 | 0.855301 | 0.936364 | 0.800000 | 0.283333 | 0.716667 | 0.283333 |
| `offline.local_fallback` | `executed` | locomo | 1986 | 1982 | 4 | 0.337538 | 0.571140 | 0.427506 | 0.438158 | 0.527055 | - | - | - | - |
| `offline.local_fallback` | `executed` | rp-gold | 60 | 60 | 0 | 0.727273 | 1.000000 | 0.854545 | 0.871102 | 0.963636 | 0.600000 | 0.283333 | 0.733333 | 0.283333 |
| `configured.embedding.default` | `skipped_service_unreachable` | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `configured.planner.default` | `skipped_disabled` | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `configured.rerank.default` | `skipped_disabled` | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `configured.effective` | `degraded_runtime_fallback` | locomo | 1986 | 1982 | 4 | 0.337538 | 0.571140 | 0.427506 | 0.438158 | 0.527055 | - | - | - | - |
| `configured.effective` | `degraded_runtime_fallback` | rp-gold | 60 | 60 | 0 | 0.727273 | 1.000000 | 0.854545 | 0.871102 | 0.963636 | 0.600000 | 0.283333 | 0.733333 | 0.283333 |

## 分类指标

| 路径 | 数据集 | 分类 | 总题数 | 计分 | 未计分 | Hit@1 | Recall@5 | MRR | Forbidden@5 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `offline.keyword_rule` | locomo | 1 | 282 | 282 | 0 | 0.180851 | 0.393617 | 0.256738 | - |
| `offline.keyword_rule` | locomo | 2 | 321 | 321 | 0 | 0.414330 | 0.651090 | 0.506542 | - |
| `offline.keyword_rule` | locomo | 3 | 96 | 92 | 4 | 0.076087 | 0.271739 | 0.152536 | - |
| `offline.keyword_rule` | locomo | 4 | 841 | 841 | 0 | 0.375743 | 0.602854 | 0.461811 | - |
| `offline.keyword_rule` | locomo | 5 | 446 | 446 | 0 | 0.352018 | 0.632287 | 0.459081 | - |
| `offline.keyword_rule` | rp-gold | alias_and_pronoun | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.200000 |
| `offline.keyword_rule` | rp-gold | attempt_vs_success | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `offline.keyword_rule` | rp-gold | commitment_vs_completion | 5 | 5 | 0 | 0.000000 | 0.800000 | 0.400000 | 1.000000 |
| `offline.keyword_rule` | rp-gold | epistemic_status | 5 | 5 | 0 | 0.800000 | 1.000000 | 0.900000 | 1.000000 |
| `offline.keyword_rule` | rp-gold | latest_fact | 5 | 5 | 0 | 0.200000 | 1.000000 | 0.600000 | 1.000000 |
| `offline.keyword_rule` | rp-gold | multi_evidence | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.400000 |
| `offline.keyword_rule` | rp-gold | no_answer | 5 | 5 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.200000 |
| `offline.keyword_rule` | rp-gold | player_vs_npc | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `offline.keyword_rule` | rp-gold | relative_and_scene_time | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `offline.keyword_rule` | rp-gold | scene_status_narrative_boundary | 5 | 5 | 0 | 0.800000 | 1.000000 | 0.900000 | 0.600000 |
| `offline.keyword_rule` | rp-gold | state_and_item_location | 5 | 5 | 0 | 0.000000 | 1.000000 | 0.433333 | 1.000000 |
| `offline.keyword_rule` | rp-gold | story_session_isolation | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `offline.local_fallback` | locomo | 1 | 282 | 282 | 0 | 0.191489 | 0.386525 | 0.262293 | - |
| `offline.local_fallback` | locomo | 2 | 321 | 321 | 0 | 0.420561 | 0.657321 | 0.512565 | - |
| `offline.local_fallback` | locomo | 3 | 96 | 92 | 4 | 0.065217 | 0.271739 | 0.153442 | - |
| `offline.local_fallback` | locomo | 4 | 841 | 841 | 0 | 0.374554 | 0.605232 | 0.462683 | - |
| `offline.local_fallback` | locomo | 5 | 446 | 446 | 0 | 0.356502 | 0.623318 | 0.460949 | - |
| `offline.local_fallback` | rp-gold | alias_and_pronoun | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.200000 |
| `offline.local_fallback` | rp-gold | attempt_vs_success | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `offline.local_fallback` | rp-gold | commitment_vs_completion | 5 | 5 | 0 | 0.000000 | 1.000000 | 0.466667 | 1.000000 |
| `offline.local_fallback` | rp-gold | epistemic_status | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `offline.local_fallback` | rp-gold | latest_fact | 5 | 5 | 0 | 0.200000 | 1.000000 | 0.600000 | 1.000000 |
| `offline.local_fallback` | rp-gold | multi_evidence | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.400000 |
| `offline.local_fallback` | rp-gold | no_answer | 5 | 5 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.400000 |
| `offline.local_fallback` | rp-gold | player_vs_npc | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `offline.local_fallback` | rp-gold | relative_and_scene_time | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `offline.local_fallback` | rp-gold | scene_status_narrative_boundary | 5 | 5 | 0 | 0.800000 | 1.000000 | 0.900000 | 0.600000 |
| `offline.local_fallback` | rp-gold | state_and_item_location | 5 | 5 | 0 | 0.000000 | 1.000000 | 0.433333 | 1.000000 |
| `offline.local_fallback` | rp-gold | story_session_isolation | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `configured.effective` | locomo | 1 | 282 | 282 | 0 | 0.191489 | 0.386525 | 0.262293 | - |
| `configured.effective` | locomo | 2 | 321 | 321 | 0 | 0.420561 | 0.657321 | 0.512565 | - |
| `configured.effective` | locomo | 3 | 96 | 92 | 4 | 0.065217 | 0.271739 | 0.153442 | - |
| `configured.effective` | locomo | 4 | 841 | 841 | 0 | 0.374554 | 0.605232 | 0.462683 | - |
| `configured.effective` | locomo | 5 | 446 | 446 | 0 | 0.356502 | 0.623318 | 0.460949 | - |
| `configured.effective` | rp-gold | alias_and_pronoun | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.200000 |
| `configured.effective` | rp-gold | attempt_vs_success | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `configured.effective` | rp-gold | commitment_vs_completion | 5 | 5 | 0 | 0.000000 | 1.000000 | 0.466667 | 1.000000 |
| `configured.effective` | rp-gold | epistemic_status | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| `configured.effective` | rp-gold | latest_fact | 5 | 5 | 0 | 0.200000 | 1.000000 | 0.600000 | 1.000000 |
| `configured.effective` | rp-gold | multi_evidence | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.400000 |
| `configured.effective` | rp-gold | no_answer | 5 | 5 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.400000 |
| `configured.effective` | rp-gold | player_vs_npc | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `configured.effective` | rp-gold | relative_and_scene_time | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 0.600000 |
| `configured.effective` | rp-gold | scene_status_narrative_boundary | 5 | 5 | 0 | 0.800000 | 1.000000 | 0.900000 | 0.600000 |
| `configured.effective` | rp-gold | state_and_item_location | 5 | 5 | 0 | 0.000000 | 1.000000 | 0.433333 | 1.000000 |
| `configured.effective` | rp-gold | story_session_isolation | 5 | 5 | 0 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |

## 结果判读

- `offline.keyword_rule` 是不包含 embedding、LLM Planner 或 rerank 的纯离线关键词基线。它适合稳定回归候选覆盖，但无法判断旧状态与当前状态、承诺与完成、尝试与结果等事实阶段；因此该路径的 Forbidden 指标只用于诊断词法候选污染，不能代表完整模型配置路径的质量。
- 不同检索路径的指标不能直接混合归因。只有对应能力状态为 `executed` 时，才能评价 embedding、Planner 或 rerank 的实际效果；横向回归应优先比较相同路径。
- locomo：Hit@1 `0.335015`，Recall@5 `0.572149`，计分 `1982/1986`；指标用于相对比较，不单独构成 RP 质量结论。
- RP Gold：Hit@1 `0.709091`，Recall@5 `0.981818`，计分 `60/60`；Forbidden@5 `0.716667`。该数值来自上述离线关键词基线，较高值主要反映词法召回会同时保留主题相关但事实阶段错误的候选；Gold 尚未完成双人审核，因此当前结果不足以作为发布质量门禁。
- 向量召回：`skipped_service_unreachable`，本次未包含该路径；原因：LLM service unavailable: All connection attempts failed
- Planner 扩展查询：`skipped_disabled`，本次未包含该路径；原因：memory.query_planner_enabled is false
- rerank：`skipped_disabled`，本次未包含该路径；原因：memory.rerank_enabled is false

## Planner 与查询扩展活动

| 路径 | 数据集 | Planner 来源 | 使用扩展的题目 | 变体数 | 扩展用途 |
|---|---|---|---:|---:|---|
| `offline.keyword_rule` | locomo | `rule_based=1982` | 0/1982 | 0 | existing-candidate scoring only |
| `offline.keyword_rule` | rp-gold | `rule_based=60` | 12/60 | 12 | existing-candidate scoring only |
| `offline.local_fallback` | locomo | `rule_based=1982` | 0/1982 | 0 | raw-md candidate generation and existing-candidate scoring |
| `offline.local_fallback` | rp-gold | `rule_based=60` | 12/60 | 12 | raw-md candidate generation and existing-candidate scoring |
| `configured.effective` | locomo | `rule_based=1982` | 0/1982 | 0 | raw-md candidate generation and existing-candidate scoring |
| `configured.effective` | rp-gold | `rule_based=60` | 12/60 | 12 | raw-md candidate generation and existing-candidate scoring |

## RP Gold 失败与污染

- `offline.keyword_rule`：alias:q1, alias:q2, attempt:q1, attempt:q2, attempt:q3, attempt:q4, attempt:q5, boundary:q2, boundary:q3, boundary:q4, commit:q1, commit:q2, commit:q3, commit:q4, commit:q5, epi:q1, epi:q2, epi:q3, epi:q4, epi:q5, identity:q1, identity:q3, identity:q5, isolation:q1, isolation:q2, isolation:q3, isolation:q4, isolation:q5, latest:q1, latest:q2, latest:q3, latest:q4, latest:q5, multi:q1, multi:q2, multi:q4, multi:q5, none:q5, state:q1, state:q2, state:q3, state:q4, state:q5, time:q2, time:q3, time:q4
- `offline.local_fallback`：alias:q1, attempt:q1, attempt:q2, attempt:q3, attempt:q4, attempt:q5, boundary:q2, boundary:q3, boundary:q4, commit:q1, commit:q2, commit:q3, commit:q4, commit:q5, epi:q1, epi:q2, epi:q3, epi:q4, epi:q5, identity:q1, identity:q3, identity:q5, isolation:q1, isolation:q2, isolation:q3, isolation:q4, isolation:q5, latest:q1, latest:q2, latest:q3, latest:q4, latest:q5, multi:q1, multi:q2, multi:q4, multi:q5, none:q2, none:q5, state:q1, state:q2, state:q3, state:q4, state:q5, time:q2, time:q3, time:q4
- `configured.effective`：alias:q1, attempt:q1, attempt:q2, attempt:q3, attempt:q4, attempt:q5, boundary:q2, boundary:q3, boundary:q4, commit:q1, commit:q2, commit:q3, commit:q4, commit:q5, epi:q1, epi:q2, epi:q3, epi:q4, epi:q5, identity:q1, identity:q3, identity:q5, isolation:q1, isolation:q2, isolation:q3, isolation:q4, isolation:q5, latest:q1, latest:q2, latest:q3, latest:q4, latest:q5, multi:q1, multi:q2, multi:q4, multi:q5, none:q2, none:q5, state:q1, state:q2, state:q3, state:q4, state:q5, time:q2, time:q3, time:q4

## 名词解释

| 名词 | 解释 |
|---|---|
| Hit@1 | 第一名结果命中任一 gold evidence 的题目比例。 |
| Recall@K / Recall@5 | 前 K 个结果至少命中一个 gold evidence 的题目比例；当前 K=5。 |
| MRR | 首个正确 evidence 排名倒数的平均值，越接近 1 越好。 |
| nDCG | 考虑多个正确 evidence 及其排序位置的归一化折损累计增益。 |
| Evidence Coverage | 前 K 个结果覆盖全部 gold evidence 的平均比例。 |
| No-answer Accuracy | 无答案题没有返回候选的比例。 |
| Forbidden@1 / Forbidden@K | 第一名或前 K 名出现明确禁止 evidence 的比例，越低越好。 |
| Forbidden-before-gold | 禁止 evidence 排在首个正确 evidence 前面的题目比例，越低越好。 |
| embedding | 把文本编码为向量的模型能力。 |
| vector retrieval | 按向量相似度召回候选。 |
| keyword retrieval | 按关键词或全文索引召回候选。 |
| raw-md fallback | 从原始 Markdown 文件补充候选的本地兜底路径。 |
| query planner | 把原始问题规范化并生成检索词或扩展查询的规划器。 |
| expanded query | Planner 为提高召回率生成的查询变体。 |
| hybrid fusion | 合并 vector、keyword、raw-md 等多路候选和分数。 |
| rerank | 对候选池再次相关性评分并调整排序。 |
| candidate pool | 进入融合或重排阶段的候选集合。 |
| runtime fallback | 已通过能力探测，但执行时异常而退回本地路径。 |
| Provider | 由 LLM Service 暴露的具体模型后端选项。 |
| query-local score | 只在同一次查询的候选之间有相对意义的排序分数。 |
