"""Pluggable keyword tokenizers for memory text search."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from functools import lru_cache

from loguru import logger

from rp_memory.bigram_tokenizer import tokenize_bigram

_TECH_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[.\-+][A-Za-z0-9_]+)*")


class KeywordTokenizer(ABC):
    """Tokenizer used by the SQLite keyword FTS index."""

    name: str

    @abstractmethod
    def tokenize(self, text: str) -> list[str]:
        """Return search tokens for ``text``."""


class JiebaKeywordTokenizer(KeywordTokenizer):
    name = "jieba"

    def __init__(self, dictionary_path: str | None = None) -> None:
        self._dictionary_path = dictionary_path or None
        self._tokenizer = _get_jieba_tokenizer(self._dictionary_path)

    def tokenize(self, text: str) -> list[str]:
        normalized = " ".join((text or "").split())
        if not normalized:
            return []
        try:
            if self._tokenizer is None:
                raise RuntimeError("jieba tokenizer unavailable")
            parts = self._tokenizer.lcut(normalized)
        except Exception as exc:
            logger.warning("[KeywordTokenizer] jieba unavailable, regex fallback: {}", exc)
            parts = re.findall(r"[A-Za-z0-9_]+(?:[.\-+][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+", normalized)
        tokens: list[str] = []
        for part in parts:
            token = part.strip()
            if not _is_meaningful_token(token):
                continue
            tokens.append(token)
            lower = token.lower()
            if lower != token:
                tokens.append(lower)
        return _dedupe(tokens)


class BigramKeywordTokenizer(KeywordTokenizer):
    name = "bigram"

    def tokenize(self, text: str) -> list[str]:
        return tokenize_bigram(text)


class CombinedKeywordTokenizer(KeywordTokenizer):
    name = "both"

    def __init__(self, dictionary_path: str | None = None) -> None:
        self._jieba = JiebaKeywordTokenizer(dictionary_path)
        self._bigram = BigramKeywordTokenizer()

    def tokenize(self, text: str) -> list[str]:
        return _dedupe([*self._jieba.tokenize(text), *self._bigram.tokenize(text)])


def build_keyword_tokenizer(mode: str | None = None, jieba_dict: str | None = None) -> KeywordTokenizer:
    """Build a keyword tokenizer from memory.keyword_tokenizer."""
    normalized = (mode or "jieba").strip().lower()
    if normalized == "bigram":
        return BigramKeywordTokenizer()
    if normalized == "both":
        return CombinedKeywordTokenizer(jieba_dict)
    if normalized != "jieba":
        logger.warning("[KeywordTokenizer] unknown tokenizer {!r}, fallback to jieba", mode)
    return JiebaKeywordTokenizer(jieba_dict)


@lru_cache(maxsize=8)
def _get_jieba_tokenizer(dictionary_path: str | None):
    try:
        import jieba

        if dictionary_path:
            return jieba.Tokenizer(dictionary=dictionary_path)
        return jieba.Tokenizer()
    except Exception as exc:
        logger.warning("[KeywordTokenizer] jieba tokenizer init failed, regex fallback: {}", exc)
        return None


def _is_meaningful_token(token: str) -> bool:
    return bool(token and re.search(r"[A-Za-z0-9_\u4e00-\u9fff]", token))


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result
