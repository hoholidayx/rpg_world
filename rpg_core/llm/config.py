"""LLM configuration — typed accessors for ``llm.yaml``.

This module owns the standalone ``llm.yaml`` file.  Business code never
touches raw YAML keys directly; it gets a ``BizConfig`` via
``get_biz_config(biz_key)`` or retrieves a fully-built ``LLMProvider``
from ``LLMManager.get().get_provider(biz_key)``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.utils.profile_loader import load_profiled_yaml
from rpg_world.rpg_core.llm.keys import (
    LLM_KIND_CHAT,
    LLM_KIND_RERANK,
    LLM_KINDS,
    PROVIDER_DEFAULT,
    PROVIDER_KINDS,
    PROVIDER_LLAMA,
    PROVIDER_OPENAI,
    PROVIDER_SHARED,
    RERANK_MODEL_TYPES,
)
from rpg_world.rpg_core.utils.config_values import optional_bool, optional_float, optional_int

_LLM_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "llm.yaml"
_PROFILE_ENV = "RPG_WORLD_PROFILE"

# ── cached raw config ──────────────────────────────────────────────────

_raw_settings: dict[str, Any] | None = None
_cache_key: tuple[str, str] | None = None  # (resolved_path, profile)


@dataclass(frozen=True)
class LLMRuntimeConfig:
    llama_process_enabled: bool = True
    llama_request_timeout_ms: int = 60000
    llama_startup_timeout_ms: int = 120000
    llama_max_parallel_models: int = 2


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider: str
    kind: str
    openai: dict[str, Any]
    llama: dict[str, Any]
    shared_from: str = ""


@dataclass(frozen=True)
class AgentLLMDefaults:
    provider: str
    model: str
    openai: dict[str, Any]
    llama: dict[str, Any]
    base_url: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


def _resolve_profile_name() -> str:
    """Determine the active profile name."""
    profile_name = (os.environ.get(_PROFILE_ENV) or "").strip()
    if not profile_name:
        if _LLM_SETTINGS_PATH.is_file():
            import yaml
            with _LLM_SETTINGS_PATH.open(encoding="utf-8") as fh:
                top = yaml.safe_load(fh) or {}
            if isinstance(top, dict):
                profile_name = str(top.get("default_profile") or "local").strip() or "local"
        if not profile_name:
            profile_name = "local"
    return profile_name


def _load_raw() -> dict[str, Any]:
    """Lazy-load and cache the merged raw ``llm.yaml`` dict.

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
    _raw_settings = load_profiled_yaml(_LLM_SETTINGS_PATH, profile_name, label="llm.yaml")
    return _raw_settings


def reload_llm_settings() -> None:
    """Clear the cached config so the next read re-parses ``llm.yaml``."""
    global _raw_settings, _cache_key
    _raw_settings = None
    _cache_key = None


def load_llm_settings() -> dict[str, Any]:
    """Return the merged raw LLM config for the active profile."""
    return _load_raw()


def get_active_profile() -> str:
    """Return the active profile name (e.g. ``"local"``)."""
    return _resolve_profile_name()


def get_runtime_config() -> LLMRuntimeConfig:
    """Return typed runtime settings from ``llm.yaml``."""
    raw = load_llm_settings()
    runtime = raw.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    return LLMRuntimeConfig(
        llama_process_enabled=optional_bool(runtime.get("llama_process_enabled"), True),
        llama_request_timeout_ms=optional_int(runtime.get("llama_request_timeout_ms"), 60000) or 60000,
        llama_startup_timeout_ms=optional_int(runtime.get("llama_startup_timeout_ms"), 120000) or 120000,
        llama_max_parallel_models=optional_int(runtime.get("llama_max_parallel_models"), 2) or 2,
    )


def resolve_llm_config(biz_key: str) -> ResolvedLLMConfig:
    """Return a provider-neutral typed config view for *biz_key*."""
    cfg = resolve_biz_config(biz_key)
    return ResolvedLLMConfig(
        provider=cfg.provider,
        kind=cfg.kind,
        openai=dict(cfg.openai_cfg),
        llama=dict(cfg.llama_cfg),
        shared_from=cfg.shared_from,
    )


