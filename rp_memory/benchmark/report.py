"""简体中文 Markdown 报告、独立归档与索引。"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from rp_memory.benchmark.locomo import MANIFEST as LOCOMO_MANIFEST
from rp_memory.benchmark.longmemeval import MANIFEST as LONGMEMEVAL_MANIFEST
from rp_memory.benchmark.models import (
    BenchmarkEnvironment,
    BenchmarkPathResult,
    CapabilityProbe,
    CaseResult,
    DatasetResult,
    SuiteResult,
)


INDEX_HEADER = """# RP Memory 召回基准记录

本目录只跟踪显式执行 `suite --record` 后产生的精简总结。每次运行的完整逐题诊断
保存在已被 Git 忽略的 `data/benchmarks/results/`。指标目前仅用于观察和比较，不作为
CI 或发布门禁。

混合融合与重排分数只表示单次查询内部的相对顺序，不是概率，也不能跨查询比较。

<!-- benchmark-runs:start -->
| 开始时间（UTC） | Run ID | Git revision | 工作区 | 数据集核心指标 | 能力状态 | 报告 |
|---|---|---|---|---|---|---|
<!-- benchmark-runs:end -->
"""


GLOSSARY: tuple[tuple[str, str], ...] = (
    ("Hit@1", "第一名结果命中任一 gold evidence 的题目比例。"),
    ("Recall@K / Recall@5", "前 K 个结果至少命中一个 gold evidence 的题目比例；当前 K=5。"),
    ("MRR", "首个正确 evidence 排名倒数的平均值，越接近 1 越好。"),
    ("nDCG", "考虑多个正确 evidence 及其排序位置的归一化折损累计增益。"),
    ("Evidence Coverage", "前 K 个结果覆盖全部 gold evidence 的平均比例。"),
    ("No-answer Accuracy", "无答案题没有返回候选的比例。"),
    ("Forbidden@1 / Forbidden@K", "第一名或前 K 名出现明确禁止 evidence 的比例，越低越好。"),
    ("Forbidden-before-gold", "禁止 evidence 排在首个正确 evidence 前面的题目比例，越低越好。"),
    ("embedding", "把文本编码为向量的模型能力。"),
    ("vector retrieval", "按向量相似度召回候选。"),
    ("keyword retrieval", "按关键词或全文索引召回候选。"),
    ("raw-md fallback", "从原始 Markdown 文件补充候选的本地兜底路径。"),
    ("query planner", "把原始问题规范化并生成检索词或扩展查询的规划器。"),
    ("expanded query", "Planner 为提高召回率生成的查询变体。"),
    ("hybrid fusion", "合并 vector、keyword、raw-md 等多路候选和分数。"),
    ("rerank", "对候选池再次相关性评分并调整排序。"),
    ("candidate pool", "进入融合或重排阶段的候选集合。"),
    ("runtime fallback", "已通过能力探测，但执行时异常而退回本地路径。"),
    ("Provider", "由 LLM Service 暴露的具体模型后端选项。"),
    ("query-local score", "只在同一次查询的候选之间有相对意义的排序分数。"),
)


def new_run_identity() -> tuple[str, str]:
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    return run_id, now.isoformat().replace("+00:00", "Z")


def capture_environment(
    *,
    run_id: str,
    started_at_utc: str,
    command: str,
    repo_root: Path,
    paths: dict[str, Path],
) -> BenchmarkEnvironment:
    revision = _git(repo_root, "rev-parse", "HEAD") or "unavailable"
    status = _git(repo_root, "status", "--porcelain")
    status_lines = [line for line in status.splitlines() if line.strip()]
    try:
        jieba_version = importlib.metadata.version("jieba")
    except importlib.metadata.PackageNotFoundError:
        jieba_version = "unavailable"
    return BenchmarkEnvironment(
        run_id=run_id,
        started_at_utc=started_at_utc,
        command=command,
        repo_root=str(repo_root.resolve()),
        git_revision=revision,
        git_dirty=bool(status_lines),
        git_status_summary="; ".join(status_lines[:40]) or "clean",
        python_version=" ".join(sys.version.split()),
        sqlite_version=sqlite3.sqlite_version,
        jieba_version=jieba_version,
        platform=platform.platform(),
        paths=tuple((name, str(path.resolve())) for name, path in sorted(paths.items())),
        profile=os.environ.get("RPG_WORLD_PROFILE", "local"),
        llm_service_url=_safe_service_url(
            os.environ.get(
                "RPG_WORLD_LLM_SERVICE_URL",
                "http://127.0.0.1:8012/llm/v1",
            )
        ),
    )


def render_full_report(suite: SuiteResult) -> str:
    env = suite.environment
    lines = [
        "# RP Memory 召回基准完整报告",
        "",
        f"- Run ID：`{env.run_id}`",
        f"- 开始时间（UTC）：`{env.started_at_utc}`",
        f"- 完成时间（UTC）：`{suite.finished_at_utc}`",
        f"- 是否成功：`{str(suite.successful).lower()}`",
        "- 门禁状态：仅记录，不阻断变更或发布。",
        "- 成本提示：已配置的 Provider 路径可能调用远端服务、产生费用且结果可能非确定。",
        "- 分数提示：hybrid/final score 是 query-local score，不是概率。",
        "",
        "## 测试环境",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| 执行命令 | `{_cell(env.command)}` |",
        f"| 仓库路径 | `{_cell(env.repo_root)}` |",
        f"| Git revision | `{_cell(env.git_revision)}` |",
        f"| Git dirty | `{str(env.git_dirty).lower()}` |",
        f"| Git 状态 | `{_cell(env.git_status_summary)}` |",
        f"| Python | `{_cell(env.python_version)}` |",
        f"| SQLite | `{_cell(env.sqlite_version)}` |",
        f"| jieba | `{_cell(env.jieba_version)}` |",
        f"| 平台 | `{_cell(env.platform)}` |",
        f"| RPG profile | `{_cell(env.profile or '-')}` |",
        f"| LLM Service | `{_cell(env.llm_service_url or '-')}` |",
        "",
        "## 数据与报告路径",
        "",
        "| 用途 | 绝对路径 |",
        "|---|---|",
    ]
    lines.extend(f"| `{_cell(name)}` | `{_cell(path)}` |" for name, path in env.paths)
    lines.extend(_dataset_provenance(env))
    lines.extend(_capability_section(suite))
    lines.extend(_metrics_section(suite.paths))
    lines.extend(_category_metrics_section(suite.paths))
    lines.extend(_assessment_section(suite))
    lines.extend(_path_details(suite.paths))
    if suite.errors:
        lines.extend(("", "## 套件错误", ""))
        lines.extend(f"- `{_cell(error)}`" for error in suite.errors)
    lines.extend(_glossary_section())
    lines.append("")
    return "\n".join(lines)


def render_summary_report(suite: SuiteResult, *, local_report_path: Path) -> str:
    env = suite.environment
    lines = [
        f"<!-- run-id:{env.run_id} -->",
        "# RP Memory 召回基准总结",
        "",
        f"- Run ID：`{env.run_id}`",
        f"- 开始时间（UTC）：`{env.started_at_utc}`",
        f"- Git revision：`{env.git_revision}`（dirty：`{str(env.git_dirty).lower()}`）",
        f"- 执行命令：`{_cell(env.command)}`",
        f"- 本地完整报告：`{_cell(local_report_path.resolve())}`",
        "- 门禁状态：仅记录，不阻断变更或发布。",
        "- Provider 提示：配置路径可能产生费用且结果可能非确定。",
        "",
        "## 测试环境与路径",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| Python | `{_cell(env.python_version)}` |",
        f"| SQLite / jieba | `{_cell(env.sqlite_version)}` / `{_cell(env.jieba_version)}` |",
        f"| RPG profile | `{_cell(env.profile or '-')}` |",
        f"| LLM Service | `{_cell(env.llm_service_url or '-')}` |",
        f"| 仓库 | `{_cell(env.repo_root)}` |",
        f"| 完整报告 | `{_cell(local_report_path.resolve())}` |",
    ]
    for name, path in env.paths:
        if name in {"locomo_raw", "locomo_full", "rp_gold", "longmemeval_raw", "longmemeval_full"}:
            lines.append(f"| `{_cell(name)}` | `{_cell(path)}` |")
    lines.extend(_dataset_provenance(env))
    lines.extend(_compact_capability_table(suite))
    lines.extend(("", "## 核心指标", ""))
    lines.extend(_metrics_table(suite.paths))
    lines.extend(_category_metrics_section(suite.paths))
    lines.extend(_assessment_section(suite))
    lines.extend(_planner_activity(suite.paths))
    gold_issues = _gold_issue_summary(suite.paths)
    if gold_issues:
        lines.extend(("", "## RP Gold 失败与污染", ""))
        lines.extend(f"- `{path_id}`：{', '.join(ids)}" for path_id, ids in gold_issues)
    lines.extend(_glossary_section())
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)


def record_summary(
    suite: SuiteResult,
    *,
    runs_dir: Path,
    index_path: Path,
    local_report_path: Path,
) -> tuple[Path, bool]:
    if not suite.successful:
        raise ValueError("only a successful benchmark suite may be recorded")
    report_path = runs_dir / f"rp-memory-recall-{suite.environment.run_id}.md"
    created = not report_path.exists()
    if created:
        write_report(report_path, render_summary_report(suite, local_report_path=local_report_path))
    _update_index(index_path, suite, report_path)
    return report_path.resolve(), created


def _update_index(index_path: Path, suite: SuiteResult, report_path: Path) -> None:
    current = index_path.read_text(encoding="utf-8") if index_path.exists() else INDEX_HEADER
    start = "<!-- benchmark-runs:start -->"
    end = "<!-- benchmark-runs:end -->"
    if start not in current or end not in current:
        raise ValueError("benchmark report index markers are missing")
    if f"`{suite.environment.run_id}`" in current:
        return
    before, remainder = current.split(start, 1)
    body, after = remainder.split(end, 1)
    body_lines = [line for line in body.strip().splitlines() if line.strip()]
    header_lines = body_lines[:2]
    existing_rows = body_lines[2:]
    row = _index_row(suite, report_path, index_path)
    updated_body = "\n".join([*header_lines, row, *existing_rows])
    updated = f"{before}{start}\n{updated_body}\n{end}{after}"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(index_path, updated)


def _index_row(suite: SuiteResult, report_path: Path, index_path: Path) -> str:
    env = suite.environment
    baseline = next((item for item in suite.paths if item.path_id == "offline.keyword_rule"), None)
    metrics: list[str] = []
    if baseline is not None:
        for dataset in baseline.datasets:
            values = dataset.metrics
            metrics.append(
                f"{dataset.dataset}: H1 {_metric(values.get('hit_at_1'))}, "
                f"R5 {_metric(values.get('recall_at_k'))}"
            )
    capabilities = ", ".join(
        f"{probe.capability}={probe.status.value}" for probe in suite.capability_matrix.probes
    ) or f"service={suite.capability_matrix.service_status.value}"
    relative = os.path.relpath(report_path, index_path.parent).replace(os.sep, "/")
    return (
        f"| `{env.started_at_utc}` | `{env.run_id}` | `{env.git_revision[:12]}` | "
        f"{'dirty' if env.git_dirty else 'clean'} | {_cell('; '.join(metrics) or '-')} | "
        f"`{_cell(capabilities)}` | [查看]({_cell(relative)}) |"
    )


def _dataset_provenance(env: BenchmarkEnvironment) -> list[str]:
    paths = dict(env.paths)
    rows: list[str] = []
    if "locomo_raw" in paths:
        manifest = asdict(LOCOMO_MANIFEST)
        rows.append(
            f"| LoCoMo | commit `{manifest['commit']}`；`{_cell(manifest['source_url'])}` | "
            f"size `{manifest['size']}`；SHA-256 `{manifest['sha256']}` | "
            f"[{manifest['license']}]({manifest['license_url']}) |"
        )
    gold_path = paths.get("rp_gold", "")
    if gold_path:
        try:
            payload = json.loads(Path(gold_path).read_text(encoding="utf-8"))
            gold_status = str(payload.get("review_status", "unknown"))
        except Exception:
            gold_status = "unreadable"
        rows.append(
            f"| RP Gold Seed | 仓库内维护 `{_cell(gold_path)}` | `{_cell(gold_status)}` | project-maintained |"
        )
    if "longmemeval_raw" in paths:
        manifest = asdict(LONGMEMEVAL_MANIFEST)
        rows.append(
            f"| LongMemEval-S cleaned | revision `{manifest['revision']}`；"
            f"`{_cell(manifest['source_url'])}` | size `{manifest['size']}`；"
            f"SHA-256 `{manifest['sha256']}`；turn 级 evidence | "
            f"[{manifest['license']}]({manifest['license_url']}) |"
        )
    return [
        "",
        "## 数据集来源",
        "",
        "| 数据集 | 固定来源 | 完整性 / 审核 | 许可 |",
        "|---|---|---|---|",
        *rows,
    ]


def _capability_section(suite: SuiteResult) -> list[str]:
    matrix = suite.capability_matrix
    lines = [
        "",
        "## 能力矩阵",
        "",
        f"服务探测：`{matrix.service_status.value}` — {_cell(matrix.service_reason)}",
        "",
        "| 能力 | 状态 | Biz | Provider | Backend | 模型 | Dimension | 默认 | 原因 |",
        "|---|---|---|---|---|---|---:|---|---|",
    ]
    lines.extend(_probe_row(probe) for probe in matrix.probes)
    return lines


def _compact_capability_table(suite: SuiteResult) -> list[str]:
    matrix = suite.capability_matrix
    lines = [
        "",
        "## 能力矩阵",
        "",
        f"服务探测：`{matrix.service_status.value}` — {_cell(matrix.service_reason)}",
        "",
        "| 能力 | 状态 | Provider | Backend / 模型 | Dimension | 原因 |",
        "|---|---|---|---|---:|---|",
    ]
    for probe in matrix.probes:
        provider = probe.provider
        lines.append(
            "| {cap} | `{status}` | `{provider}` | `{backend}` / `{model}` | {dimension} | {reason} |".format(
                cap=_cell(probe.capability),
                status=probe.status.value,
                provider=_cell(provider.provider_key if provider else "-"),
                backend=_cell(provider.backend if provider else "-"),
                model=_cell(provider.model if provider else "-"),
                dimension=provider.dimension if provider and provider.dimension is not None else "-",
                reason=_cell(probe.reason),
            )
        )
    return lines


def _probe_row(probe: CapabilityProbe) -> str:
    provider = probe.provider
    return (
        f"| {_cell(probe.capability)} | `{probe.status.value}` | "
        f"`{_cell(provider.biz_key if provider else '-')}` | "
        f"`{_cell(provider.provider_key if provider else '-')}` | "
        f"`{_cell(provider.backend if provider else '-')}` | "
        f"`{_cell(provider.model if provider else '-')}` | "
        f"{provider.dimension if provider and provider.dimension is not None else '-'} | "
        f"{'是' if provider and provider.is_default else '否'} | {_cell(probe.reason)} |"
    )


def _metrics_section(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    return ["", "## 指标矩阵", "", *_metrics_table(paths)]


def _metrics_table(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    lines = [
        "| 路径 | 状态 | 数据集 | 总题数 | 计分 | 未计分 | Hit@1 | Recall@5 | MRR | nDCG | Coverage | No-answer | Forbidden@1 | Forbidden@5 | Before-gold |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for path in paths:
        if not path.datasets:
            lines.append(
                f"| `{_cell(path.path_id)}` | `{path.status.value}` | - | - | - | - | - | - | - | - | - | - | - | - | - |"
            )
            continue
        for dataset in path.datasets:
            metric = dataset.metrics
            lines.append(
                "| `{path}` | `{status}` | {dataset} | {cases} | {evaluated} | {unscored} | {hit1} | {recall} | {mrr} | {ndcg} | {coverage} | {no_answer} | {forbidden1} | {forbidden5} | {before} |".format(
                    path=_cell(path.path_id),
                    status=path.status.value,
                    dataset=_cell(dataset.dataset),
                    cases=metric.get("cases", "-"),
                    evaluated=metric.get("evaluated_cases", "-"),
                    unscored=metric.get("unscored_cases", "-"),
                    hit1=_metric(metric.get("hit_at_1")),
                    recall=_metric(metric.get("recall_at_k")),
                    mrr=_metric(metric.get("mrr")),
                    ndcg=_metric(metric.get("ndcg")),
                    coverage=_metric(metric.get("evidence_coverage")),
                    no_answer=_metric(metric.get("no_answer_accuracy")),
                    forbidden1=_metric(metric.get("forbidden_at_1_rate")),
                    forbidden5=_metric(metric.get("forbidden_hit_rate")),
                    before=_metric(metric.get("forbidden_before_gold_rate")),
                )
            )
    return lines


def _category_metrics_section(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    rows: list[str] = []
    for path in paths:
        for dataset in path.datasets:
            categories = dataset.metrics.get("category_metrics", {})
            if not isinstance(categories, dict):
                continue
            for category, values in sorted(categories.items()):
                if not isinstance(values, dict):
                    continue
                rows.append(
                    f"| `{_cell(path.path_id)}` | {_cell(dataset.dataset)} | {_cell(category)} | "
                    f"{values.get('cases', '-')} | {values.get('evaluated_cases', '-')} | "
                    f"{values.get('unscored_cases', '-')} | {_metric(values.get('hit_at_1'))} | "
                    f"{_metric(values.get('recall_at_k'))} | {_metric(values.get('mrr'))} | "
                    f"{_metric(values.get('forbidden_hit_rate'))} |"
                )
    if not rows:
        return []
    return [
        "",
        "## 分类指标",
        "",
        "| 路径 | 数据集 | 分类 | 总题数 | 计分 | 未计分 | Hit@1 | Recall@5 | MRR | Forbidden@5 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
    ]


def _assessment_section(suite: SuiteResult) -> list[str]:
    baseline = next(
        (path for path in suite.paths if path.path_id == "offline.keyword_rule"),
        None,
    )
    if baseline is None or not baseline.datasets:
        return []
    lines = ["", "## 结果判读", ""]
    for dataset in baseline.datasets:
        metrics = dataset.metrics
        evaluated = int(metrics.get("evaluated_cases", 0) or 0)
        cases = int(metrics.get("cases", 0) or 0)
        unscored = int(metrics.get("unscored_cases", 0) or 0)
        summary = (
            f"Hit@1 `{_metric(metrics.get('hit_at_1'))}`，Recall@5 "
            f"`{_metric(metrics.get('recall_at_k'))}`，计分 `{evaluated}/{cases}`"
        )
        if dataset.dataset == "rp-gold":
            lines.append(
                f"- RP Gold：{summary}；Forbidden@5 "
                f"`{_metric(metrics.get('forbidden_hit_rate'))}`。"
                "Forbidden 污染仍明显，且 Gold 尚未完成双人审核，因此当前结果不足以作为发布质量门禁。"
            )
        elif dataset.dataset == "longmemeval-s":
            lines.append(
                f"- LongMemEval-S：{summary}；未计分 `{unscored}` 题均因上游缺少 turn 级 "
                "`has_answer`，不以猜测 evidence 补齐。该数据集适合重型长记忆回归，不进入默认流程。"
            )
        else:
            lines.append(f"- {dataset.dataset}：{summary}；指标用于相对比较，不单独构成 RP 质量结论。")
    probes = {probe.capability: probe for probe in suite.capability_matrix.probes}
    for capability, label in (
        ("embedding", "向量召回"),
        ("planner", "Planner 扩展查询"),
        ("reranker", "rerank"),
    ):
        probe = probes.get(capability)
        if probe is None:
            lines.append(f"- {label}：没有能力探测记录，本次未验证。")
        elif probe.status.value != "executed":
            lines.append(
                f"- {label}：`{probe.status.value}`，本次未包含该路径；原因：{_cell(probe.reason)}"
            )
    return lines


def _path_details(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    lines = ["", "## 检索路径详情"]
    for path in paths:
        pipeline = path.pipeline
        lines.extend((
            "",
            f"### `{path.path_id}`",
            "",
            f"- 状态：`{path.status.value}`",
            f"- 原因：{_cell(path.reason)}",
            f"- Pipeline：`{_cell(pipeline.arrow)}`",
            f"- 候选 K：vector `{pipeline.vector_candidate_k}`，keyword `{pipeline.keyword_candidate_k}`，rerank `{pipeline.rerank_candidate_k}`，最终 `{pipeline.top_k}`",
            f"- Tokenizer：`{pipeline.keyword_tokenizer}`；raw-md：`{pipeline.raw_md_mode}`（min `{pipeline.raw_md_min_results}`）",
            f"- 权重：`{', '.join(f'{key}={value:g}' for key, value in pipeline.weights)}`",
            f"- 扩展查询用途：{_cell(pipeline.expanded_query_effect)}",
            f"- 耗时：`{path.duration_seconds:.3f}s`",
        ))
        if pipeline.providers:
            lines.extend(("", "Provider：", ""))
            for provider in pipeline.providers:
                lines.append(
                    f"- `{provider.capability}`：biz `{provider.biz_key}`，provider `{provider.provider_key}`，backend `{provider.backend}`，model `{provider.model}`，dimension `{provider.dimension if provider.dimension is not None else '-'}`"
                )
        for dataset in path.datasets:
            source_summary = _source_summary(dataset.metrics.get("planner_source_counts", {}))
            lines.extend((
                "",
                f"- 数据集 `{_cell(dataset.dataset)}`：来源 `{_cell(dataset.source_path)}`；耗时 `{dataset.duration_seconds:.3f}s`",
                f"- Planner 活动：来源 `{_cell(source_summary)}`；使用扩展查询 `{dataset.metrics.get('expanded_query_cases', 0)}/{dataset.metrics.get('planner_trace_cases', 0)}`；变体 `{dataset.metrics.get('expanded_query_total', 0)}`",
            ))
            lines.extend(_dataset_failures(dataset))
    return lines


def _planner_activity(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    rows: list[str] = []
    for path in paths:
        for dataset in path.datasets:
            metrics = dataset.metrics
            rows.append(
                "| `{path}` | {dataset} | `{sources}` | {expanded}/{traces} | {total} | {effect} |".format(
                    path=_cell(path.path_id),
                    dataset=_cell(dataset.dataset),
                    sources=_cell(_source_summary(metrics.get("planner_source_counts", {}))),
                    expanded=metrics.get("expanded_query_cases", 0),
                    traces=metrics.get("planner_trace_cases", 0),
                    total=metrics.get("expanded_query_total", 0),
                    effect=_cell(path.pipeline.expanded_query_effect),
                )
            )
    if not rows:
        return []
    return [
        "",
        "## Planner 与查询扩展活动",
        "",
        "| 路径 | 数据集 | Planner 来源 | 使用扩展的题目 | 变体数 | 扩展用途 |",
        "|---|---|---|---:|---:|---|",
        *rows,
    ]


def _source_summary(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in sorted(value.items())) or "-"
    return str(value)


def _dataset_failures(dataset: DatasetResult) -> list[str]:
    problematic = [case for case in dataset.cases if case.issues]
    lines = [
        "",
        f"#### {dataset.dataset}：失败、部分命中与污染（{len(problematic)}/{len(dataset.cases)}）",
        "",
    ]
    if not problematic:
        lines.append("没有失败、部分命中、未计分或 forbidden 污染案例。")
        return lines
    for case in problematic:
        lines.extend(_case_detail(case))
    return lines


def _case_detail(case: CaseResult) -> list[str]:
    summary = f"{case.question_id or case.sample_id} — {', '.join(case.issues)}"
    lines = [
        "<details>",
        f"<summary>{_cell(summary)}</summary>",
        "",
        f"- 问题：{_cell(case.question)}",
        f"- 分类：`{_cell(case.category or '-')}`",
        f"- Gold：`{', '.join(case.gold_evidence) or '-'}`",
        f"- Forbidden：`{', '.join(case.forbidden_evidence) or '-'}`",
    ]
    trace = case.planner_trace
    if trace is not None:
        lines.extend((
            f"- Planner：`{trace.planner_source}`",
            f"- 规范化查询：`{_cell(trace.normalized_query)}`",
            f"- 关键词查询：`{_cell(' | '.join(trace.keyword_queries) or '-')}`",
            f"- 扩展查询：`{_cell(' | '.join(trace.expanded_queries) or '-')}`",
            f"- Raw terms：`{_cell(' | '.join(trace.raw_md_terms) or '-')}`",
            f"- 扩展用途：{_cell(trace.expanded_query_effect)}",
        ))
    lines.extend((
        "",
        "| 排名 | Evidence | Final | Vector | Keyword | Raw | Exact | Fuzzy | Expanded | Granularity | Hybrid | Rerank | 预览 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ))
    if not case.rankings:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | 无结果 |")
    for ranked in case.rankings:
        scores = dict(ranked.scores)
        lines.append(
            "| {rank} | `{evidence}` | {final} | {vector} | {keyword} | {raw} | {exact} | {fuzzy} | {expanded} | {granularity} | {hybrid} | {rerank} | {preview} |".format(
                rank=ranked.rank,
                evidence=_cell(ranked.evidence_id or "-"),
                final=_score(ranked.final_score),
                vector=_score(scores.get("vector")),
                keyword=_score(scores.get("keyword")),
                raw=_score(scores.get("raw_md")),
                exact=_score(scores.get("exact")),
                fuzzy=_score(scores.get("fuzzy")),
                expanded=_score(scores.get("expanded")),
                granularity=_score(scores.get("granularity")),
                hybrid=_score(scores.get("hybrid")),
                rerank=_score(scores.get("rerank")),
                preview=_cell(ranked.text_preview),
            )
        )
    lines.extend(("", "</details>", ""))
    return lines


def _gold_issue_summary(paths: tuple[BenchmarkPathResult, ...]) -> list[tuple[str, list[str]]]:
    summary: list[tuple[str, list[str]]] = []
    for path in paths:
        ids = sorted({
            case.question_id
            for dataset in path.datasets
            if dataset.dataset == "rp-gold"
            for case in dataset.cases
            if case.issues
        })
        if ids:
            summary.append((path.path_id, ids))
    return summary


def _glossary_section() -> list[str]:
    return [
        "",
        "## 名词解释",
        "",
        "| 名词 | 解释 |",
        "|---|---|",
        *(f"| {term} | {description} |" for term, description in GLOSSARY),
    ]


def _metric(value: object) -> str:
    if value is None or value == "-":
        return "-"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return _cell(str(value))


def _score(value: float | None) -> str:
    return "-" if value is None else f"{float(value):.6f}"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _safe_service_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if not parsed.scheme or not parsed.hostname:
            return "invalid"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        return "invalid"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
