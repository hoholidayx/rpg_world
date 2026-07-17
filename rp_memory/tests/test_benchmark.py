from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from llm_client.client import LLMServiceUnavailable
from llm_client.keys import (
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
)
from llm_client.types import (
    DocumentScore,
    LLMBizCatalog,
    LLMProviderOption,
    LLMResponse,
)
from rp_memory.benchmark import locomo, longmemeval
from rp_memory.benchmark.capabilities import DetectedCapabilities, detect_capabilities
from rp_memory.benchmark.datasets import parse_datasets
from rp_memory.benchmark.metrics import evaluate_rankings, evaluate_rp_rankings
from rp_memory.benchmark.models import (
    BenchmarkEnvironment,
    BenchmarkPathResult,
    BenchmarkStatus,
    CapabilityMatrix,
    CapabilityProbe,
    DatasetResult,
    PipelineDescription,
    ProviderInfo,
    SuiteResult,
)
from rp_memory.benchmark.report import record_summary, render_full_report
from rp_memory.benchmark.rp_gold import RP_GOLD_CATEGORIES, load_rp_gold
from rp_memory.benchmark.runner import (
    build_path_specs,
    load_jsonl_dataset,
    run_benchmark_paths,
)
from rpg_core.settings import MemorySettings


def test_recall_metrics_cover_rank_and_no_answer_cases() -> None:
    metrics = evaluate_rankings(
        [
            (["D1:3"], ["D1:1", "D1:3"]),
            (["D2:2", "D2:4"], ["D2:4", "D9:1"]),
            ([], []),
        ],
        top_k=2,
        unscored_cases=2,
    )

    assert metrics.recall_at_k == 1.0
    assert metrics.hit_at_1 == pytest.approx(0.5)
    assert metrics.mrr == pytest.approx(0.75)
    assert metrics.evidence_coverage == pytest.approx(0.75)
    assert metrics.cases == 5
    assert metrics.evaluated_cases == 3
    assert metrics.answerable_cases == 2
    assert metrics.no_answer_cases == 1
    assert metrics.unscored_cases == 2
    assert metrics.no_answer_accuracy == 1.0

    answerable_only = evaluate_rankings([(["D1"], ["D1"])], top_k=1)
    assert answerable_only.no_answer_cases == 0
    assert answerable_only.no_answer_accuracy is None


def test_rp_gold_cases_are_valid_and_track_forbidden_hits() -> None:
    samples = load_rp_gold()
    question_count = sum(len(sample["questions"]) for sample in samples)
    no_answer_questions = [
        question
        for sample in samples
        for question in sample["questions"]
        if question.get("no_answer") is True
    ]
    metrics = evaluate_rp_rankings(
        [
            (["confirmed"], ["rumor"], ["rumor", "confirmed"]),
            (["success"], ["failed"], ["success"]),
        ],
        top_k=2,
    )

    category_counts = {
        category: sum(
            question["category"] == category
            for sample in samples
            for question in sample["questions"]
        )
        for category in RP_GOLD_CATEGORIES
    }

    assert len(samples) == 12
    assert question_count == 60
    assert len(no_answer_questions) == 5
    assert all(question["gold_evidence"] == [] for question in no_answer_questions)
    assert set(category_counts.values()) == {5}
    assert metrics.recall_at_k == 1.0
    assert metrics.hit_at_1 == 0.5
    assert metrics.forbidden_cases == 2
    assert metrics.forbidden_at_1_rate == 0.5
    assert metrics.forbidden_hit_rate == 0.5
    assert metrics.forbidden_before_gold_rate == 0.5


def test_dataset_selection_is_explicit_and_stable() -> None:
    assert parse_datasets(None) == ("locomo", "rp-gold")
    assert parse_datasets(["rp-gold,longmemeval-s", "rp-gold"]) == (
        "rp-gold",
        "longmemeval-s",
    )
    with pytest.raises(ValueError, match="unsupported benchmark dataset"):
        parse_datasets(["unknown"])


