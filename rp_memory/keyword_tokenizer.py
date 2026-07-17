"""Pluggable keyword tokenizers for memory text search."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from functools import lru_cache

from loguru import logger

from rp_memory.bigram_tokenizer import TECH_TOKEN_RE, tokenize_bigram
KEYWORD_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "着",
        "过",
        "呢",
        "吗",
        "么",
        "啊",
        "吧",
        "呀",
        "哦",
        "和",
        "与",
        "及",
        "或",
        "而",
        "并",
        "且",
        "在",
        "于",
        "从",
        "到",
        "对",
        "向",
        "把",
        "被",
        "给",
        "跟",
        "是",
        "有",
        "为",
        "作为",
        "这",
        "那",
        "此",
        "这些",
        "那些",
        "这个",
        "那个",
        "我",
        "你",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "她们",
        "它们",
        "谁",
        "什么",
        "哪",
        "哪个",
        "哪里",
        "何时",
        "什么时候",
        "怎么",
        "如何",
        "为什么",
        "是否",
        "一下",
        "一个",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "from",
        "with",
        "by",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "whether",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "us",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
    }
)


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
            parts = tokenize_bigram(normalized)
        parts.extend(TECH_TOKEN_RE.findall(normalized))
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
    return bool(
        token
        and not is_keyword_stopword(token)
        and re.search(r"[A-Za-z0-9_\u4e00-\u9fff]", token)
    )


def is_keyword_stopword(token: str) -> bool:
    """Return whether a segmented token carries no useful recall identity."""
    return token.strip().casefold() in KEYWORD_STOPWORDS


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result
