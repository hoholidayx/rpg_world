"""LLM configuration — typed accessors for ``llm_service/llm.yaml``.

This module owns the standalone LLM settings file.  Business code never
touches raw YAML keys directly; it gets a ``BizConfig`` via
``get_biz_config(biz_key)`` or retrieves a fully-built ``LLMProvider``
from ``LLMManager.get().get_provider(biz_key)``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from commons.settings import (
    PROFILE_ENV,
    ConfigDict,
    ConfigValue,
    load_profiled_yaml,
    load_yaml_mapping,
    optional_bool,
    optional_float,
    optional_int,
    resolve_profile_name,
)
from llm_service.keys import (
    LLMConfigKey,
    LLM_KIND_CHAT,
    LLM_KIND_RERANK,
    LLM_KINDS,
    PROVIDER_KINDS,
    PROVIDER_LLAMA,
    PROVIDER_OPENAI,
    RERANK_MODEL_TYPES,
    LLM_INPUT_MODALITIES,
    LLM_INPUT_MODALITY_TEXT,
)

_LLM_SETTINGS_PATH = Path(__file__).resolve().parent / "llm.yaml"
_PROFILE_ENV = PROFILE_ENV

# ── cached raw config ──────────────────────────────────────────────────

_raw_settings: ConfigDict | None = None
_cache_key: tuple[str, str] | None = None  # (resolved_path, profile)


@dataclass(frozen=True)
class LLMProviderOption:
    provider_key: str
    backend: str
    model: str
    context_window: int | None
    input_modalities: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider_key: str
    provider: str
    kind: str
    openai: ConfigDict
    llama: ConfigDict
    input_modalities: tuple[str, ...]


@dataclass(frozen=True)
class AgentLLMDefaults:
    provider_key: str
    provider: str
    model: str
    openai: ConfigDict
    llama: ConfigDict
    base_url: str | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    temperature: float | None = None


def _resolve_profile_name() -> str:
    """Determine the active profile name."""
    if not _LLM_SETTINGS_PATH.is_file():
        return (os.environ.get(_PROFILE_ENV) or "").strip() or "local"
    return resolve_profile_name(load_yaml_mapping(_LLM_SETTINGS_PATH, "llm_service/llm.yaml"), env_var=_PROFILE_ENV)


def _load_raw() -> ConfigDict:
    """Lazy-load and cache the merged raw LLM settings dict.

    The cache is keyed by (resolved_path, profile) so switching
    ``RPG_WORLD_PROFILE`` or ``_LLM_SETTINGS_PATH`` invalidates correctly.
    """
    global _raw_settings, _cache_key

    profile_name = _resolve_profile_name()
    path_key = str(_LLM_SETTINGS_PATH.resolve()) if _LLM_SETTINGS_PATH.is_file() else ""
    current_key = (path_key, profile_name)

    if _raw_settings is not None and _cache_key == current_key:
        return _raw_settings

    if not _LLM_SETTINGS_PATH.is_file():
        _raw_settings = {}
        _cache_key = current_key
        return _raw_settings

    _cache_key = current_key
    _raw_settings = load_profiled_yaml(_LLM_SETTINGS_PATH, profile_name, label="llm_service/llm.yaml")
    return _raw_settings


def reload_llm_settings() -> None:
    """Clear the cached config so the next read re-parses LLM settings."""
    global _raw_settings, _cache_key
    _raw_settings = None
    _cache_key = None


def load_llm_settings() -> ConfigDict:
    """Return the merged raw LLM config for the active profile."""
    return _load_raw()


def get_active_profile() -> str:
    """Return the active profile name (e.g. ``"local"``)."""
    return _resolve_profile_name()


def resolve_llm_config(
    biz_key: str,
    *,
    provider_key: str | None = None,
) -> ResolvedLLMConfig:
    """Return a provider-neutral typed config view for *biz_key*."""
    cfg = resolve_biz_config(biz_key, provider_key=provider_key)
    return ResolvedLLMConfig(
        provider_key=cfg.provider_key,
        provider=cfg.provider,
        kind=cfg.kind,
        openai=dict(cfg.openai_cfg),
        llama=dict(cfg.llama_cfg),
        input_modalities=cfg.input_modalities,
    )


def resolve_agent_defaults(
    biz_key: str,
    *,
    provider_key: str | None = None,
) -> AgentLLMDefaults:
    """Return the default agent-facing LLM settings for *biz_key*."""
    cfg = resolve_biz_config(biz_key, provider_key=provider_key)
    provider = cfg.provider
    if provider == PROVIDER_OPENAI:
        return AgentLLMDefaults(
            provider_key=cfg.provider_key,
            provider=provider,
            model=cfg.openai_model,
            openai=dict(cfg.openai_cfg),
            llama=dict(cfg.llama_cfg),
            base_url=cfg.openai_base_url or None,
            max_tokens=cfg.openai_max_tokens,
            context_window=cfg.openai_context_window,
            temperature=cfg.openai_temperature,
        )
    return AgentLLMDefaults(
        provider_key=cfg.provider_key,
        provider=provider,
        model=cfg.llama_model_path,
        openai=dict(cfg.openai_cfg),
        llama=dict(cfg.llama_cfg),
        context_window=cfg.llama_n_ctx,
    )


# ── typed biz-config wrapper ────────────────────────────────────────────


class BizConfig:
    """Typed view of a single ``biz`` entry in LLM settings.

    All YAML key access is encapsulated here so consumers never write
    hard-coded string keys.
    """

    __slots__ = ("_key", "_provider_key", "_provider_option_keys", "_raw")

    def __init__(
        self,
        biz_key: str,
        provider_key: str,
        provider_option_keys: tuple[str, ...],
        raw: ConfigDict,
    ) -> None:
        self._key = biz_key
        self._provider_key = provider_key
        self._provider_option_keys = provider_option_keys
        self._raw = raw

    # -- identity --------------------------------------------------------

    @property
    def biz_key(self) -> str:
        return self._key

    @property
    def provider_key(self) -> str:
        return self._provider_key

    @property
    def provider_option_keys(self) -> tuple[str, ...]:
        return self._provider_option_keys

    @property
    def provider(self) -> str:
        """``"openai"`` / ``"llama"``."""
        label = (
            f"{LLMConfigKey.PROVIDERS}.{self._provider_key}."
            f"{LLMConfigKey.PROVIDER}"
        )
        value = self._require_non_empty(self._raw.get(LLMConfigKey.PROVIDER), label)
        provider = value.lower()
        if provider not in PROVIDER_KINDS:
            raise ValueError(
                f"{label} must be one of {', '.join(sorted(PROVIDER_KINDS))}; got {provider!r}"
            )
        return provider

    @property
    def kind(self) -> str:
        """``"chat"`` / ``"embedding"`` / ``"planner"`` / ``"rerank"``."""
        label = f"{self._key}.{LLMConfigKey.KIND}"
        value = self._require_non_empty(self._raw.get(LLMConfigKey.KIND), label)
        kind = value.lower()
        if kind not in LLM_KINDS:
            raise ValueError(
                f"{label} must be one of {', '.join(sorted(LLM_KINDS))}; got {kind!r}"
            )
        return kind

    @property
    def input_modalities(self) -> tuple[str, ...]:
        """Ordered input capabilities declared by the selected provider."""
        label = f"{LLMConfigKey.PROVIDERS}.{self._provider_key}.{LLMConfigKey.INPUT_MODALITIES}"
        raw_value = self._raw.get(LLMConfigKey.INPUT_MODALITIES)
        if raw_value is None:
            return (LLM_INPUT_MODALITY_TEXT,)
        if not isinstance(raw_value, list):
            raise ValueError(f"{label} must be a list")
        modalities: list[str] = []
        for index, raw_modality in enumerate(raw_value):
            if not isinstance(raw_modality, str) or not raw_modality.strip():
                raise ValueError(f"{label}[{index}] must be a non-empty string")
            modality = raw_modality.strip().lower()
            if modality not in LLM_INPUT_MODALITIES:
                raise ValueError(
                    f"{label}[{index}] must be one of {', '.join(sorted(LLM_INPUT_MODALITIES))}; "
                    f"got {modality!r}"
                )
            if modality in modalities:
                raise ValueError(f"{label} must not contain duplicates")
            modalities.append(modality)
        if LLM_INPUT_MODALITY_TEXT not in modalities:
            raise ValueError(f"{label} must include {LLM_INPUT_MODALITY_TEXT!r}")
        return tuple(modalities)

    @property
    def rerank_model_type(self) -> str:
        """Explicit rerank scoring protocol for ``kind: rerank`` configs."""
        label = f"{self._key}.{LLMConfigKey.RERANK_MODEL_TYPE}"
        raw_value = self._raw.get(LLMConfigKey.RERANK_MODEL_TYPE)
        if self.kind != LLM_KIND_RERANK:
            return self._optional_str(raw_value)
        value = self._require_non_empty(raw_value, label).lower()
        if value not in RERANK_MODEL_TYPES:
            raise ValueError(
                f"{label} must be one of {', '.join(sorted(RERANK_MODEL_TYPES))}; got {value!r}"
            )
        return value

    # -- openai ----------------------------------------------------------

    @property
    def openai_model(self) -> str:
        return self._require_non_empty(
            self._openai_sub.get(LLMConfigKey.MODEL),
            f"{self._key}.{PROVIDER_OPENAI}.{LLMConfigKey.MODEL}",
        )

    @property
    def openai_cfg(self) -> ConfigDict:
        return self._openai_sub

    @property
    def openai_api_key(self) -> str | None:
        return self._resolve_api_key(self._openai_sub)

    @property
    def openai_base_url(self) -> str:
        return self._optional_str(self._openai_sub.get(LLMConfigKey.BASE_URL))

    @property
    def openai_max_tokens(self) -> int | None:
        return optional_int(self._openai_sub.get(LLMConfigKey.MAX_TOKENS), None)

    @property
    def openai_context_window(self) -> int | None:
        return optional_int(self._openai_sub.get(LLMConfigKey.CONTEXT_WINDOW), None)

    @property
    def openai_temperature(self) -> float | None:
        return self._optional_float(
            self._openai_sub.get(LLMConfigKey.TEMPERATURE),
            f"{self._key}.{PROVIDER_OPENAI}.{LLMConfigKey.TEMPERATURE}",
        )

    @property
    def _openai_sub(self) -> ConfigDict:
        value = self._raw.get(PROVIDER_OPENAI)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{self._key}.{PROVIDER_OPENAI} must be a mapping")
        return value

    # -- llama -----------------------------------------------------------

    @property
    def llama_model_path(self) -> str:
        return self._require_non_empty(
            self._llama_sub.get(LLMConfigKey.MODEL_PATH),
            f"{self._key}.{PROVIDER_LLAMA}.{LLMConfigKey.MODEL_PATH}",
        )

    @property
    def llama_cfg(self) -> ConfigDict:
        return self._llama_sub

    @property
    def llama_n_ctx(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.N_CTX), 2048) or 2048

    @property
    def llama_max_length(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.MAX_LENGTH), self.llama_n_ctx) or self.llama_n_ctx

    @property
    def llama_n_gpu_layers(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.N_GPU_LAYERS), 0) or 0

    @property
    def llama_n_threads(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.N_THREADS), 4) or 4

    @property
    def llama_verbose(self) -> bool:
        return optional_bool(self._llama_sub.get(LLMConfigKey.VERBOSE), False)

    @property
    def llama_request_timeout_ms(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.REQUEST_TIMEOUT_MS), 60000) or 60000

    @property
    def llama_max_tokens(self) -> int:
        return optional_int(self._llama_sub.get(LLMConfigKey.MAX_TOKENS), 512) or 512

    @property
    def llama_temperature(self) -> float:
        return optional_float(self._llama_sub.get(LLMConfigKey.TEMPERATURE), 0.0) or 0.0

    @property
    def _llama_sub(self) -> ConfigDict:
        value = self._raw.get(PROVIDER_LLAMA)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{self._key}.{PROVIDER_LLAMA} must be a mapping")
        return value

    # -- helpers ---------------------------------------------------------

    @property
    def raw(self) -> ConfigDict:
        """Effective provider config after applying biz-level overrides."""
        return self._raw

    @staticmethod
    def _optional_str(value: ConfigValue) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _require_non_empty(value: ConfigValue, label: str) -> str:
        text = BizConfig._optional_str(value)
        if not text:
            raise ValueError(f"{label} is required")
        return text

    @staticmethod
    def _optional_float(value: ConfigValue, label: str) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError(f"{label} must be a number")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a number") from exc

    @staticmethod
    def _resolve_api_key(openai_cfg: ConfigDict) -> str | None:
        api_key = BizConfig._optional_str(openai_cfg.get(LLMConfigKey.API_KEY))
        if api_key:
            return api_key
        api_key_env = BizConfig._optional_str(openai_cfg.get(LLMConfigKey.API_KEY_ENV))
        if api_key_env:
            env_value = os.environ.get(api_key_env)
            if env_value:
                return env_value
        return None


# ── public API ──────────────────────────────────────────────────────────


_BIZ_FIELDS = frozenset(
    {
        LLMConfigKey.KIND,
        LLMConfigKey.PROVIDER_KEY,
        LLMConfigKey.PROVIDER_OPTION_KEYS,
        LLMConfigKey.CONTEXT_WINDOW,
        LLMConfigKey.MAX_TOKENS,
        LLMConfigKey.TEMPERATURE,
        LLMConfigKey.RERANK_MODEL_TYPE,
    }
)
_BIZ_PROVIDER_OVERRIDES = frozenset(
    {
        LLMConfigKey.CONTEXT_WINDOW,
        LLMConfigKey.MAX_TOKENS,
        LLMConfigKey.TEMPERATURE,
    }
)


def _resolve_provider_option_keys(
    biz_key: str,
    biz_cfg: ConfigDict,
    default_provider_key: str,
) -> tuple[str, ...]:
    raw_options = biz_cfg.get(LLMConfigKey.PROVIDER_OPTION_KEYS)
    if raw_options is None:
        return (default_provider_key,)
    if not isinstance(raw_options, list):
        raise ValueError(
            f"{biz_key}.{LLMConfigKey.PROVIDER_OPTION_KEYS} must be a list"
        )

    option_keys: list[str] = []
    for index, raw_key in enumerate(raw_options):
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(
                f"{biz_key}.{LLMConfigKey.PROVIDER_OPTION_KEYS}[{index}] must be a non-empty string"
            )
        option_keys.append(raw_key.strip())
    if not option_keys:
        raise ValueError(
            f"{biz_key}.{LLMConfigKey.PROVIDER_OPTION_KEYS} must not be empty"
        )
    if len(set(option_keys)) != len(option_keys):
        raise ValueError(
            f"{biz_key}.{LLMConfigKey.PROVIDER_OPTION_KEYS} must not contain duplicates"
        )
    if default_provider_key not in option_keys:
        raise ValueError(
            f"{biz_key}.{LLMConfigKey.PROVIDER_OPTION_KEYS} must include default provider_key "
            f"{default_provider_key!r}"
        )
    return tuple(option_keys)


def _resolve_biz_entry(
    biz_key: str,
    biz_cfg: ConfigDict,
    *,
    selected_provider_key: str | None = None,
) -> BizConfig:
    unknown_fields = sorted(set(biz_cfg) - _BIZ_FIELDS)
    if unknown_fields:
        raise ValueError(
            f"{biz_key} config has unsupported fields: {', '.join(unknown_fields)}"
        )

    default_provider_key = BizConfig._require_non_empty(
        biz_cfg.get(LLMConfigKey.PROVIDER_KEY),
        f"{biz_key}.{LLMConfigKey.PROVIDER_KEY}",
    )
    provider_option_keys = _resolve_provider_option_keys(
        biz_key,
        biz_cfg,
        default_provider_key,
    )
    provider_key = (
        default_provider_key
        if selected_provider_key is None
        else selected_provider_key
    )
    if provider_key not in provider_option_keys:
        raise ValueError(
            f"{biz_key} provider_key {provider_key!r} is not in "
            f"{LLMConfigKey.PROVIDER_OPTION_KEYS}"
        )
    raw = load_llm_settings()
    providers = raw.get(LLMConfigKey.PROVIDERS)
    if not isinstance(providers, dict):
        raise ValueError(f"llm {LLMConfigKey.PROVIDERS} must be a mapping")
    for option_key in provider_option_keys:
        if option_key not in providers:
            raise ValueError(f"llm provider config not found: {option_key}")
    provider_cfg = providers.get(provider_key)
    if provider_cfg is None:
        raise ValueError(f"llm provider config not found: {provider_key}")
    if not isinstance(provider_cfg, dict):
        raise ValueError(
            f"{LLMConfigKey.PROVIDERS}.{provider_key} must be a mapping"
        )

    effective = dict(provider_cfg)
    effective[LLMConfigKey.PROVIDER_KEY] = provider_key
    effective[LLMConfigKey.KIND] = biz_cfg.get(LLMConfigKey.KIND)
    cfg = BizConfig(biz_key, provider_key, provider_option_keys, effective)
    backend = cfg.provider
    kind = cfg.kind

    backend_cfg = effective.get(backend)
    if not isinstance(backend_cfg, dict):
        raise ValueError(
            f"{LLMConfigKey.PROVIDERS}.{provider_key}.{backend} must be a mapping"
        )
    merged_backend_cfg = dict(backend_cfg)
    for field in _BIZ_PROVIDER_OVERRIDES:
        if field not in biz_cfg:
            continue
        target_field = (
            LLMConfigKey.N_CTX
            if backend == PROVIDER_LLAMA and field == LLMConfigKey.CONTEXT_WINDOW
            else field
        )
        merged_backend_cfg[target_field] = biz_cfg[field]
    effective[backend] = merged_backend_cfg

    if LLMConfigKey.RERANK_MODEL_TYPE in biz_cfg:
        effective[LLMConfigKey.RERANK_MODEL_TYPE] = biz_cfg[LLMConfigKey.RERANK_MODEL_TYPE]

    resolved = BizConfig(biz_key, provider_key, provider_option_keys, effective)
    resolved.input_modalities
    if kind == LLM_KIND_RERANK:
        resolved.rerank_model_type
    return resolved


def get_biz_config(biz_key: str) -> BizConfig | None:
    """Return the resolved config for *biz_key*, or ``None`` if absent."""
    raw = load_llm_settings()
    biz = raw.get(LLMConfigKey.BIZ)
    if biz is None:
        return None
    if not isinstance(biz, dict):
        raise ValueError(f"llm {LLMConfigKey.BIZ} must be a mapping")
    biz_cfg = biz.get(biz_key)
    if biz_cfg is None:
        return None
    if not isinstance(biz_cfg, dict):
        raise ValueError(f"{biz_key} config must be a mapping")
    return _resolve_biz_entry(biz_key, biz_cfg)


def resolve_biz_config(
    biz_key: str,
    *,
    provider_key: str | None = None,
) -> BizConfig:
    """Resolve a biz entry against the configured provider pool."""
    raw = load_llm_settings()
    biz = raw.get(LLMConfigKey.BIZ)
    if biz is None:
        raise ValueError(f"llm biz config not found: {biz_key}")
    if not isinstance(biz, dict):
        raise ValueError(f"llm {LLMConfigKey.BIZ} must be a mapping")
    biz_cfg = biz.get(biz_key)
    if biz_cfg is None:
        raise ValueError(f"llm biz config not found: {biz_key}")
    if not isinstance(biz_cfg, dict):
        raise ValueError(f"{biz_key} config must be a mapping")
    return _resolve_biz_entry(
        biz_key,
        biz_cfg,
        selected_provider_key=provider_key,
    )


def list_provider_options(biz_key: str) -> tuple[LLMProviderOption, ...]:
    """Return the ordered, safe-to-expose provider options for one biz."""
    default_cfg = resolve_biz_config(biz_key)
    options: list[LLMProviderOption] = []
    for provider_key in default_cfg.provider_option_keys:
        cfg = resolve_biz_config(biz_key, provider_key=provider_key)
        if cfg.provider == PROVIDER_OPENAI:
            model = cfg.openai_model
            context_window = cfg.openai_context_window
        else:
            model = PureWindowsPath(cfg.llama_model_path).name
            context_window = cfg.llama_n_ctx
        options.append(
            LLMProviderOption(
                provider_key=provider_key,
                backend=cfg.provider,
                model=model,
                context_window=context_window,
                input_modalities=cfg.input_modalities,
            )
        )
    return tuple(options)


def resolve_context_window(
    biz_key: str,
    *,
    provider_key: str | None = None,
) -> int | None:
    """Return the configured context window for a chat biz key, if known."""
    cfg = resolve_biz_config(biz_key, provider_key=provider_key)
    if cfg.provider == PROVIDER_OPENAI:
        return cfg.openai_context_window
    if cfg.provider == PROVIDER_LLAMA:
        return cfg.llama_n_ctx
    return None
