"""Local demo provider that samples a configured PNG/JPEG/WebP directory."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rpg_media.errors import MediaGenerationCancelled
from rpg_media.providers.base import CancellationProbe
from rpg_media.providers.selection import FileSelectionStrategy, RandomFileSelectionStrategy
from rpg_media.types import GeneratedImage, MediaGenerationRequest, MediaProviderDescriptor

_SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


class LocalFileProvider:
    def __init__(
        self,
        source_dir: str | Path,
        *,
        enabled: bool = True,
        selection_strategy: FileSelectionStrategy | None = None,
    ) -> None:
        self._source_dir = Path(source_dir).expanduser().resolve()
        self._enabled = bool(enabled)
        self._selection_strategy = selection_strategy or RandomFileSelectionStrategy()

    @property
    def descriptor(self) -> MediaProviderDescriptor:
        candidates = self._candidates() if self._enabled else ()
        if not self._enabled:
            reason = "Disabled by media configuration."
        elif not self._source_dir.is_dir():
            reason = f"Configured source directory does not exist: {self._source_dir}"
        elif not candidates:
            reason = "Configured source directory contains no PNG/JPEG/WebP images."
        else:
            reason = ""
        return MediaProviderDescriptor(
            key="local_file",
            display_name="Local file demo",
            kind="local_file",
            available=bool(candidates),
            reason=reason,
        )

    async def generate(
        self,
        request: MediaGenerationRequest,
        *,
        is_cancelled: CancellationProbe,
    ) -> GeneratedImage:
        if await is_cancelled():
            raise MediaGenerationCancelled()
        candidates = self._candidates()
        selected = self._selection_strategy.select(candidates)
        data = await asyncio.to_thread(selected.read_bytes)
        if await is_cancelled():
            raise MediaGenerationCancelled()
        return GeneratedImage(
            data=data,
            provider_asset_id=str(selected),
            metadata={"sourceFile": selected.name},
        )

    def _candidates(self) -> tuple[Path, ...]:
        if not self._enabled or not self._source_dir.is_dir():
            return ()
        return tuple(
            sorted(
                path
                for path in self._source_dir.iterdir()
                if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES
            )
        )
