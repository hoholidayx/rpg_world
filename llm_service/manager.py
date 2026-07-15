"""Central LLM manager.

The manager owns raw client/model caching plus provider routing.
Business code only names a ``biz_key`` and receives a fully constructed
business provider — no raw clients, no config reading, no special-casing
of embedding / rerank / planner outside this module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import RLock
from typing import ClassVar
from typing import TypeAlias

from openai import AsyncOpenAI

from llm_service.base_provider import DocumentScoreProvider, LLMProvider
from llm_service.config import BizConfig, resolve_biz_config
from llm_service.keys import (
    LLM_KIND_EMBEDDING,
    LLM_KIND_RERANK,
    PROVIDER_LLAMA,
    PROVIDER_OPENAI,
    PROVIDER_KINDS,
    RERANK_MODEL_TYPE_CHAT_POINTWISE,
    RERANK_MODEL_TYPE_QWEN3_LOGIT,
)
from llm_service.llama_provider import (
    LlamaCompletionProvider,
    LlamaEmbeddingProvider,
    LlamaLogitRerankProvider,
)
from llm_service.openai_provider import OpenAIProvider
from llm_service.runtime import (
    DirectLlamaCompletionModel,
    DirectLlamaEmbeddingModel,
    DirectLlamaRerankModel,
    reset_direct_llama_runtime,
)


ManagedProvider: TypeAlias = LLMProvider | DocumentScoreProvider


@dataclass(frozen=True)
class OpenAIClientCacheKey:
    scope: str
    api_key: str
    base_url: str
    http_client_id: int = 0


@dataclass(frozen=True)
class LlamaCompletionModelCacheKey:
    scope: str
    model_path: str
    n_ctx: int
    n_gpu_layers: int
    request_timeout_ms: int


@dataclass(frozen=True)
class LlamaEmbeddingModelCacheKey:
    scope: str
    model_path: str
    n_ctx: int
    n_gpu_layers: int
    n_threads: int
    verbose: bool
    request_timeout_ms: int


@dataclass(frozen=True)
class LlamaRerankModelCacheKey:
    scope: str
    model_path: str
    n_ctx: int
    n_gpu_layers: int
    verbose: bool
    request_timeout_ms: int


class LLMManager:
    """Per-process LLM factory and cache."""

    _instance: ClassVar[LLMManager | None] = None
    _instance_lock: ClassVar[RLock] = RLock()

    def __init__(self) -> None:
        self._openai_client_cache: dict[OpenAIClientCacheKey, AsyncOpenAI] = {}
        self._llama_completion_model_cache: dict[LlamaCompletionModelCacheKey, DirectLlamaCompletionModel] = {}
        self._llama_embedding_model_cache: dict[LlamaEmbeddingModelCacheKey, DirectLlamaEmbeddingModel] = {}
        self._llama_rerank_model_cache: dict[LlamaRerankModelCacheKey, DirectLlamaRerankModel] = {}
        self._provider_cache: dict[tuple[str, str], ManagedProvider] = {}
        self._lock = RLock()

    @classmethod
    def get(cls) -> LLMManager:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._instance_lock:
            cls._instance = None
        reset_direct_llama_runtime()

    @classmethod
    async def areset(cls) -> None:
        with cls._instance_lock:
            previous = cls._instance
            cls._instance = None
        if previous is not None:
            await previous.aclose()
        reset_direct_llama_runtime()

    async def aclose(self) -> None:
        with self._lock:
            clients = tuple(self._openai_client_cache.values())
            self._openai_client_cache.clear()
            self._provider_cache.clear()
            self._llama_completion_model_cache.clear()
            self._llama_embedding_model_cache.clear()
            self._llama_rerank_model_cache.clear()
        if clients:
            await asyncio.gather(*(client.close() for client in clients))

    # ------------------------------------------------------------------
    # Raw client/model builders (private — only called internally)
    # ------------------------------------------------------------------

    def _build_openai_client(
        self,
        *,
        scope: str,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client: object | None = None,
    ) -> AsyncOpenAI:
        key = OpenAIClientCacheKey(
            scope=scope,
            api_key=api_key or "",
            base_url=base_url or "",
            http_client_id=id(http_client) if http_client is not None else 0,
        )
        with self._lock:
            cached = self._openai_client_cache.get(key)
            if cached is not None:
                return cached
            client_kwargs: dict[str, object] = {
                "api_key": api_key,
                "base_url": base_url,
            }
            if http_client is not None:
                client_kwargs["http_client"] = http_client
            client = AsyncOpenAI(**client_kwargs)
            self._openai_client_cache[key] = client
            return client

    def _build_llama_completion_model(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        request_timeout_ms: int = 60000,
    ) -> DirectLlamaCompletionModel:
        key = LlamaCompletionModelCacheKey(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            request_timeout_ms=request_timeout_ms,
        )
        with self._lock:
            cached = self._llama_completion_model_cache.get(key)
            if cached is not None:
                return cached
            model = DirectLlamaCompletionModel(
                model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                request_timeout_ms=request_timeout_ms,
            )
            self._llama_completion_model_cache[key] = model
            return model

    def _build_llama_embedding_model(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
    ) -> DirectLlamaEmbeddingModel:
        key = LlamaEmbeddingModelCacheKey(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        with self._lock:
            cached = self._llama_embedding_model_cache.get(key)
            if cached is not None:
                return cached
            model = DirectLlamaEmbeddingModel(
                model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                n_threads=n_threads,
                verbose=verbose,
                request_timeout_ms=request_timeout_ms,
            )
            self._llama_embedding_model_cache[key] = model
            return model

    def _build_llama_rerank_model(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
    ) -> DirectLlamaRerankModel:
        key = LlamaRerankModelCacheKey(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        with self._lock:
            cached = self._llama_rerank_model_cache.get(key)
            if cached is not None:
                return cached
            model = DirectLlamaRerankModel(
                model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=verbose,
                request_timeout_ms=request_timeout_ms,
            )
            self._llama_rerank_model_cache[key] = model
            return model

    # ------------------------------------------------------------------
    # Provider builder helpers (private)
    # ------------------------------------------------------------------

    def _build_openai_provider(
        self,
        *,
        scope: str,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> OpenAIProvider:
        client = self._build_openai_client(scope=scope, api_key=api_key, base_url=base_url)
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            client=client,
        )

    def _build_llama_provider(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        request_timeout_ms: int = 60000,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> LlamaCompletionProvider:
        model = self._build_llama_completion_model(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            request_timeout_ms=request_timeout_ms,
        )
        return LlamaCompletionProvider(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            request_timeout_ms=request_timeout_ms,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )

    def _build_llama_embedding_provider(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
    ) -> LlamaEmbeddingProvider:
        model = self._build_llama_embedding_model(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        return LlamaEmbeddingProvider(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
            model=model,
        )

    def _build_llama_logit_rerank_provider(
        self,
        *,
        scope: str,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        max_length: int | None = None,
    ) -> LlamaLogitRerankProvider:
        model = self._build_llama_rerank_model(
            scope=scope,
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        return LlamaLogitRerankProvider(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
            max_length=max_length,
            model=model,
        )

    # ------------------------------------------------------------------
    # Public — single entry point
    # ------------------------------------------------------------------

    def get_provider(
        self,
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> ManagedProvider:
        """Return a fully constructed provider for *biz_key*.

        This is the **only** public method business code should call.
        Config lives in ``llm_service/llm.yaml``; provider differences (OpenAI /
        llama / chat / embedding / rerank) are handled internally.
        """
        with self._lock:
            cfg = self._resolve_cfg(biz_key, provider_key=provider_key)
            cache_key = (biz_key, cfg.provider_key)
            cached = self._provider_cache.get(cache_key)
            if cached is not None:
                return cached
            provider = self._build_provider(cfg, biz_key)
            self._provider_cache[cache_key] = provider
            return provider

    # ------------------------------------------------------------------
    # Unified provider construction
    # ------------------------------------------------------------------

    def _build_provider(
        self,
        cfg: BizConfig,
        biz_key: str,
    ) -> ManagedProvider:
        backend = cfg.provider

        if backend not in PROVIDER_KINDS:
            raise ValueError(
                f"{biz_key} config invalid: provider must be "
                f"{sorted(PROVIDER_KINDS)}, got {backend!r}"
            )

        if cfg.kind == LLM_KIND_EMBEDDING:
            return self._build_embedding_provider(cfg, biz_key, backend)
        if cfg.kind == LLM_KIND_RERANK:
            return self._build_rerank_provider(cfg, biz_key, backend)

        # Chat and planner use the same provider construction path.
        return self._build_chat_provider_inner(cfg, biz_key, backend)

    def _build_chat_provider_inner(
        self,
        cfg: BizConfig,
        biz_key: str,
        backend: str,
    ) -> LLMProvider:
        if backend == PROVIDER_OPENAI:
            return self._build_openai_provider(
                scope=cfg.provider_key,
                model=cfg.openai_model,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                max_tokens=cfg.openai_max_tokens,
                temperature=cfg.openai_temperature,
            )
        if backend == PROVIDER_LLAMA:
            return self._build_llama_provider(
                scope=cfg.provider_key,
                model_path=cfg.llama_model_path,
                n_ctx=cfg.llama_n_ctx,
                n_gpu_layers=cfg.llama_n_gpu_layers,
                request_timeout_ms=cfg.llama_request_timeout_ms,
                max_tokens=cfg.llama_max_tokens,
                temperature=cfg.llama_temperature,
            )
        raise ValueError(f"{biz_key} config invalid: unsupported backend {backend!r}")

    def _build_embedding_provider(
        self,
        cfg: BizConfig,
        biz_key: str,
        backend: str,
    ) -> LLMProvider:
        if backend == PROVIDER_OPENAI:
            return self._build_openai_provider(
                scope=cfg.provider_key,
                model=cfg.openai_model,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
            )
        if backend == PROVIDER_LLAMA:
            return self._build_llama_embedding_provider(
                scope=cfg.provider_key,
                model_path=cfg.llama_model_path,
                n_ctx=cfg.llama_n_ctx,
                n_gpu_layers=cfg.llama_n_gpu_layers,
                n_threads=cfg.llama_n_threads,
                verbose=cfg.llama_verbose,
                request_timeout_ms=cfg.llama_request_timeout_ms,
            )
        raise ValueError(f"{biz_key} config invalid: unsupported backend {backend!r}")

    def _build_rerank_provider(
        self,
        cfg: BizConfig,
        biz_key: str,
        backend: str,
    ) -> ManagedProvider:
        rerank_model_type = cfg.rerank_model_type
        if rerank_model_type == RERANK_MODEL_TYPE_CHAT_POINTWISE:
            if backend != PROVIDER_OPENAI:
                raise ValueError(
                    f"{biz_key} config invalid: rerank_model_type={rerank_model_type!r} requires provider={PROVIDER_OPENAI!r}"
                )
            return self._build_openai_provider(
                scope=cfg.provider_key,
                model=cfg.openai_model,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                max_tokens=cfg.openai_max_tokens,
                temperature=cfg.openai_temperature,
            )
        if rerank_model_type == RERANK_MODEL_TYPE_QWEN3_LOGIT:
            if backend != PROVIDER_LLAMA:
                raise ValueError(
                    f"{biz_key} config invalid: rerank_model_type={rerank_model_type!r} requires provider={PROVIDER_LLAMA!r}"
                )
            return self._build_llama_logit_rerank_provider(
                scope=cfg.provider_key,
                model_path=cfg.llama_model_path,
                n_ctx=cfg.llama_n_ctx,
                n_gpu_layers=cfg.llama_n_gpu_layers,
                verbose=cfg.llama_verbose,
                request_timeout_ms=cfg.llama_request_timeout_ms,
                max_length=cfg.llama_max_length,
            )
        raise ValueError(f"{biz_key} config invalid: unsupported rerank_model_type {rerank_model_type!r}")

    @staticmethod
    def _resolve_cfg(
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> BizConfig:
        if provider_key is None:
            return resolve_biz_config(biz_key)
        return resolve_biz_config(biz_key, provider_key=provider_key)
