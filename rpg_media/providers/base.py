"""Provider contracts kept independent from HTTP and worker frameworks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from rpg_media.types import GeneratedImage, MediaGenerationRequest, MediaProviderDescriptor

CancellationProbe = Callable[[], Awaitable[bool]]


class ImageProvider(Protocol):
    @property
    def descriptor(self) -> MediaProviderDescriptor: ...

    async def generate(
        self,
        request: MediaGenerationRequest,
        *,
        is_cancelled: CancellationProbe,
    ) -> GeneratedImage: ...
