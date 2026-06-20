"""OpenAI-compatible query planner for memory retrieval."""

from __future__ import annotations

from openai import AsyncOpenAI

from rpg_world.rpg_core.memory.asyncio_utils import run_awaitable_sync
from rpg_world.rpg_core.memory.planning.planner import (
    BaseQueryPlanner,
    _build_prompt,
    _extract_text,
    _parse_json_object,
    _plan_from_mapping,
)


class OpenAIQueryPlanner(BaseQueryPlanner):
    """Plan memory queries with an OpenAI-compatible chat model."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        fallback_planner: BaseQueryPlanner | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._fallback_planner = fallback_planner
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

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
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a memory query planner."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        choice = response.choices[0]
        data = _parse_json_object(_extract_text(choice.message.content or ""))
        return _plan_from_mapping(
            query,
            normalized,
            data,
            planner_source="openai",
            fallback_planner=self._fallback_planner,
        )
