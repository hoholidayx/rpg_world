"""Shared LLM business keys and provider labels."""

from __future__ import annotations

AGENT_MAIN_BIZ_KEY = "agent.main"
AGENT_STATUS_SUB_AGENT_BIZ_KEY = "agent.status_sub_agent"
AGENT_MEMORY_SUB_AGENT_BIZ_KEY = "agent.memory_sub_agent"

MEMORY_EMBED_BIZ_KEY = "memory.embed"
MEMORY_QUERY_PLANNER_BIZ_KEY = "memory.query_planner"
MEMORY_RERANK_BIZ_KEY = "memory.rerank"

PROVIDER_SHARED = "shared"
PROVIDER_OPENAI = "openai"
PROVIDER_LLAMA = "llama"

PROVIDER_KINDS = frozenset({PROVIDER_SHARED, PROVIDER_OPENAI, PROVIDER_LLAMA})
