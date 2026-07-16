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
