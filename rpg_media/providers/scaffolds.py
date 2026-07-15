"""Non-network provider placeholders advertised by the v1 capability catalog."""

from __future__ import annotations

from rpg_media.errors import MediaProviderUnavailableError
from rpg_media.providers.base import CancellationProbe
from rpg_media.types import GeneratedImage, MediaGenerationRequest, MediaProviderDescriptor


class ScaffoldImageProvider:
    def __init__(self, *, key: str, display_name: str, kind: str) -> None:
        self._descriptor = MediaProviderDescriptor(
            key=key,
            display_name=display_name,
            kind=kind,
            available=False,
            reason="Catalog scaffold only; network generation is not implemented in v1.",
        )

    @property
    def descriptor(self) -> MediaProviderDescriptor:
        return self._descriptor

    async def generate(
        self,
        request: MediaGenerationRequest,
        *,
        is_cancelled: CancellationProbe,
    ) -> GeneratedImage:
        raise MediaProviderUnavailableError(self._descriptor.key)