def test_prepare_longmemeval_validates_and_converts_turn_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "longmemeval.json"
    source.write_text(json.dumps([
        {
            "question_id": "q-1",
            "question_type": "knowledge-update",
            "question": "Where is the key now?",
            "answer": "In the drawer.",
            "question_date": "2026/01/03",
            "haystack_dates": ["2026/01/01"],
            "haystack_session_ids": ["session-1"],
            "haystack_sessions": [[
                {"role": "user", "content": "I put the key away.", "has_answer": False},
                {"role": "assistant", "content": "The key is in the drawer.", "has_answer": True},
            ]],
            "answer_session_ids": ["session-1"],
        },
        {
            "question_id": "q-2",
            "question_type": "abstention",
            "question": "What is the password?",
            "answer": "Unknown.",
            "question_date": "2026/01/04",
            "haystack_dates": ["2026/01/02"],
            "haystack_session_ids": ["session-2"],
            "haystack_sessions": [[
                {"role": "user", "content": "No password was recorded.", "has_answer": False},
            ]],
            "answer_session_ids": ["session-2"],
        },
    ]), encoding="utf-8")
    monkeypatch.setattr(longmemeval, "LONGMEMEVAL_SIZE", source.stat().st_size)
    monkeypatch.setattr(
        longmemeval,
        "LONGMEMEVAL_SHA256",
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(longmemeval, "LONGMEMEVAL_RECORDS", 2)
    monkeypatch.setattr(longmemeval, "LONGMEMEVAL_MAX_DOWNLOAD_BYTES", 1024 * 1024)

    def copy_download(_url, destination):  # noqa: ANN001
        shutil.copyfile(source, destination)

    monkeypatch.setattr(longmemeval, "_download", copy_download)
    paths = longmemeval.prepare_longmemeval(tmp_path / "cache")
    converted = [
        json.loads(line)
        for line in paths["full"].read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert converted[0]["documents"][1]["id"] == "session-1:s1:t2"
    assert converted[0]["questions"][0]["evidence"] == ["session-1:s1:t2"]
    assert converted[1]["questions"][0]["evidence"] == []
    assert manifest["records"] == 2
    assert manifest["unscored_missing_has_answer"] == 1


def test_longmemeval_download_rejects_declared_oversize(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(longmemeval, "LONGMEMEVAL_SIZE", 200)
    monkeypatch.setattr(longmemeval, "LONGMEMEVAL_MAX_DOWNLOAD_BYTES", 100)

    with pytest.raises(ValueError, match="expected size exceeds"):
        longmemeval._download("https://example.invalid/data.json", tmp_path / "data.json")


def test_prepare_locomo_validates_and_builds_deterministic_smoke_subset(
    tmp_path,
    monkeypatch,
) -> None:
    qa_counts = [199] * 6 + [198] * 4
    samples = []
    for sample_index, qa_count in enumerate(qa_counts, start=1):
        samples.append({
            "sample_id": f"sample-{sample_index}",
            "conversation": {
                "speaker_a": "A",
                "speaker_b": "B",
                "session_1_date_time": "1 Jan 2024",
                "session_1": [{
                    "speaker": "A",
                    "dia_id": f"D{sample_index}:1",
                    "text": "A frozen fact",
                }],
            },
            "qa": [
                {
                    "question": "What happened?",
                    "answer": "A frozen fact",
                    "evidence": [f"D{sample_index}:1"],
                    "category": 1,
                }
                for _ in range(qa_count)
            ],
        })
    source = tmp_path / "source.json"
    source.write_text(json.dumps(samples), encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(locomo, "LOCOMO_SIZE", source.stat().st_size)
    monkeypatch.setattr(locomo, "LOCOMO_SHA256", digest)

    def copy_download(_url, destination):  # noqa: ANN001
        shutil.copyfile(source, destination)

    monkeypatch.setattr(locomo, "_download", copy_download)
    paths = locomo.prepare_locomo(tmp_path / "cache")

    assert len(paths["full"].read_text(encoding="utf-8").splitlines()) == 10
    smoke = [json.loads(line) for line in paths["smoke"].read_text(encoding="utf-8").splitlines()]
    assert len(smoke) == 1
    assert smoke[0]["sample_id"] == "sample-1"
    assert smoke[0]["documents"][0]["id"] == "D1:1"
    assert len(smoke[0]["questions"]) == 199


def test_prepare_locomo_uses_valid_cache_without_network(tmp_path, monkeypatch) -> None:
    source = _locomo_source(tmp_path)
    _patch_locomo_integrity(monkeypatch, source)
    cache = tmp_path / "cache"
    cache.mkdir()
    raw_path = cache / f"locomo10.{locomo.LOCOMO_COMMIT[:8]}.json"
    shutil.copyfile(source, raw_path)

    def unexpected_download(_url, _destination):  # noqa: ANN001
        raise AssertionError("valid LoCoMo cache must not use the network")

    monkeypatch.setattr(locomo, "_download", unexpected_download)
    paths = locomo.prepare_locomo(cache)

    assert paths["raw"] == raw_path
    assert paths["full"].is_file()
    assert paths["smoke"].is_file()


def test_locomo_download_retries_and_publishes_only_verified_file(
    tmp_path,
    monkeypatch,
) -> None:
    source = _locomo_source(tmp_path)
    _patch_locomo_integrity(monkeypatch, source)
    monkeypatch.setattr(locomo.time, "sleep", lambda _seconds: None)
    attempts = 0

    def flaky_download(_url: str, temporary: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("temporary network failure")
        shutil.copyfile(source, temporary)

    monkeypatch.setattr(locomo, "_download_once", flaky_download)
    destination = tmp_path / "downloaded.json"
    locomo._download("https://example.invalid/locomo.json", destination)

    assert attempts == 2
    assert destination.read_bytes() == source.read_bytes()
    assert not list(tmp_path.glob("*.part"))


def test_locomo_download_rejects_corrupt_artifact_without_partial_publish(
    tmp_path,
    monkeypatch,
) -> None:
    source = _locomo_source(tmp_path)
    _patch_locomo_integrity(monkeypatch, source)
    monkeypatch.setattr(locomo.time, "sleep", lambda _seconds: None)

    def corrupt_download(_url: str, temporary: Path) -> None:
        temporary.write_bytes(b"corrupt")

    monkeypatch.setattr(locomo, "_download_once", corrupt_download)
    destination = tmp_path / "downloaded.json"

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        locomo._download("https://example.invalid/locomo.json", destination)

    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.asyncio
async def test_capability_detection_probes_all_enabled_provider_paths() -> None:
    embedding = _EmbeddingProvider()
    planner = _PlannerProvider()
    reranker = _RerankProvider()
    manager = _FakeManager(
        providers={
            MEMORY_EMBED_BIZ_KEY: embedding,
            MEMORY_QUERY_PLANNER_BIZ_KEY: planner,
            MEMORY_RERANK_BIZ_KEY: reranker,
        }
    )

    detected = await detect_capabilities(
        MemorySettings(
            enabled=True,
            query_planner_enabled=True,
            rerank_enabled=True,
        ),
        manager=manager,  # type: ignore[arg-type]
    )

    assert detected.matrix.service_status is BenchmarkStatus.EXECUTED
    assert {
        (probe.capability, probe.status)
        for probe in detected.matrix.probes
    } == {
        ("embedding", BenchmarkStatus.EXECUTED),
        ("planner", BenchmarkStatus.EXECUTED),
        ("reranker", BenchmarkStatus.EXECUTED),
    }
    assert detected.matrix.default("embedding").provider.dimension == 2  # type: ignore[union-attr]
    assert detected.handle("embedding", "fake") is embedding
    assert detected.handle("planner", "fake") is planner
    assert detected.handle("reranker", "fake") is reranker


@pytest.mark.asyncio
async def test_capability_detection_explains_unreachable_and_disabled_paths() -> None:
    manager = _FakeManager(service_error=LLMServiceUnavailable("connection refused"))
    detected = await detect_capabilities(
        MemorySettings(enabled=True, query_planner_enabled=False, rerank_enabled=False),
        manager=manager,  # type: ignore[arg-type]
    )

    assert detected.matrix.service_status is BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE
    by_capability = {
        probe.capability: probe
        for probe in detected.matrix.probes
    }
    assert by_capability["embedding"].status is BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE
    assert by_capability["planner"].status is BenchmarkStatus.SKIPPED_DISABLED
    assert by_capability["reranker"].status is BenchmarkStatus.SKIPPED_DISABLED
    assert "connection refused" in by_capability["embedding"].reason


def test_path_matrix_keeps_skips_and_effective_local_fallback_explicit() -> None:
    settings = MemorySettings(
        enabled=True,
        query_planner_enabled=False,
        rerank_enabled=False,
        raw_md_mode="fallback_only",
    )
    detected = DetectedCapabilities(
        matrix=CapabilityMatrix(
            service_status=BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE,
            service_reason="connection refused",
            probes=(
                CapabilityProbe(
                    "embedding",
                    BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE,
                    "connection refused",
                ),
                CapabilityProbe(
                    "planner",
                    BenchmarkStatus.SKIPPED_DISABLED,
                    "memory.query_planner_enabled is false",
                ),
                CapabilityProbe(
                    "reranker",
                    BenchmarkStatus.SKIPPED_DISABLED,
                    "memory.rerank_enabled is false",
                ),
            ),
        ),
        handles={},
    )

    specs = {
        spec.path_id: spec
        for spec in build_path_specs(settings, detected, offline_only=False)
    }

    assert specs["offline.keyword_rule"].status is BenchmarkStatus.EXECUTED
    assert specs["offline.local_fallback"].status is BenchmarkStatus.EXECUTED
    assert specs["configured.embedding.default"].status is BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE
    assert specs["configured.planner.default"].status is BenchmarkStatus.SKIPPED_DISABLED
    assert specs["configured.rerank.default"].status is BenchmarkStatus.SKIPPED_DISABLED
    effective = specs["configured.effective"]
    assert effective.status is BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK
    assert effective.pipeline.retrievers == ("keyword", "raw-md")
    assert "embedding: connection refused" in effective.reason


@pytest.mark.asyncio
async def test_runtime_embedding_failure_is_recorded_as_degraded_fallback(
    tmp_path,
) -> None:
    dataset_path = tmp_path / "tiny.jsonl"
    dataset_path.write_text(
        json.dumps({
            "sample_id": "tiny",
            "documents": [{"id": "D1", "text": "艾琳在钟楼等待。"}],
            "questions": [{
                "id": "tiny:q1",
                "question": "谁在钟楼等待？",
                "evidence": ["D1"],
            }],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    provider = _FailingEmbeddingProvider()
    info = ProviderInfo(
        capability="embedding",
        biz_key=MEMORY_EMBED_BIZ_KEY,
        provider_key="broken",
        backend="llama_cpp",
        model="missing.gguf",
        is_default=True,
        dimension=2,
    )
    detected = DetectedCapabilities(
        matrix=CapabilityMatrix(
            service_status=BenchmarkStatus.EXECUTED,
            service_reason="ready",
            probes=(CapabilityProbe(
                "embedding",
                BenchmarkStatus.EXECUTED,
                "probe passed before runtime failure",
                info,
            ),),
        ),
        handles={("embedding", "broken"): provider},
    )

    results = await run_benchmark_paths(
        (load_jsonl_dataset(dataset_path),),
        MemorySettings(enabled=True, raw_md_mode="disabled"),
        detected,
        index_root=tmp_path / "indexes",
        offline_only=False,
    )
    by_path = {result.path_id: result for result in results}

    embedding_result = by_path["configured.embedding.broken"]
    assert embedding_result.status is BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK
    assert "embedding runtime fallback count=" in embedding_result.reason
    assert embedding_result.datasets[0].metrics["recall_at_k"] == 1.0
    assert by_path["configured.effective"].status is BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK


@pytest.mark.asyncio
async def test_equivalent_local_pipelines_keep_identical_tie_ordering(tmp_path) -> None:
    dataset_path = tmp_path / "ties.jsonl"
    dataset_path.write_text(
        json.dumps({
            "sample_id": "ties",
            "documents": [
                {"id": f"E{index}", "text": "钟楼线索"}
                for index in range(1, 8)
            ],
            "questions": [{
                "id": "ties:q1",
                "question": "钟楼线索",
                "evidence": ["E1"],
            }],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    detected = DetectedCapabilities(
        matrix=CapabilityMatrix(
            service_status=BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE,
            service_reason="connection refused",
            probes=(CapabilityProbe(
                "embedding",
                BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE,
                "connection refused",
            ),),
        ),
        handles={},
    )

    results = await run_benchmark_paths(
        (load_jsonl_dataset(dataset_path),),
        MemorySettings(enabled=True, raw_md_mode="fallback_only"),
        detected,
        index_root=tmp_path / "indexes",
        offline_only=False,
    )
    by_path = {result.path_id: result for result in results}
    local_rankings = by_path["offline.local_fallback"].datasets[0].cases[0].rankings
    effective_rankings = by_path["configured.effective"].datasets[0].cases[0].rankings

    assert [item.evidence_id for item in local_rankings] == [
        item.evidence_id for item in effective_rankings
    ]
    assert by_path["offline.local_fallback"].datasets[0].metrics == (
        by_path["configured.effective"].datasets[0].metrics
    )


def test_markdown_record_creates_independent_chinese_report_and_index(tmp_path) -> None:
    suite = _successful_suite("fixed-run-id")
    runs_dir = tmp_path / "runs"
    index_path = tmp_path / "README.md"
    report_path = tmp_path / "result.md"

    tracked_path, created = record_summary(
        suite,
        runs_dir=runs_dir,
        index_path=index_path,
        local_report_path=report_path,
    )
    duplicate_path, duplicate_created = record_summary(
        suite,
        runs_dir=runs_dir,
        index_path=index_path,
        local_report_path=report_path,
    )

    content = tracked_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    assert created is True
    assert duplicate_created is False
    assert duplicate_path == tracked_path
    assert content.count("<!-- run-id:fixed-run-id -->") == 1
    assert "# RP Memory 召回基准总结" in content
    assert "## 名词解释" in content
    assert "offline.keyword_rule" in content
    assert "0.500000" in content
    assert "服务探测：`skipped_disabled` — test" in content
    assert "`fixed-run-id`" in index
    assert "runs/rp-memory-recall-fixed-run-id.md" in index


def test_full_report_is_simplified_chinese_and_contains_glossary() -> None:
    report = render_full_report(_successful_suite("full-report"))

    assert report.startswith("# RP Memory 召回基准完整报告")
    assert "## 测试环境" in report
    assert "## 名词解释" in report
    assert "Forbidden-before-gold" in report
    assert "本次没有成功执行 embedding 检索路径" in report
    assert "不包含 embedding、LLM Planner 或 rerank 的纯离线关键词基线" in report
    assert "不能代表完整模型配置路径的质量" in report
    assert "只有对应能力状态为 `executed` 时" in report


def test_report_focuses_vector_metrics_when_embedding_path_executed() -> None:
    suite = _successful_suite("embedding-report")
    provider = ProviderInfo(
        capability="embedding",
        biz_key=MEMORY_EMBED_BIZ_KEY,
        provider_key="embedding-default",
        backend="llama_cpp",
        model="embedding.gguf",
        is_default=True,
        dimension=1024,
    )
    baseline = suite.paths[0]
    embedding_path = BenchmarkPathResult(
        path_id="configured.embedding.embedding-default",
        status=BenchmarkStatus.EXECUTED,
        reason="ready",
        pipeline=replace(
            baseline.pipeline,
            retrievers=("vector", "keyword"),
            providers=(provider,),
        ),
        datasets=baseline.datasets,
    )
    suite = replace(
        suite,
        capability_matrix=CapabilityMatrix(
            BenchmarkStatus.EXECUTED,
            "ready",
            (CapabilityProbe("embedding", BenchmarkStatus.EXECUTED, "ready", provider),),
        ),
        paths=(*suite.paths, embedding_path),
    )

    report = render_full_report(suite)

    assert "本次没有成功执行 embedding 检索路径" not in report
    assert "不能代表完整模型配置路径的质量" not in report
    assert "向量路径 `configured.embedding.embedding-default` / locomo" in report
    assert "该路径已成功执行 embedding，应以这些指标评价向量召回质量" in report


def _locomo_source(tmp_path: Path) -> Path:
    qa_counts = [199] * 6 + [198] * 4
    samples = []
    for sample_index, qa_count in enumerate(qa_counts, start=1):
        samples.append({
            "sample_id": f"sample-{sample_index}",
            "conversation": {
                "session_1_date_time": "1 Jan 2024",
                "session_1": [{
                    "speaker": "A",
                    "dia_id": f"D{sample_index}:1",
                    "text": "A frozen fact",
                }],
            },
            "qa": [
                {
                    "question": "What happened?",
                    "answer": "A frozen fact",
                    "evidence": [f"D{sample_index}:1"],
                    "category": 1,
                }
                for _ in range(qa_count)
            ],
        })
    source = tmp_path / "locomo-source.json"
    source.write_text(json.dumps(samples), encoding="utf-8")
    return source


def _patch_locomo_integrity(monkeypatch, source: Path) -> None:  # noqa: ANN001
    monkeypatch.setattr(locomo, "LOCOMO_SIZE", source.stat().st_size)
    monkeypatch.setattr(
        locomo,
        "LOCOMO_SHA256",
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )


class _FakeClient:
    def __init__(self, service_error: Exception | None = None) -> None:
        self._service_error = service_error

    async def health(self) -> dict[str, object]:
        if self._service_error is not None:
            raise self._service_error
        return {"status": "ok", "configLoaded": True}


class _FakeManager:
    def __init__(
        self,
        *,
        providers: dict[str, object] | None = None,
        service_error: Exception | None = None,
    ) -> None:
        self.client = _FakeClient(service_error)
        self._providers = providers or {}

    async def get_catalog(self, biz_key: str, *, refresh: bool = False) -> LLMBizCatalog:
        del refresh
        provider = self._providers[biz_key]
        return LLMBizCatalog(
            biz_key=biz_key,
            kind=(
                "embedding"
                if biz_key == MEMORY_EMBED_BIZ_KEY
                else "rerank"
                if biz_key == MEMORY_RERANK_BIZ_KEY
                else "chat"
            ),
            default_provider_key="fake",
            options=(LLMProviderOption(
                provider_key="fake",
                backend="test",
                model=provider.get_default_model(),  # type: ignore[attr-defined]
                context_window=4096,
            ),),
        )

    async def get_provider(
        self,
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> object:
        assert provider_key == "fake"
        return self._providers[biz_key]


class _EmbeddingProvider:
    def get_default_model(self) -> str:
        return "fake-embedding"

    async def dimension(self) -> int:
        return 2

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _FailingEmbeddingProvider(_EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("model file missing")


class _PlannerProvider:
    def get_default_model(self) -> str:
        return "fake-planner"

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        del messages, tools
        return LLMResponse(
            content=json.dumps({
                "keyword_queries": ["钟楼 会合"],
                "expanded_queries": ["艾琳 钟楼"],
                "raw_md_terms": ["钟楼"],
                "query_type": "fact",
            }),
            tool_calls=None,
            finish_reason="stop",
        )


class _RerankProvider:
    def get_default_model(self) -> str:
        return "fake-reranker"

    async def score_documents(
        self,
        query: str,
        documents: list[str],
    ) -> list[DocumentScore]:
        del query
        return [DocumentScore(0.9) for _ in documents]


def _successful_suite(run_id: str) -> SuiteResult:
    pipeline = PipelineDescription(
        planner="rule_based",
        retrievers=("keyword",),
        fusion="hybrid",
        reranker="disabled",
        top_k=5,
        vector_candidate_k=50,
        keyword_candidate_k=50,
        rerank_candidate_k=8,
        keyword_tokenizer="jieba",
        raw_md_mode="disabled",
        raw_md_min_results=0,
        weights=(("keyword", 1.0),),
        expanded_query_effect="existing-candidate scoring only",
    )
    metrics = asdict(evaluate_rankings([(["D1"], ["D2", "D1"])], top_k=5))
    return SuiteResult(
        environment=BenchmarkEnvironment(
            run_id=run_id,
            started_at_utc="2026-07-17T00:00:00Z",
            command="benchmark",
            repo_root="/repo",
            git_revision="abc123",
            git_dirty=False,
            git_status_summary="clean",
            python_version="3.12",
            sqlite_version="3",
            jieba_version="1",
            platform="test",
            paths=(),
            profile="test",
            llm_service_url="http://127.0.0.1:8012/llm/v1",
        ),
        capability_matrix=CapabilityMatrix(
            BenchmarkStatus.SKIPPED_DISABLED,
            "test",
        ),
        paths=(BenchmarkPathResult(
            path_id="offline.keyword_rule",
            status=BenchmarkStatus.EXECUTED,
            reason="test",
            pipeline=pipeline,
            datasets=(DatasetResult(
                dataset="locomo",
                source_path="/dataset",
                metrics=metrics,
                cases=(),
                duration_seconds=0.1,
            ),),
        ),),
        finished_at_utc="2026-07-17T00:00:01Z",
    )
