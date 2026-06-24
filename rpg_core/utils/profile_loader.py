"""Helpers for loading ``base + profiles`` YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from rpg_core.common_types import ConfigDict, ConfigValue
from rpg_core.utils.config_values import optional_bool

YamlMergeFn = Callable[[ConfigDict, ConfigDict], ConfigDict]


def load_yaml_mapping(path: Path, label: str) -> ConfigDict:
    with path.open(encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a mapping")
    return loaded


def deep_merge_dicts(base: ConfigDict, override: ConfigDict) -> ConfigDict:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_profile_override(
    base_path: Path,
    profile_name: str,
    profile: ConfigValue,
    *,
    label: str,
    merge_fn: YamlMergeFn = deep_merge_dicts,
) -> ConfigDict:
    """Resolve a profile definition into a merged override mapping."""
    if profile is None:
        return {}
    if isinstance(profile, str):
        return load_profile_file(base_path, profile_name, profile, required=False, label=label)
    if not isinstance(profile, dict):
        raise ValueError(f"{label} profile must be a mapping or file path: {profile_name}")

    file_value = profile.get("file")
    required = optional_bool(profile.get("required", False), False)
    inline = {
        key: value
        for key, value in profile.items()
        if key not in {"file", "required"}
    }
    if file_value is None:
        return inline
    if not isinstance(file_value, str) or not file_value.strip():
        raise ValueError(f"{label} profile file must be a non-empty string: {profile_name}")
    file_override = load_profile_file(base_path, profile_name, file_value, required=required, label=label)
    return merge_fn(inline, file_override)


def load_profile_file(
    base_path: Path,
    profile_name: str,
    file_value: str,
    *,
    required: bool,
    label: str,
) -> ConfigDict:
    path = Path(file_value).expanduser()
    if not path.is_absolute():
        path = base_path.parent / path
    if not path.is_file():
        if required:
            raise ValueError(f"{label} profile file not found: profile={profile_name} file={path}")
        return {}
    return load_yaml_mapping(path, f"{label} profile file: {profile_name}")


def load_profiled_yaml(
    path: Path,
    profile_name: str,
    *,
    label: str,
    merge_fn: YamlMergeFn = deep_merge_dicts,
) -> ConfigDict:
    """Load and merge a base/profile YAML config file."""
    loaded = load_yaml_mapping(path, label)
    base = loaded.get("base", {})
    if not isinstance(base, dict):
        raise ValueError(f"{label} base must be a mapping")
    profiles = loaded.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError(f"{label} profiles must be a mapping")
    if profile_name not in profiles:
        raise ValueError(f"{label} profile not found: {profile_name}")
    profile = resolve_profile_override(path, profile_name, profiles.get(profile_name), label=label, merge_fn=merge_fn)
    return merge_fn(base, profile)
