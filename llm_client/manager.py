"""Process-local cache of remote LLM provider handles."""

from __future__ import annotations

import asyncio
import os
from threading import RLock
from typing import ClassVar

from llm_client.auth import resolve_llm_service_token
from llm_client.client import LLMServiceClient
from llm_client.provider import RemoteLLMProvider
from llm_client.types import LLMBizCatalog


class LLMClientManager:
    _instance: ClassVar["LLMClientManager | None"] = None
    _instance_lock: ClassVar[RLock] = RLock()

    def __init__(self, client: LLMServiceClient | None = None) -> None:
        self.client = client or LLMServiceClient(
            base_url=os.environ.get("RPG_WORLD_LLM_SERVICE_URL", "http://127.0.0.1:8012/llm/v1"),
            token=resolve_llm_service_token(),
        )
        self._catalogs: dict[str, LLMBizCatalog] = {}
        self._providers: dict[tuple[str, str], RemoteLLMProvider] = {}
        self._catalog_locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def get(cls) -> "LLMClientManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    async def aconfigure(
        cls,
        *,
        base_url: str,
        token: str,
        request_timeout_ms: int,
        stream_timeout_ms: int,
    ) -> "LLMClientManager":
        manager = cls(
            LLMServiceClient(
                base_url=base_url,
                token=token,
                request_timeout_ms=request_timeout_ms,
                stream_timeout_ms=stream_timeout_ms,
            )
        )
        with cls._instance_lock:
            previous = cls._instance
            cls._instance = manager
        if previous is not None:
            await previous.aclose()
        return manager

    @classmethod
    async def aset_for_tests(cls, manager: "LLMClientManager | None") -> None:
        with cls._instance_lock:
            previous = cls._instance
            cls._instance = manager
        if previous is not None and previous is not manager:
            await previous.aclose()

    @classmethod
    async def areset(cls) -> None:
        with cls._instance_lock:
            previous = cls._instance
            cls._instance = None
        if previous is not None:
            await previous.aclose()

    async def get_catalog(self, biz_key: str, *, refresh: bool = False) -> LLMBizCatalog:
        lock = self._catalog_lock(biz_key)
        async with lock:
            if not refresh and biz_key in self._catalogs:
                return self._catalogs[biz_key]
            catalog = await self.client.get_catalog(biz_key)
            self._catalogs[biz_key] = catalog
            return catalog

    async def get_provider(
        self,
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> RemoteLLMProvider:
        catalog = await self.get_catalog(biz_key)
        selected = provider_key or catalog.default_provider_key
        key = (biz_key, selected)
        cached = self._providers.get(key)
        if cached is not None:
            return cached
        provider = RemoteLLMProvider(
            client=self.client,
            catalog=catalog,
            provider_key=selected,
        )
        self._providers[key] = provider
        return provider

    async def aclose(self) -> None:
        await self.client.aclose()

    def _catalog_lock(self, biz_key: str) -> asyncio.Lock:
        lock = self._catalog_locks.get(biz_key)
        if lock is None:
            lock = asyncio.Lock()
            self._catalog_locks[biz_key] = lock
        return lock
