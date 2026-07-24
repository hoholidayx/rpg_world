"""RP contextual query planner backed by an OpenAI-compatible provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from memory_retrieval.planning.planner import (
    BaseQueryPlanner,
    _build_prompt,
    _parse_json_object,
    _plan_from_mapping,
    plan_from_context_mapping,
)
from memory_retrieval.query import RetrievalQuery

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

    async def plan_context(self, context: RetrievalQuery):
        if not context.text.strip():
            return await self.plan("")
        response = await self._provider.chat(
            [
                {"role": "system", "content": "You are an RP memory query planner."},
                {"role": "user", "content": _build_rp_context_prompt(context)},
            ]
        )
        data = _parse_json_object(response.content)
        return plan_from_context_mapping(
            context,
            data,
            planner_source=self._planner_source,
            fallback_planner=self._fallback_planner,
        )


def _build_rp_context_prompt(context: RetrievalQuery) -> str:
    return (
        "你是 RPG 长期记忆检索查询规划器。根据当前输入、最近两个可推进世界的 turn、"
        "玩家身份和当前场景，解决代词、角色别名与相对时间引用。\n"
        "只输出 JSON 对象，不要输出解释。\n"
        "字段：keyword_queries、expanded_queries、raw_md_terms、query_type。\n"
        "不要把传闻改写成事实，也不要假设尝试已经成功。\n\n"
        f"{context.prompt_context}"
    )
