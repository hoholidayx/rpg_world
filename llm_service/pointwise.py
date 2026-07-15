"""Provider-neutral chat pointwise scoring owned by LLM Service."""

from __future__ import annotations

import asyncio
import re

from llm_client.types import DocumentScore, LLMProvider

_SYSTEM_PROMPT = "你是记忆检索重排器。只输出评分行。"
_INSTRUCTIONS = (
    "任务：判断候选记忆是否能回答用户查询。\n"
    "分数：0无关，30弱相关，60相关，80强相关，100精确命中。\n"
    "输出格式：<0-100整数>\\t<8字内原因>\n"
    "禁止输出其他内容。"
)


async def score_documents_with_chat(
    provider: LLMProvider,
    query: str,
    documents: list[str],
    *,
    max_document_chars: int = 2400,
) -> list[DocumentScore]:
    return await asyncio.gather(
        *(
            _score_one(
                provider,
                query,
                document,
                max_document_chars=max_document_chars,
            )
            for document in documents
        )
    )


async def _score_one(
    provider: LLMProvider,
    query: str,
    document: str,
    *,
    max_document_chars: int,
) -> DocumentScore:
    content = document
    if max_document_chars > 0 and len(content) > max_document_chars:
        content = f"{content[:max_document_chars]}\n...[候选记忆已截断，仅用于重排]"
    response = await provider.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{_INSTRUCTIONS}\n\n查询：{query}\n候选：{content}\n评分：",
            },
        ]
    )
    score, reason = _parse(response.content)
    return DocumentScore(
        score=max(0.0, min(1.0, score / 100.0)),
        reason=reason,
        debug={"source": "chat", "raw": " ".join(response.content.split())[:160]},
    )


def _parse(text: str) -> tuple[float, str]:
    first_line = (text or "").strip()[:4000].splitlines()[0].strip()
    if not first_line:
        raise ValueError("empty rerank output")
    parts = first_line.split("\t")
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split("|") if part.strip()]
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split(",") if part.strip()]
    try:
        score = float(parts[0])
    except (TypeError, ValueError):
        match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", first_line)
        if match is None:
            raise ValueError(f"no numeric score found: {first_line!r}")
        score = float(match.group(1))
    return score, parts[1] if len(parts) >= 2 else ""
