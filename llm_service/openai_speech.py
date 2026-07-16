"""OpenAI speech provider owned by the standalone LLM service."""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass(frozen=True)
class SpeechProfile:
    provider_key: str
    model: str
    voice: str
    response_format: str
    speed: float
    cache_revision: str
    config_fingerprint: str


class OpenAISpeechProvider:
    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        profile: SpeechProfile,
    ) -> None:
        self._client = client
        self.profile = profile

    async def synthesize(self, text: str) -> bytes:
        response = await self._client.audio.speech.create(
            model=self.profile.model,
            voice=self.profile.voice,  # type: ignore[arg-type]
            input=text,
            response_format=self.profile.response_format,  # type: ignore[arg-type]
            speed=self.profile.speed,
        )
        return bytes(response.content)
