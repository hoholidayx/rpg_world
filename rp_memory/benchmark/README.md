# RP Memory 召回基准

固定套件默认同时运行 LoCoMo 与项目维护的 RP Gold Seed。LongMemEval-S cleaned
作为可选第三方长记忆数据集，只有显式选择时才会下载和执行。套件会探测 LLM
Service，并分别执行当前可用的 embedding、LLM query planner、reranker Provider；
未配置、禁用、服务不可达或探测失败时，只跳过对应路径并在报告中说明原因。

```bash
# 默认完整套件：LoCoMo full + RP Gold
uv run python -m rp_memory.benchmark suite

# 成功后生成独立的 Git 跟踪中文总结并更新索引
uv run python -m rp_memory.benchmark suite --record

# 不访问 LLM Service；数据缓存缺失时仍可能下载所选数据集
uv run python -m rp_memory.benchmark suite --offline-only

# 显式加入 LongMemEval-S；首次需要下载约 277 MB
uv run python -m rp_memory.benchmark suite \
  --datasets locomo,rp-gold,longmemeval-s

# 只准备指定数据集；有效缓存不会联网
uv run python -m rp_memory.benchmark prepare \
  --datasets locomo,longmemeval-s
```

`--datasets` 可以重复传入或使用逗号分隔，支持 `locomo`、`rp-gold`、
`longmemeval-s`。`--locomo-tier smoke` 仅供开发调试；记录包含 LoCoMo 的正式结果时
仍强制使用 full。指标目前只记录，不作为 CI 或发布门禁。

## 固定路径矩阵

1. `offline.keyword_rule`：冻结的 jieba + keyword + Rule Planner 基线。
2. `offline.local_fallback`：keyword + 当前配置的 raw-md fallback。
3. `configured.embedding.<provider>`：vector + keyword + Rule Planner。
4. `configured.planner.<provider>`：keyword + LLM Planner，运行失败回退 Rule Planner。
5. `configured.rerank.<provider>`：keyword + Rule Planner + pointwise rerank。
6. `configured.effective`：默认 Provider 与当前开关形成的实际组合；能力异常时运行
   本地 fallback，并标记 `degraded_runtime_fallback`。

所有路径关闭 recency，因为临时索引时间不是数据集事实。报告记录 Planner →
keyword/vector/raw-md → fusion → rerank → Top-5 的完整链路、候选池、Tokenizer、
权重、Provider、模型、dimension、Planner source、扩展查询覆盖题数与变体数。
hybrid/final score 只是单次查询内的相对排序信号，不是概率，不能跨查询比较。

## 数据与完整性

- LoCoMo 固定到 commit `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`，
  原始文件 SHA-256 为
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`，
  许可为 CC BY-NC 4.0。
- LongMemEval-S cleaned 固定到 Hugging Face revision
  `98d7416c24c778c2fee6e6f3006e7a073259d48f`，原始文件大小 277,383,467
  bytes，SHA-256 为
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`，
  数据卡声明 MIT。它是最小的正式 haystack 版本；15 MB oracle 只包含答案会话，
  不适合衡量真实召回，因此不作为 benchmark。
- RP Gold Seed 固定为 12 类、每类 5 题，共 60 题。当前仍为
  `seed_pending_two_person_review`，双人独立审核前不能升级为发布门禁。

下载器使用有限重试、响应/累计大小上限、size + SHA-256 校验和临时文件原子替换；
有效缓存不会联网。LongMemEval 使用流式 JSON array 解码，避免一次性加载 277 MB
原始文件；缺少 `has_answer` evidence 的问题明确计为 `unscored`。

## 报告位置

- 每次运行的完整中文报告：
  `data/benchmarks/results/rp-memory-recall-full-<UTC>-<run-id>.md`
- 每次成功执行 `--record` 的精简中文报告：
  `docs/benchmarks/runs/rp-memory-recall-<UTC>-<run-id>.md`
- Git 跟踪的运行索引：`docs/benchmarks/README.md`

原始与转换数据、临时索引、完整逐题结果均位于已忽略的 `data/benchmarks/`，
不会提交 Git。只有代码、测试、RP Gold、精简总结和索引进入版本控制。

状态值固定为：`executed`、`skipped_disabled`、`skipped_unconfigured`、
`skipped_service_unreachable`、`skipped_probe_failed`、
`degraded_runtime_fallback`、`failed`。
