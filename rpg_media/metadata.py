"""Image metadata recognition through the standalone LLM service."""

from __future__ import annotations

import base64
from typing import Protocol

from llm_client.client import LLMServiceClientError, LLMServiceRemoteError
from llm_client.keys import MEDIA_IMAGE_METADATA_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMProvider
from rpg_media.errors import (
    MediaImageAnalysisFailedError,
    MediaImageAnalysisUnsupportedError,
)
from rpg_media.structured_output import parse_json_object
from rpg_media.types import InspectedImage, MediaImageMetadata


class ImageMetadataAnalyzer(Protocol):
    async def analyze(self, image: InspectedImage) -> MediaImageMetadata: ...


class LLMImageMetadataAnalyzer:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    async def analyze(self, image: InspectedImage) -> MediaImageMetadata:
        try:
            provider = self._provider or await self._resolve_provider()
            encoded = base64.b64encode(image.data).decode("ascii")
            result = await provider.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "识别这张图片并输出可编辑的媒体库元数据。",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image.mime_type};base64,{encoded}",
                                },
                            },
                        ],
                    },
                ]
            )
            payload = parse_json_object(result.content, label="image metadata response")
            return MediaImageMetadata.from_mapping(payload)
        except MediaImageAnalysisUnsupportedError:
            raise
        except LLMServiceRemoteError as exc:
            if exc.error_code == "LLM_INPUT_MODALITY_UNSUPPORTED":
                raise MediaImageAnalysisUnsupportedError() from exc
            raise MediaImageAnalysisFailedError(str(exc)) from exc
        except LLMServiceClientError as exc:
            raise MediaImageAnalysisFailedError(str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise MediaImageAnalysisFailedError(str(exc)) from exc

    @staticmethod
    async def _resolve_provider() -> LLMProvider:
        manager = LLMClientManager.get()
        catalog = await manager.get_catalog(MEDIA_IMAGE_METADATA_BIZ_KEY)
        if not catalog.option().supports_input_modality("image"):
            raise MediaImageAnalysisUnsupportedError()
        return await manager.get_provider(MEDIA_IMAGE_METADATA_BIZ_KEY)


_SYSTEM_PROMPT = """
你是媒体库图片识别助手。只依据图片中可见内容生成中文元数据，不猜测真实人物身份、隐私或图片外事实。
标题应简洁明确；描述应适合后续场景匹配；Tags 使用 1–20 个短词，覆盖地点、时段、天气、风格、色调和显著主体。
只输出严格 JSON，不要 Markdown、解释或额外字段：
{"title":"...","description":"...","tags":["...","..."]}
""".strip()
