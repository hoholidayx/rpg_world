# RP Memory Recall Benchmark History

This append-only summary records explicit `--record` runs. The suite is
informational and does not block changes yet. Full per-case diagnostics stay
in the ignored local `data/benchmarks/results/` report named by each entry.

Scores from hybrid fusion and reranking are query-local ordering signals, not
probabilities and not comparable across independent queries.

<!-- run-id:20260717T044504Z-08cc0e0c -->
## 2026-07-17T04:45:04.288731Z — `20260717T044504Z-08cc0e0c`

- Revision: `c21e888cc0ae6bec3ee53c72267260466f276354` (dirty: `true`)
- Command: `uv run python -m rp_memory.benchmark suite --record`
- Full local report: `/Users/hoholiday/Projects/Pycharm/rpg_world/data/benchmarks/results/20260717T044504Z-08cc0e0c.md`
- Gate: informational only.
- Configured Provider results may have cost and non-determinism.
- Follow-up: this pre-stabilization run exposed path-dependent ordering for
  FTS ties; benchmark evidence IDs were stabilized in `324dfcf`, so use the
  next recorded run as the reproducible baseline.

Capability matrix:

| Capability | Status | Provider | Backend/model | Dimension |
|---|---|---|---|---:|
| planner | `skipped_disabled` | `-` | `-` / `-` | - |
| reranker | `skipped_disabled` | `-` | `-` / `-` | - |
| embedding | `skipped_service_unreachable` | `-` | `-` / `-` | - |
| Path | Status | Dataset | Cases | Hit@1 | Recall@5 | MRR | nDCG | Coverage | No-answer | Forbidden@1 | Forbidden@5 | Before-gold |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `offline.keyword_rule` | `executed` | locomo | 1986 | 0.335015 | 0.571645 | 0.424655 | 0.436174 | 0.527080 | - | - | - | - |
| `offline.keyword_rule` | `executed` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |
| `offline.local_fallback` | `executed` | locomo | 1986 | 0.337538 | 0.570636 | 0.427296 | 0.438085 | 0.526954 | - | - | - | - |
| `offline.local_fallback` | `executed` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |
| `configured.embedding.default` | `skipped_service_unreachable` | - | - | - | - | - | - | - | - | - | - | - |
| `configured.planner.default` | `skipped_disabled` | - | - | - | - | - | - | - | - | - | - | - |
| `configured.rerank.default` | `skipped_disabled` | - | - | - | - | - | - | - | - | - | - | - |
| `configured.effective` | `degraded_runtime_fallback` | locomo | 1986 | 0.337538 | 0.570636 | 0.427338 | 0.437987 | 0.526701 | - | - | - | - |
| `configured.effective` | `degraded_runtime_fallback` | rp-gold | 13 | 0.916667 | 1.000000 | 0.958333 | 0.969244 | 1.000000 | 1.000000 | 0.100000 | 0.400000 | 0.100000 |

Planner/query expansion activity:

| Path | Dataset | Planner sources | Cases with expansion | Variants | Expansion use |
|---|---|---|---:|---:|---|
| `offline.keyword_rule` | locomo | `rule_based=1982` | 0/1982 | 0 | existing-candidate scoring only |
| `offline.keyword_rule` | rp-gold | `rule_based=13` | 3/13 | 3 | existing-candidate scoring only |
| `offline.local_fallback` | locomo | `rule_based=1982` | 0/1982 | 0 | raw-md candidate generation and existing-candidate scoring |
| `offline.local_fallback` | rp-gold | `rule_based=13` | 3/13 | 3 | raw-md candidate generation and existing-candidate scoring |
| `configured.effective` | locomo | `rule_based=1982` | 0/1982 | 0 | raw-md candidate generation and existing-candidate scoring |
| `configured.effective` | rp-gold | `rule_based=13` | 3/13 | 3 | raw-md candidate generation and existing-candidate scoring |

RP Gold failures/contamination:

- `offline.keyword_rule`: contradiction:q1, epistemic:q1, identity:q1, item:q1
- `offline.local_fallback`: contradiction:q1, epistemic:q1, identity:q1, item:q1
- `configured.effective`: contradiction:q1, epistemic:q1, identity:q1, item:q1
