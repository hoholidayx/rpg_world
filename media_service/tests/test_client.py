from __future__ import annotations

import httpx
import pytest

from media_service.client import MediaClient


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
