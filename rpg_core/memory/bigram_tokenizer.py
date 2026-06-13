"""Chinese-friendly bigram tokenizer for SQLite FTS."""

from __future__ import annotations

import re

_TECH_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[.\-+][A-Za-z0-9_]+)*")


def tokenize_bigram(text: str) -> list[str]:
    """Tokenize mixed Chinese/technical text without external segmenters."""
    tokens: list[str] = []
    chinese_run: list[str] = []
    index = 0
    text = " ".join((text or "").split())

    def flush_chinese() -> None:
        if not chinese_run:
            return
        run = "".join(chinese_run)
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        chinese_run.clear()

    while index < len(text):
        char = text[index]
        if _is_cjk(char):
            chinese_run.append(char)
            index += 1
            continue

        flush_chinese()
        match = _TECH_TOKEN_RE.match(text, index)
        if match:
            token = match.group(0)
            tokens.append(token)
            lower = token.lower()
            if lower != token:
                tokens.append(lower)
            index = match.end()
            continue
        index += 1

    flush_chinese()
    return _dedupe(tokens)


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result
