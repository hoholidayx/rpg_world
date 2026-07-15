"""Compatibility exports for server-side provider implementations.

Production consumers import these contracts from :mod:`llm_client`.
"""

from llm_client.types import DocumentScoreProvider, EmbeddingProviderError, LLMProvider

__all__ = ["DocumentScoreProvider", "EmbeddingProviderError", "LLMProvider"]