def resolve_agent_defaults(biz_key: str) -> AgentLLMDefaults:
    """Return the default agent-facing LLM settings for *biz_key*."""
    cfg = resolve_biz_config(biz_key)
    provider = cfg.provider
    if provider == PROVIDER_OPENAI:
        return AgentLLMDefaults(
            provider=provider,
            model=cfg.openai_model,
            openai=dict(cfg.openai_cfg),
            llama=dict(cfg.llama_cfg),
            base_url=cfg.openai_base_url or None,
            max_tokens=cfg.openai_max_tokens,
            temperature=cfg.openai_temperature,
        )
    return AgentLLMDefaults(
        provider=provider,
        model=cfg.llama_model_path,
        openai=dict(cfg.openai_cfg),
        llama=dict(cfg.llama_cfg),
    )


# ── typed biz-config wrapper ────────────────────────────────────────────


class BizConfig:
    """Typed view of a single ``biz`` entry in ``llm.yaml``.

    All YAML key access is encapsulated here so consumers never write
    hard-coded string keys.
    """

    __slots__ = ("_key", "_raw")

    def __init__(self, biz_key: str, raw: dict[str, Any]) -> None:
        self._key = biz_key
        self._raw = raw

    # -- identity --------------------------------------------------------

    @property
    def biz_key(self) -> str:
        return self._key

    @property
    def provider(self) -> str:
        """``"openai"`` / ``"llama"`` / ``"shared"``."""
        raw_value = self._raw.get("provider", PROVIDER_DEFAULT)
        value = str(raw_value).strip()
        provider = value.lower()
        if provider not in PROVIDER_KINDS:
            raise ValueError(
                f"{self._key}.provider must be one of {', '.join(sorted(PROVIDER_KINDS))}; got {provider!r}"
            )
        return provider

    @property
    def kind(self) -> str:
        """``"chat"`` / ``"embedding"`` / ``"planner"`` / ``"rerank"``."""
        raw_value = self._raw.get("kind", LLM_KIND_CHAT)
        value = str(raw_value).strip()
        kind = value.lower()
        if kind not in LLM_KINDS:
            raise ValueError(
                f"{self._key}.kind must be one of {', '.join(sorted(LLM_KINDS))}; got {kind!r}"
            )
        return kind

    @property
    def shared_from(self) -> str:
        """Biz key to delegate to when ``provider == "shared"``."""
        return str(self._raw.get("shared_from") or "").strip()

    @property
    def rerank_model_type(self) -> str:
        """Explicit rerank scoring protocol for ``kind: rerank`` configs."""
        label = f"{self._key}.rerank_model_type"
        raw_value = self._raw.get("rerank_model_type")
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
            self._openai_sub.get("model"), f"{self._key}.openai.model"
        )

    @property
    def openai_cfg(self) -> dict[str, Any]:
        return self._openai_sub

    @property
    def openai_api_key(self) -> str | None:
        return self._resolve_api_key(self._openai_sub)

    @property
    def openai_base_url(self) -> str:
        return self._optional_str(self._openai_sub.get("base_url"))

    @property
    def openai_max_tokens(self) -> int | None:
        return optional_int(self._openai_sub.get("max_tokens"), None)

    @property
    def openai_temperature(self) -> float | None:
        return self._optional_float(self._openai_sub.get("temperature"), f"{self._key}.openai.temperature")

    @property
    def _openai_sub(self) -> dict[str, Any]:
        value = self._raw.get(PROVIDER_OPENAI)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{self._key}.openai must be a mapping")
        return value

    # -- llama -----------------------------------------------------------

    @property
    def llama_model_path(self) -> str:
        return self._require_non_empty(
            self._llama_sub.get("model_path"), f"{self._key}.llama.model_path"
        )

    @property
    def llama_cfg(self) -> dict[str, Any]:
        return self._llama_sub

    @property
    def llama_n_ctx(self) -> int:
        return optional_int(self._llama_sub.get("n_ctx"), 2048) or 2048

    @property
    def llama_max_length(self) -> int:
        return optional_int(self._llama_sub.get("max_length"), self.llama_n_ctx) or self.llama_n_ctx

    @property
    def llama_n_gpu_layers(self) -> int:
        return optional_int(self._llama_sub.get("n_gpu_layers"), 0) or 0

    @property
    def llama_n_threads(self) -> int:
        return optional_int(self._llama_sub.get("n_threads"), 4) or 4

    @property
    def llama_verbose(self) -> bool:
        return optional_bool(self._llama_sub.get("verbose"), False)

    @property
    def llama_request_timeout_ms(self) -> int:
        return optional_int(self._llama_sub.get("request_timeout_ms"), 60000) or 60000

    @property
    def llama_max_tokens(self) -> int:
        return optional_int(self._llama_sub.get("max_tokens"), 512) or 512

    @property
    def llama_temperature(self) -> float:
        return optional_float(self._llama_sub.get("temperature"), 0.0) or 0.0

    @property
    def _llama_sub(self) -> dict[str, Any]:
        value = self._raw.get(PROVIDER_LLAMA)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{self._key}.llama must be a mapping")
        return value

    # -- helpers ---------------------------------------------------------

    @property
    def raw(self) -> dict[str, Any]:
        """Raw merged config dict (escape hatch for legacy consumers)."""
        return self._raw

    @staticmethod
    def _optional_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _require_non_empty(value: Any, label: str) -> str:
        text = BizConfig._optional_str(value)
        if not text:
            raise ValueError(f"{label} is required")
        return text

    @staticmethod
    def _optional_float(value: Any, label: str) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError(f"{label} must be a number")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a number") from exc

    @staticmethod
    def _resolve_api_key(openai_cfg: dict[str, Any]) -> str | None:
        api_key = BizConfig._optional_str(openai_cfg.get("api_key"))
        if api_key:
            return api_key
        api_key_env = BizConfig._optional_str(openai_cfg.get("api_key_env"))
        if api_key_env:
            env_value = os.environ.get(api_key_env)
            if env_value:
                return env_value
        return None


