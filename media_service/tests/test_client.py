from __future__ import annotations

import json

import httpx
import pytest

from media_service.client import MediaClient
from media_service.schemas import MediaJobRetryRequest, VisualBriefSchema


def _job_payload(*, user_prompt: str = "") -> dict[str, object]:
    return {
        "jobId": "job-retry",
        "sessionId": "session1",
        "providerKey": "local_file",
        "status": "queued",
        "startTurnId": 1,
        "endTurnId": 2,
        "sourceFingerprint": "a" * 64,
        "visualBrief": {
            "sceneDescription": "雨夜咖啡馆",
            "subjects": ["言沁", "夏澄"],
            "environment": "临窗座",
            "action": "雨中对视",
            "composition": "中景",
            "moodLighting": "暖色灯光",
            "style": "动画电影",
            "negativeConstraints": "文字、水印",
            "aspectRatio": "16:9",
            "userPrompt": user_prompt,
        },
        "generationParams": {"seed": 17},
        "outputAssetId": None,
        "retryOfJobId": "job-original",
        "errorCode": "",
        "errorMessage": "",
        "createdAt": "now",
        "updatedAt": "now",
        "startedAt": "",
        "finishedAt": "",
    }


@pytest.mark.asyncio
async def test_media_client_reconcile_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/media/v1/workspaces/demo_workspace/library/reconcile"
        return httpx.Response(
            200,
            json={
                "workspaceId": "demo_workspace",
                "scannedBlobs": 4,
                "removedBlobs": 1,
                "removedAssets": 2,
                "removedLibraryItems": 2,
                "removedGalleryItems": 1,
                "clearedBackgrounds": 1,
            },
        )

    client = MediaClient(base_url="http://media.test/media/v1")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.reconcile_library_assets("demo_workspace")
    finally:
        await client.aclose()

    assert result.workspace_id == "demo_workspace"
    assert result.scanned_blobs == 4
    assert result.removed_assets == 2
    assert result.cleared_backgrounds == 1


@pytest.mark.asyncio
async def test_media_client_image_analysis_multipart_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/media/v1/workspaces/demo_workspace/library/analyze"
        body = await request.aread()
        assert b'filename="forest.png"' in body
        assert b"png-bytes" in body
        return httpx.Response(
            200,
            json={
                "title": "Forest",
                "description": "Moonlit forest",
                "tags": ["forest", "night"],
            },
        )

    client = MediaClient(base_url="http://media.test/media/v1")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.analyze_library_image(
            "demo_workspace",
            filename="forest.png",
            content_type="image/png",
            content=b"png-bytes",
        )
    finally:
        await client.aclose()

    assert result.title == "Forest"
    assert result.tags == ["forest", "night"]


@pytest.mark.asyncio
async def test_media_client_retry_supports_empty_and_edited_body() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.method == "POST"
        assert request.url.path == "/media/v1/sessions/session1/jobs/job-original/retry"
        if request_count == 1:
            assert request.content == b""
            return httpx.Response(200, json=_job_payload())

        payload = json.loads(request.content)
        assert payload["visualBrief"]["style"] == "动画电影"
        assert payload["visualBrief"]["userPrompt"] == "必须保持角色金色眼睛"
        return httpx.Response(
            200,
            json=_job_payload(user_prompt="必须保持角色金色眼睛"),
        )

    client = MediaClient(base_url="http://media.test/media/v1")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        direct = await client.retry_job("session1", "job-original")
        edited = await client.retry_job(
            "session1",
            "job-original",
            MediaJobRetryRequest(
                visualBrief=VisualBriefSchema(
                    sceneDescription="雨夜咖啡馆",
                    subjects=["言沁", "夏澄"],
                    environment="临窗座",
                    action="雨中对视",
                    composition="中景",
                    moodLighting="暖色灯光",
                    style="动画电影",
                    negativeConstraints="文字、水印",
                    aspectRatio="16:9",
                    userPrompt="必须保持角色金色眼睛",
                )
            ),
        )
    finally:
        await client.aclose()

    assert request_count == 2
    assert direct.visual_brief.user_prompt == ""
    assert edited.visual_brief.user_prompt == "必须保持角色金色眼睛"
