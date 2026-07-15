"""Static built-in provider catalog; no third-party code loading."""

from __future__ import annotations

from rpg_media.errors import MediaProviderUnavailableError
from rpg_media.providers.base import ImageProvider
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.providers.scaffolds import ScaffoldImageProvider
from rpg_media.settings import MediaProviderSettings
from rpg_media.types import MediaProviderDescriptor


class MediaProviderCatalog:
    def __init__(self, providers: tuple[ImageProvider, ...], *, default_key: str) -> None:
        self._providers = {provider.descriptor.key: provider for provider in providers}
        self.default_key = str(default_key)
        if self.default_key not in self._providers:
            raise ValueError(f"unknown default media provider: {self.default_key}")

    def list(self) -> list[MediaProviderDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]

    def get(self, provider_key: str) -> ImageProvider | None:
        return self._providers.get(str(provider_key))

    def require_available(self, provider_key: str) -> ImageProvider:
        provider = self.get(provider_key)
        if provider is None or not provider.descriptor.available:
            raise MediaProviderUnavailableError(str(provider_key))
        return provider


def build_provider_catalog(config: MediaProviderSettings) -> MediaProviderCatalog:
    return MediaProviderCatalog(
        (
            LocalFileProvider(
                config.local_file.source_dir,
                enabled=config.local_file.enabled,
            ),
            ScaffoldImageProvider(
                key="hosted_api",
                display_name="Hosted image API",
                kind="hosted_api",
            ),
            ScaffoldImageProvider(
                key="comfyui",
                display_name="ComfyUI",
                kind="comfyui",
            ),
        ),
        default_key=config.default_key,
    )