# ── public API ──────────────────────────────────────────────────────────


def get_biz_config(biz_key: str) -> BizConfig | None:
    """Return the typed config block for *biz_key*, or ``None`` if absent."""
    raw = load_llm_settings()
    biz = raw.get("biz", {})
    if not isinstance(biz, dict):
        return None
    cfg = biz.get(biz_key)
    if not isinstance(cfg, dict):
        return None
    return BizConfig(biz_key, cfg)


def _deep_merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge dictionaries used by shared config inheritance."""
    merged = dict(left)
    for key, value in right.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def _resolve_shared_chain(
    biz_key: str,
    *,
    seen: tuple[str, ...],
) -> dict[str, Any]:
    """Resolve one shared chain branch with loop prevention."""
    cfg = get_biz_config(biz_key)
    if cfg is None:
        raise ValueError(f"llm biz config not found: {biz_key}")

    if cfg.provider != PROVIDER_SHARED:
        return dict(cfg.raw)

    shared_from = cfg.shared_from
    if not shared_from:
        raise ValueError(
            f"{biz_key} config invalid: shared_from is required for shared provider"
        )

    if shared_from in seen:
        chain = " -> ".join((*seen, shared_from))
        raise ValueError(f"llm biz shared_from cycle detected: {chain}")

    parent_raw = _resolve_shared_chain(shared_from, seen=(*seen, biz_key))
    merged = _deep_merge_dicts(parent_raw, cfg.raw)
    merged["provider"] = str(parent_raw.get("provider") or PROVIDER_DEFAULT).strip().lower() or PROVIDER_DEFAULT
    return merged


def resolve_biz_config(biz_key: str) -> BizConfig:
    """Like :func:`get_biz_config` but follows ``shared_from`` chains."""
    merged = _resolve_shared_chain(biz_key, seen=())
    return BizConfig(biz_key, merged)
