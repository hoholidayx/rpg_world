"""Process-local cache of remote LLM provider handles."""

from __future__ import annotations

import os
from threading import RLock
from typing import ClassVar

from llm_client.client import LLMServiceClient
from llm_client.provider import RemoteLLMProvider
from llm_client.types import LLMBizCatalog


class LLMClientManager:
    _instance: ClassVar["LLMClientManager | None"] = None
    _instance_lock: ClassVar[RLock] = RLock()

    def __init__(self, client: LLMServiceClient | None = None) -> None:
        self.client = client or LLMServiceClient(
            base_url=os.environ.get("RPG_WORLD_LLM_SERVICE_URL", "http://127.0.0.1:8012/llm/v1"),
            token=os.environ.get("RPG_WORLD_LLM_SERVICE_TOKEN", ""),
        )
        self._catalogs: dict[str, LLMBizCatalog] = {}
        self._providers: dict[tuple[str, str], RemoteLLMProvider] = {}
        self._lock = RLock()

    @classmethod
    def get(cls) -> "LLMClientManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def configure(
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
            previous.client.close()
        return manager

    @classmethod
    def set_for_tests(cls, manager: "LLMClientManager | None") -> None:
        with cls._instance_lock:
            cls._instance = manager

    @classmethod
    def reset(cls) -> None:
        with cls._instance_lock:
            previous = cls._instance
            cls._instance = None
        if previous is not None:
            previous.client.close()

    def get_catalog(self, biz_key: str, *, refresh: bool = False) -> LLMBizCatalog:
        with self._lock:
            if not refresh and biz_key in self._catalogs:
                return self._catalogs[biz_key]
        catalog = self.client.get_catalog(biz_key)
        with self._lock:
            self._catalogs[biz_key] = catalog
        return catalog

    def get_provider(
        self,
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> RemoteLLMProvider:
        catalog = self.get_catalog(biz_key)
        selected = provider_key or catalog.default_provider_key
        key = (biz_key, selected)
        with self._lock:
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
