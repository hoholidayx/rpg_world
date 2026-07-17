"""Safe LLM-service capability discovery for configured benchmark paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from llm_client.client import (
    LLMServiceRemoteError,
    LLMServiceTimeout,
    LLMServiceUnavailable,
)
from llm_client.keys import (
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
)
from llm_client.manager import LLMClientManager
from rp_memory.benchmark.models import (
    BenchmarkStatus,
    CapabilityMatrix,
    CapabilityProbe,
    ProviderInfo,
)
from rp_memory.planning.openai_planner import OpenAIQueryPlanner
from rp_memory.planning.planner import RuleBasedQueryPlanner
from rp_memory.recall_query import RecallQueryContext


@dataclass(frozen=True)
class DetectedCapabilities:
    matrix: CapabilityMatrix
    handles: dict[tuple[str, str], object]

    def handle(self, capability: str, provider_key: str) -> object:
        return self.handles[(capability, provider_key)]


async def detect_capabilities(
    memory_settings,
    *,
    manager: LLMClientManager | None = None,
    offline_only: bool = False,
) -> DetectedCapabilities:
    """Probe only public LLM-client APIs; never read provider YAML or secrets."""
    enabled = {
        "embedding": bool(memory_settings.enabled),
        "planner": bool(memory_settings.enabled and memory_settings.query_planner_enabled),
        "reranker": bool(memory_settings.enabled and memory_settings.rerank_enabled),
    }
    biz_keys = {
        "embedding": MEMORY_EMBED_BIZ_KEY,
        "planner": MEMORY_QUERY_PLANNER_BIZ_KEY,
        "reranker": MEMORY_RERANK_BIZ_KEY,
    }
    if offline_only:
        probes = tuple(
            CapabilityProbe(
                capability=capability,
                status=BenchmarkStatus.SKIPPED_DISABLED,
                reason="--offline-only disables configured-provider probes and execution",
            )
            for capability in biz_keys
        )
        return DetectedCapabilities(
            CapabilityMatrix(
                service_status=BenchmarkStatus.SKIPPED_DISABLED,
                service_reason="configured LLM service intentionally not contacted",
                probes=probes,
            ),
            {},
        )

    disabled_probes = [
        CapabilityProbe(
            capability=capability,
            status=BenchmarkStatus.SKIPPED_DISABLED,
            reason=(
                "memory.enabled is false"
                if not memory_settings.enabled
                else f"memory.{_enabled_field(capability)} is false"
            ),
        )
        for capability, is_enabled in enabled.items()
        if not is_enabled
    ]
    active = [capability for capability, is_enabled in enabled.items() if is_enabled]
    if not active:
        return DetectedCapabilities(
            CapabilityMatrix(
                service_status=BenchmarkStatus.SKIPPED_DISABLED,
                service_reason="all configured memory capabilities are disabled",
                probes=tuple(disabled_probes),
            ),
            {},
        )

    resolved_manager = manager or LLMClientManager.get()
    try:
        health = await resolved_manager.client.health()
        if str(health.get("status", "")).lower() != "ok" or not bool(
            health.get("configLoaded", health.get("config_loaded", False))
        ):
            raise RuntimeError("LLM service health is not ready with loaded configuration")
    except Exception as exc:
        status = _status_for_exception(exc)
        probes = [*disabled_probes]
        probes.extend(
            CapabilityProbe(
                capability=capability,
                status=status,
                reason=_safe_reason(exc),
            )
            for capability in active
        )
        return DetectedCapabilities(
            CapabilityMatrix(status, _safe_reason(exc), tuple(probes)),
            {},
        )

    probes = [*disabled_probes]
    handles: dict[tuple[str, str], object] = {}
    for capability in active:
        biz_key = biz_keys[capability]
        try:
            catalog = await resolved_manager.get_catalog(biz_key, refresh=True)
        except Exception as exc:
            probes.append(
                CapabilityProbe(
                    capability=capability,
                    status=_status_for_exception(exc),
                    reason=_safe_reason(exc),
                )
            )
            continue
        if not catalog.options:
            probes.append(
                CapabilityProbe(
                    capability=capability,
                    status=BenchmarkStatus.SKIPPED_UNCONFIGURED,
                    reason=f"{biz_key} catalog has no provider options",
                )
            )
            continue
        for option in catalog.options:
            provider_info = ProviderInfo(
                capability=capability,
                biz_key=biz_key,
                provider_key=option.provider_key,
                backend=option.backend,
                model=option.model,
                is_default=option.provider_key == catalog.default_provider_key,
            )
            if not option.model.strip():
                probes.append(
                    CapabilityProbe(
                        capability=capability,
                        provider=provider_info,
                        status=BenchmarkStatus.SKIPPED_UNCONFIGURED,
                        reason="provider model/path is empty",
                    )
                )
                continue
            try:
                provider = await resolved_manager.get_provider(
                    biz_key,
                    provider_key=option.provider_key,
                )
                dimension = await _probe_provider(capability, provider)
                if dimension is not None:
                    provider_info = replace(provider_info, dimension=dimension)
            except Exception as exc:
                probes.append(
                    CapabilityProbe(
                        capability=capability,
                        provider=provider_info,
                        status=_status_for_exception(exc),
                        reason=_safe_reason(exc),
                    )
                )
                continue
            probes.append(
                CapabilityProbe(
                    capability=capability,
                    provider=provider_info,
                    status=BenchmarkStatus.EXECUTED,
                    reason="catalog and minimal inference probe succeeded",
                )
            )
            handles[(capability, option.provider_key)] = provider

    return DetectedCapabilities(
        CapabilityMatrix(
            service_status=BenchmarkStatus.EXECUTED,
            service_reason="health endpoint reported loaded configuration",
            probes=tuple(probes),
        ),
        handles,
    )


async def _probe_provider(capability: str, provider: object) -> int | None:
    if capability == "embedding":
        dimension = int(await provider.dimension())  # type: ignore[attr-defined]
        if dimension <= 0:
            raise ValueError("embedding provider returned a non-positive dimension")
        vectors = await provider.embed(["RP memory benchmark capability probe"])  # type: ignore[attr-defined]
        if len(vectors) != 1 or len(vectors[0]) != dimension:
            raise ValueError("embedding probe shape does not match declared dimension")
        return dimension
    if capability == "planner":
        fallback = RuleBasedQueryPlanner()
        planner = OpenAIQueryPlanner(
            provider,  # type: ignore[arg-type]
            fallback_planner=fallback,
            planner_source="benchmark_probe",
        )
        plan = await planner.plan_context(
            RecallQueryContext(current_input="谁在钟楼约定会合？")
        )
        if not plan.normalized_query:
            raise ValueError("planner probe returned an empty normalized query")
        return None
    scores = await provider.score_documents(  # type: ignore[attr-defined]
        "谁在钟楼约定会合？",
        ["艾琳约定在钟楼会合。"],
    )
    if len(scores) != 1:
        raise ValueError("reranker probe returned an unexpected score count")
    _ = scores[0].clamped_score
    return None


def _enabled_field(capability: str) -> str:
    return {
        "planner": "query_planner_enabled",
        "reranker": "rerank_enabled",
        "embedding": "enabled",
    }[capability]


def _status_for_exception(exc: Exception) -> BenchmarkStatus:
    if isinstance(exc, (LLMServiceUnavailable, LLMServiceTimeout)):
        return BenchmarkStatus.SKIPPED_SERVICE_UNREACHABLE
    if isinstance(exc, LLMServiceRemoteError) and (
        exc.status_code == 404 or exc.error_code == "LLM_BIZ_NOT_FOUND"
    ):
        return BenchmarkStatus.SKIPPED_UNCONFIGURED
    return BenchmarkStatus.SKIPPED_PROBE_FAILED


def _safe_reason(exc: Exception) -> str:
    value = " ".join(str(exc or type(exc).__name__).split())[:400]
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)\S+", r"\1[REDACTED]", value)
    return value or type(exc).__name__
