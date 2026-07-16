"""Public client contract for the standalone LLM service."""

from llm_client.client import (
    LLMServiceAuthError,
    LLMServiceClient,
    LLMServiceClientError,
    LLMServiceRemoteError,
    LLMServiceTimeout,
    LLMServiceUnavailable,
)
from llm_client.manager import LLMClientManager
from llm_client.provider import RemoteLLMProvider
from llm_client.types import (
    DocumentScore,
    DocumentScoreProvider,
    EmbeddingProviderError,
    LLMBizCatalog,
    LLMProvider,
    LLMProviderOption,
    LLMResponse,
    LLMSpeechAudio,
    LLMSpeechProfile,
    LLMUsage,
    ProviderChunk,
)

__all__ = [
    "DocumentScore",
    "DocumentScoreProvider",
    "EmbeddingProviderError",
    "LLMBizCatalog",
    "LLMClientManager",
    "LLMProvider",
    "LLMProviderOption",
    "LLMResponse",
    "LLMSpeechAudio",
    "LLMSpeechProfile",
    "LLMServiceAuthError",
    "LLMServiceClient",
    "LLMServiceClientError",
    "LLMServiceRemoteError",
    "LLMServiceTimeout",
    "LLMServiceUnavailable",
    "LLMUsage",
    "ProviderChunk",
    "RemoteLLMProvider",
]
