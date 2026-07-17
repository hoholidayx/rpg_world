"""OpenAI-compatible query planner for memory retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rp_memory.planning.planner import (
    BaseQueryPlanner,
    _build_prompt,
    _parse_json_object,
    _plan_from_mapping,
    build_context_prompt,
    plan_from_context_mapping,
)
from rp_memory.recall_query import RecallQueryContext

if TYPE_CHECKING:
    from llm_client.types import LLMProvider


class OpenAIQueryPlanner(BaseQueryPlanner):
    """Plan memory queries with an OpenAI-compatible chat model.

    Uses an ``LLMProvider`` obtained from ``LLMClientManager`` — no raw client.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_planner: BaseQueryPlanner | None = None,
        planner_source: str = "openai",
    ) -> None:
        self._provider = provider
        self._fallback_planner = fallback_planner
        self._planner_source = planner_source

    async def plan(self, query: str):
        normalized = query.strip()
        if not normalized:
            return _plan_from_mapping(
                query,
                "",
                {},
                planner_source=self._planner_source,
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
            planner_source=self._planner_source,
            fallback_planner=self._fallback_planner,
        )

    async def plan_context(self, context: RecallQueryContext):
        if not context.current_input.strip():
            return await self.plan("")
        response = await self._provider.chat(
            [
                {"role": "system", "content": "You are an RP memory query planner."},
                {"role": "user", "content": build_context_prompt(context)},
            ]
        )
        data = _parse_json_object(response.content)
        return plan_from_context_mapping(
            context,
            data,
            planner_source=self._planner_source,
            fallback_planner=self._fallback_planner,
        )
