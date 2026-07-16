from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commons.settings import ProfiledYamlSettings, forgiving_int

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"


@dataclass(frozen=True)
class TTSSynthesisSettings:
    biz_key: str = "tts.reply"
    normalization_revision: str = "rp-text-v1"
    max_chars_per_part: int = 1800


class RPGTTSSettings(ProfiledYamlSettings):
    def __init__(self, profile_name: str | None = None) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "rpg_tts/settings.yaml"
        super().__init__(profile_name)

    @property
    def synthesis(self) -> TTSSynthesisSettings:
        raw = self._mapping("synthesis")
        biz_key = str(raw.get("biz_key", "tts.reply") or "tts.reply").strip()
        revision = str(
            raw.get("normalization_revision", "rp-text-v1") or "rp-text-v1"
        ).strip()
        if not biz_key or not revision:
            raise ValueError("TTS biz_key and normalization_revision are required")
        return TTSSynthesisSettings(
            biz_key=biz_key,
            normalization_revision=revision,
            max_chars_per_part=min(
                4096,
                max(
                    100,
                    forgiving_int(raw.get("max_chars_per_part", 1800), 1800),
                ),
            ),
        )


settings = RPGTTSSettings()
