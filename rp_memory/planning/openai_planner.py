"""OpenAI-compatible query planner for memory retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rp_memory.asyncio_utils import run_awaitable_sync
from rp_memory.planning.planner import (
    BaseQueryPlanner,
    _build_prompt,
    _parse_json_object,
    _plan_from_mapping,
)

if TYPE_CHECKING:
    from llm_service.base_provider import LLMProvider


class OpenAIQueryPlanner(BaseQueryPlanner):
    """Plan memory queries with an OpenAI-compatible chat model.

    Uses an ``LLMProvider`` obtained from ``LLMManager`` — no raw client.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_planner: BaseQueryPlanner | None = None,
    ) -> None:
        self._provider = provider
        self._fallback_planner = fallback_planner

    def plan(self, query: str):
        return run_awaitable_sync(self._plan_async(query))

    async def _plan_async(self, query: str):
        normalized = query.strip()
        if not normalized:
            return _plan_from_mapping(
                query,
                "",
                {},
                planner_source="openai",
                fallback_planner=self._fallback_planner,
            )
        prompt = _build_prompt(normalized)
        response = await self._provider.chat(
            [
                {"role": "system", "content": "You are a memory query planner."},
                {"role": "user", "content": prompt},
            ]
        )
        data = _parse_json_object(response.content)
        return _plan_from_mapping(
            query,
            normalized,
            data,
            planner_source="openai",
            fallback_planner=self._fallback_planner,
        )
