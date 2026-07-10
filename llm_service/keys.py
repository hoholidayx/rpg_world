"""Shared LLM business keys, provider labels, and config schema fields."""

from __future__ import annotations

AGENT_MAIN_BIZ_KEY = "agent.main"
AGENT_STATUS_SUB_AGENT_BIZ_KEY = "agent.status_sub_agent"
AGENT_MEMORY_SUB_AGENT_BIZ_KEY = "agent.memory_sub_agent"

MEMORY_EMBED_BIZ_KEY = "memory.embed"
MEMORY_QUERY_PLANNER_BIZ_KEY = "memory.query_planner"
MEMORY_RERANK_BIZ_KEY = "memory.rerank"


class LLMConfigKey:
    """Canonical field names used by ``llm_service/llm.yaml`` accessors."""

    RUNTIME = "runtime"
    PROVIDERS = "providers"
    BIZ = "biz"

    PROVIDER = "provider"
    PROVIDER_KEY = "provider_key"
    KIND = "kind"
    RERANK_MODEL_TYPE = "rerank_model_type"

    MODEL = "model"
    API_KEY = "api_key"
    API_KEY_ENV = "api_key_env"
    BASE_URL = "base_url"
    CONTEXT_WINDOW = "context_window"
    MAX_TOKENS = "max_tokens"
    TEMPERATURE = "temperature"

    MODEL_PATH = "model_path"
    N_CTX = "n_ctx"
    MAX_LENGTH = "max_length"
    N_GPU_LAYERS = "n_gpu_layers"
    N_THREADS = "n_threads"
    VERBOSE = "verbose"
    REQUEST_TIMEOUT_MS = "request_timeout_ms"

    LLAMA_PROCESS_ENABLED = "llama_process_enabled"
    LLAMA_REQUEST_TIMEOUT_MS = "llama_request_timeout_ms"
    LLAMA_STARTUP_TIMEOUT_MS = "llama_startup_timeout_ms"
    LLAMA_MAX_PARALLEL_MODELS = "llama_max_parallel_models"


PROVIDER_OPENAI = "openai"
PROVIDER_LLAMA = "llama"

PROVIDER_KINDS = frozenset({PROVIDER_OPENAI, PROVIDER_LLAMA})

LLM_KIND_CHAT = "chat"
LLM_KIND_EMBEDDING = "embedding"
LLM_KIND_PLANNER = "planner"
LLM_KIND_RERANK = "rerank"
LLM_KINDS = frozenset({LLM_KIND_CHAT, LLM_KIND_EMBEDDING, LLM_KIND_PLANNER, LLM_KIND_RERANK})

RERANK_MODEL_TYPE_QWEN3_LOGIT = "qwen3_logit"
RERANK_MODEL_TYPE_CHAT_POINTWISE = "chat_pointwise"
RERANK_MODEL_TYPES = frozenset({RERANK_MODEL_TYPE_QWEN3_LOGIT, RERANK_MODEL_TYPE_CHAT_POINTWISE})
