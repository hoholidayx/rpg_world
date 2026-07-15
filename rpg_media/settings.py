"""Typed settings for the framework-free media domain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DemoBriefSettings:
    scene_description_prefix: str = "依据所选剧情还原这一幕："
    environment: str = "沉浸式奇幻角色扮演场景"
    composition: str = "电影感广角构图，主体与环境层次清晰"
    mood_lighting: str = "叙事性光影，氛围浓郁但细节可辨"
    style: str = "高质量电影概念艺术"
    negative_constraints: str = "文字，水印，标志，界面元素，低清晰度"
    aspect_ratio: str = "16:9"


@dataclass(frozen=True)
class LocalFileProviderSettings:
    enabled: bool = True
    source_dir: Path = _PROJECT_ROOT / "data" / "media_provider"


@dataclass(frozen=True)
class ProviderScaffoldSettings:
    enabled: bool = False


@dataclass(frozen=True)
class MediaProviderSettings:
    default_key: str
    local_file: LocalFileProviderSettings
    hosted_api: ProviderScaffoldSettings
    comfyui: ProviderScaffoldSettings


class RPGMediaSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "rpg_media/settings.yaml"
        super().__init__(profile_name)

    @property
    def demo_brief(self) -> DemoBriefSettings:
        raw = self._mapping("brief_planner").get("demo", {})
        if not isinstance(raw, dict):
            raw = {}
        return DemoBriefSettings(
            scene_description_prefix=str(
                raw.get("scene_description_prefix", "依据所选剧情还原这一幕：")
            ),
            environment=str(raw.get("environment", "沉浸式奇幻角色扮演场景")),
            composition=str(
                raw.get("composition", "电影感广角构图，主体与环境层次清晰")
            ),
            mood_lighting=str(
                raw.get("mood_lighting", "叙事性光影，氛围浓郁但细节可辨")
            ),
            style=str(raw.get("style", "高质量电影概念艺术")),
            negative_constraints=str(
                raw.get("negative_constraints", "文字，水印，标志，界面元素，低清晰度")
            ),
            aspect_ratio=str(raw.get("aspect_ratio", "16:9")),
        )

    @property
    def providers(self) -> MediaProviderSettings:
        raw = self._mapping("providers")
        local_raw = raw.get("local_file", {})
        hosted_raw = raw.get("hosted_api", {})
        comfy_raw = raw.get("comfyui", {})
        if not isinstance(local_raw, dict):
            local_raw = {}
        if not isinstance(hosted_raw, dict):
            hosted_raw = {}
        if not isinstance(comfy_raw, dict):
            comfy_raw = {}
        configured_dir = Path(
            str(local_raw.get("source_dir", "data/media_provider"))
        ).expanduser()
        if not configured_dir.is_absolute():
            configured_dir = (_PROJECT_ROOT / configured_dir).resolve()
        return MediaProviderSettings(
            default_key=str(raw.get("default_key", "local_file") or "local_file"),
            local_file=LocalFileProviderSettings(
                enabled=optional_bool(local_raw.get("enabled", True), True),
                source_dir=configured_dir,
            ),
            hosted_api=ProviderScaffoldSettings(
                enabled=optional_bool(hosted_raw.get("enabled", False), False)
            ),
            comfyui=ProviderScaffoldSettings(
                enabled=optional_bool(comfy_raw.get("enabled", False), False)
            ),
        )


settings = RPGMediaSettings()
