"""Shared LLM business keys, provider labels, and config schema fields."""

from __future__ import annotations

from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
    MEDIA_IMAGE_METADATA_BIZ_KEY,
    MEDIA_VISUAL_BRIEF_BIZ_KEY,
    TTS_REPLY_BIZ_KEY,
    PROVIDER_LLAMA,
    PROVIDER_OPENAI,
)


class LLMConfigKey:
    """Canonical field names used by ``llm_service/llm.yaml`` accessors."""

    PROVIDERS = "providers"
    BIZ = "biz"

    PROVIDER = "provider"
    PROVIDER_KEY = "provider_key"
    PROVIDER_OPTION_KEYS = "provider_option_keys"
    KIND = "kind"
    RERANK_MODEL_TYPE = "rerank_model_type"

    MODEL = "model"
    API_KEY = "api_key"
    API_KEY_ENV = "api_key_env"
    BASE_URL = "base_url"
    CONTEXT_WINDOW = "context_window"
    MAX_TOKENS = "max_tokens"
    TEMPERATURE = "temperature"
    VOICE = "voice"
    RESPONSE_FORMAT = "response_format"
    SPEED = "speed"
    CACHE_REVISION = "cache_revision"
    INPUT_MODALITIES = "input_modalities"

    MODEL_PATH = "model_path"
    N_CTX = "n_ctx"
    MAX_LENGTH = "max_length"
    N_GPU_LAYERS = "n_gpu_layers"
    N_THREADS = "n_threads"
    VERBOSE = "verbose"
    REQUEST_TIMEOUT_MS = "request_timeout_ms"


PROVIDER_KINDS = frozenset({PROVIDER_OPENAI, PROVIDER_LLAMA})

LLM_KIND_CHAT = "chat"
LLM_KIND_EMBEDDING = "embedding"
LLM_KIND_PLANNER = "planner"
LLM_KIND_RERANK = "rerank"
LLM_KIND_SPEECH = "speech"
LLM_KINDS = frozenset(
    {LLM_KIND_CHAT, LLM_KIND_EMBEDDING, LLM_KIND_PLANNER, LLM_KIND_RERANK, LLM_KIND_SPEECH}
)

RERANK_MODEL_TYPE_QWEN3_LOGIT = "qwen3_logit"
RERANK_MODEL_TYPE_CHAT_POINTWISE = "chat_pointwise"
RERANK_MODEL_TYPES = frozenset({RERANK_MODEL_TYPE_QWEN3_LOGIT, RERANK_MODEL_TYPE_CHAT_POINTWISE})

LLM_INPUT_MODALITY_TEXT = "text"
LLM_INPUT_MODALITY_IMAGE = "image"
LLM_INPUT_MODALITIES = frozenset({LLM_INPUT_MODALITY_TEXT, LLM_INPUT_MODALITY_IMAGE})
