"""Shared base support for ``base + profiles`` YAML settings."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Callable, cast

import yaml

from commons.types import YamlMapping, YamlValue

ConfigDict = YamlMapping
ConfigValue = YamlValue
YamlMergeFn = Callable[[ConfigDict, ConfigDict], ConfigDict]

PROFILE_ENV = "RPG_WORLD_PROFILE"
FIXED_PROFILES = frozenset({"local", "test", "prod"})


def load_yaml_mapping(path: Path, label: str) -> ConfigDict:
    with path.open(encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(ConfigDict, loaded)


def deep_merge_dicts(base: ConfigDict, override: ConfigDict) -> ConfigDict:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def optional_bool(value: ConfigValue, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def optional_int(value: object, default: int | None = None) -> int | None:
    """Return an int when *value* is parseable, otherwise *default*."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def optional_float(value: object, default: float | None = None) -> float | None:
    """Return a float when *value* is parseable, otherwise *default*."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def forgiving_int(value: object, default: int) -> int:
    """Return parsed int or *default* for invalid config values."""
    parsed = optional_int(value, default)
    return default if parsed is None else parsed


def forgiving_float(value: object, default: float) -> float:
    """Return parsed float or *default* for invalid config values."""
    parsed = optional_float(value, default)
    return default if parsed is None else parsed


def resolve_profile_name(
    loaded: ConfigDict,
    *,
    env_var: str = PROFILE_ENV,
    default: str = "local",
) -> str:
    profile_name = (os.environ.get(env_var) or "").strip()
    if not profile_name:
        profile_name = str(loaded.get("default_profile") or default).strip() or default
    if profile_name not in FIXED_PROFILES:
        raise ValueError(
            f"profile must be one of {', '.join(sorted(FIXED_PROFILES))}; got {profile_name!r}"
        )
    return profile_name


def automatic_profile_path(base_path: Path, profile_name: str) -> Path:
    return base_path.with_name(f"{base_path.stem}.{profile_name}{base_path.suffix}")


def _inline_profile_override(
    profile_name: str,
    profile: ConfigValue,
    *,
    label: str,
) -> ConfigDict:
    """Return inline profile overrides only.

    Cross-file overrides are loaded from automatic sibling profile files such
    as ``settings.local.yaml``. Explicit ``profiles.*.file`` is intentionally
    unsupported in the split process-config architecture.
    """
    if profile is None:
        return {}
    if isinstance(profile, str):
        raise ValueError(f"{label} profile must be a mapping: {profile_name}")
    if not isinstance(profile, dict):
        raise ValueError(f"{label} profile must be a mapping: {profile_name}")
    if "file" in profile or "required" in profile:
        raise ValueError(
            f"{label} profile must not declare file/required: {profile_name}; "
            "use the sibling profile YAML file instead"
        )
    return cast(ConfigDict, dict(profile))


def load_profiled_yaml(
    path: Path,
    profile_name: str | None = None,
    *,
    label: str,
    merge_fn: YamlMergeFn = deep_merge_dicts,
    env_var: str = PROFILE_ENV,
) -> ConfigDict:
    """Load a YAML file as ``base + profile + sibling profile file``.

    Supported profile names are fixed to ``local``, ``test`` and ``prod``.
    For a base file named ``settings.yaml``, the selected profile also loads
    optional sibling files such as ``settings.local.yaml`` automatically.
    """
    loaded = load_yaml_mapping(path, label)
    profile = profile_name or resolve_profile_name(loaded, env_var=env_var)
    if profile not in FIXED_PROFILES:
        raise ValueError(f"{label} profile not found: {profile}")

    base = loaded.get("base", {})
    if not isinstance(base, dict):
        raise ValueError(f"{label} base must be a mapping")
    profiles = loaded.get("profiles", {})
    if profiles is None:
        profiles = {}
    if not isinstance(profiles, dict):
        raise ValueError(f"{label} profiles must be a mapping")

    inline = _inline_profile_override(
        profile,
        profiles.get(profile, {}),
        label=label,
    )
    merged = merge_fn(base, inline)

    auto_path = automatic_profile_path(path, profile)
    if auto_path.is_file():
        merged = merge_fn(merged, load_yaml_mapping(auto_path, f"{label} profile file: {profile}"))
    return merged


class ProfiledYamlSettings:
    """Base class for read-only process settings backed by profiled YAML."""

    settings_path: Path
    label: str = "settings.yaml"
    env_var: str = PROFILE_ENV
    merge_fn: YamlMergeFn = staticmethod(deep_merge_dicts)

    def __init__(self, profile_name: str | None = None) -> None:
        loaded = load_yaml_mapping(self.settings_path, self.label)
        self.profile = profile_name or resolve_profile_name(loaded, env_var=self.env_var)
        self._raw = load_profiled_yaml(
            self.settings_path,
            self.profile,
            label=self.label,
            merge_fn=self.merge_fn,
            env_var=self.env_var,
        )

    @property
    def raw(self) -> ConfigDict:
        return copy.deepcopy(self._raw)

    def _mapping(self, key: str) -> ConfigDict:
        raw = self._raw.get(key, {})
        return raw if isinstance(raw, dict) else {}
