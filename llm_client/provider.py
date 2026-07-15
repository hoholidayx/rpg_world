"""Provider-shaped facade over :mod:`llm_client.client`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from llm_client.client import LLMServiceClient
from llm_client.types import (
    DocumentScore,
    DocumentScoreProvider,
    LLMBizCatalog,
    LLMProvider,
    LLMResponse,
    ProviderChunk,
)


class RemoteLLMProvider(LLMProvider, DocumentScoreProvider):
    """A lightweight immutable handle for one server-side biz route."""

    def __init__(
        self,
        *,
        client: LLMServiceClient,
        catalog: LLMBizCatalog,
        provider_key: str | None = None,
    ) -> None:
        self._client = client
        self.biz_key = catalog.biz_key
        self.provider_key = provider_key or catalog.default_provider_key
        self.kind = catalog.kind
        self._option = catalog.option(self.provider_key)
        self._dimension: int | None = None

    def get_default_model(self) -> str:
        return self._option.model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        return await self._client.chat(
            biz_key=self.biz_key,
            provider_key=self.provider_key,
            messages=messages,
            tools=tools,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        async for chunk in self._client.chat_stream(
            biz_key=self.biz_key,
            provider_key=self.provider_key,
            messages=messages,
            tools=tools,
        ):
            yield chunk

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_sync, texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed(
            biz_key=self.biz_key,
            provider_key=self.provider_key,
            texts=texts,
        )

    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = self._client.embedding_dimension(
                biz_key=self.biz_key,
                provider_key=self.provider_key,
            )
        return self._dimension

    async def score_documents(
        self,
        query: str,
        documents: list[str],
    ) -> list[DocumentScore]:
        return await self._client.rerank(
            biz_key=self.biz_key,
            provider_key=self.provider_key,
            query=query,
            documents=documents,
        )
