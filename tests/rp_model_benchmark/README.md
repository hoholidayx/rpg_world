# 中立 RP 模型评测

该评测直接调用 LLM Service 的 `agent.main` Provider，不导入 Story Pack、不创建
Session 或数据库数据。每题只使用冻结的核心 RP 契约和自包含的虚构事实，用于区分
模型本身的事实遵循、玩家能动性、工具使用和叙事能力。

```bash
# 日常 12 题单轮 smoke，默认使用 agent.main 当前 Provider
uv run python -m tests.rp_model_benchmark run --suite smoke

# 48 题、每题两轮
uv run python -m tests.rp_model_benchmark run --suite full

# 显式比较多个已配置 Provider
uv run python -m tests.rp_model_benchmark run --suite full \
  --provider deepseek_v4_flash --provider another_provider

# Codex 完成证据模板后生成最终报告
uv run python -m tests.rp_model_benchmark finalize --run-dir <run-dir>
```

原始报告、完整请求/响应、缓存与 token 统计写入已忽略的
`data/benchmarks/rp-model/`。第一版所有质量分数只报告；数据、配置或 Provider
基础设施错误才使运行命令失败。语义结论必须由 Codex 填写绑定到原始 queue SHA-256
的 `codex-review.json`，不会调用被测模型或额外 verifier LLM。
