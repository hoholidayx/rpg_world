"""Shared string constants used across RPG core modules."""

from __future__ import annotations

from typing import Literal

LLM_PROVIDER_SHARED = "shared"
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_LLAMA = "llama"

LLM_PROVIDER_MODES = (
    LLM_PROVIDER_SHARED,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_LLAMA,
)

MEMORY_RERANK_SYSTEM_PROMPT = "你是一个本地记忆检索重排器。"
MEMORY_RERANK_INSTRUCTIONS = (
    "给定用户查询和候选记忆，请判断每条候选记忆是否能帮助回答查询。\n"
    "只根据候选内容本身打分，不要编造。\n"
    "评分：\n"
    "0 = 完全无关\n"
    "30 = 弱相关\n"
    "60 = 有一定相关\n"
    "80 = 强相关\n"
    "100 = 精确命中\n"
    "请只输出 JSON 数组，不要输出其他文字。"
)

SubAgentProviderMode = Literal[
    LLM_PROVIDER_SHARED,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_LLAMA,
]
