"""Stable media-domain errors surfaced through service boundaries."""

from __future__ import annotations


class MediaError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


class MediaSourceChangedError(MediaError):
    def __init__(self) -> None:
        super().__init__(
            "MEDIA_SOURCE_CHANGED",
            "The selected turns changed after the visual brief was created.",
        )


class MediaSourceRangeError(ValueError):
    """The selected persisted turns do not satisfy Media source policy."""


class MediaProviderUnavailableError(MediaError):
    def __init__(self, provider_key: str) -> None:
        super().__init__(
            "MEDIA_PROVIDER_UNAVAILABLE",
            f"Media provider is unavailable: {provider_key}",
        )


class MediaInvalidImageError(MediaError):
    def __init__(self, message: str) -> None:
        super().__init__("MEDIA_INVALID_IMAGE", message)


class MediaGenerationCancelled(MediaError):
    def __init__(self) -> None:
        super().__init__("MEDIA_JOB_CANCELLED", "Media generation was cancelled.")


class MediaAssetInUseDomainError(MediaError):
    def __init__(self, asset_id: str) -> None:
        super().__init__(
            "MEDIA_ASSET_IN_USE",
            f"Media asset is still used by a typed binding: {asset_id}",
        )


class MediaImageAnalysisUnsupportedError(MediaError):
    def __init__(self) -> None:
        super().__init__(
            "MEDIA_IMAGE_ANALYSIS_UNSUPPORTED",
            "The configured LLM provider does not support image input.",
        )


class MediaImageAnalysisFailedError(MediaError):
    def __init__(self, message: str) -> None:
        super().__init__("MEDIA_IMAGE_ANALYSIS_FAILED", str(message))


class MediaVisualBriefFailedError(MediaError):
    def __init__(self, message: str) -> None:
        super().__init__("MEDIA_VISUAL_BRIEF_FAILED", str(message))
