from __future__ import annotations

from fastapi.testclient import TestClient

from media_service.client import (
    MediaClientError,
    MediaContentStream,
    MediaServiceUnavailable,
)
from media_service.schemas import (
    MediaAssetDeleteResponse,
    MediaBackgroundResponse,
    MediaBackgroundEvaluationResponse,
    MediaDisplayAssetResponse,
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
    MediaLibraryDeleteResponse,
    MediaLibraryBatchResponse,
    MediaLibraryFacetValueResponse,
    MediaLibraryFacetsResponse,
    MediaLibraryStoryFacetResponse,
    MediaImageMetadataResponse,
    MediaLibraryItemResponse,
    MediaLibraryReconcileResponse,
    MediaLibraryResponse,
    MediaJobResponse,
    MediaProviderCatalogResponse,
    MediaProviderResponse,
    MediaSourceReferenceResponse,
    MediaSourceTurnResponse,
    MediaSourceTurnsResponse,
    VisualBriefSchema,
)
from play_api import media_client
from play_api.main import app
from rpg_data.services import reset_data_service_gateways


def _brief() -> VisualBriefSchema:
    return VisualBriefSchema(sceneDescription="forest", aspectRatio="16:9")


def _job(status: str = "queued") -> MediaJobResponse:
    return MediaJobResponse(
        jobId="job1",
        sessionId="s_forest001",
        providerKey="local_file",
        status=status,
        startTurnId=1,
        endTurnId=1,
        sourceFingerprint="a" * 64,
        visualBrief=_brief(),
        generationParams={},
        outputAssetId=None,
        retryOfJobId=None,
        errorCode="",
        errorMessage="",
        createdAt="now",
        updatedAt="now",
        startedAt="",
        finishedAt="",
    )


def _asset() -> MediaGalleryItemResponse:
    return MediaGalleryItemResponse(
        assetId="asset1",
        jobId="job1",
        providerKey="local_file",
        sha256="b" * 64,
        mimeType="image/png",
        byteSize=12,
        visualBrief=_brief(),
        source=MediaSourceReferenceResponse(
            startTurnId=1,
            endTurnId=1,
            fingerprint="a" * 64,
            stale=False,
        ),
        createdAt="now",
    )


def _library_item() -> MediaLibraryItemResponse:
    return MediaLibraryItemResponse(
        itemId="item1",
        assetId="library-asset1",
        workspaceId="demo_workspace",
        scope="story",
        storyId=1,
        mediaType="background",
        title="Forest",
        description="Moonlit forest",
        tags=["forest", "night"],
        isDefault=True,
        origin="upload",
        mimeType="image/png",
        byteSize=9,
        backgroundReferences=0,
        galleryReferences=0,
        createdAt="now",
        updatedAt="now",
    )


def _evaluation(status: str = "queued") -> MediaBackgroundEvaluationResponse:
    return MediaBackgroundEvaluationResponse(
        evaluationId="evaluation1",
        sessionId="s_forest001",
        status=status,
        targetTurnId=1,
        decision="",
        selectedAssetId=None,
        reason="",
        errorCode="",
        errorMessage="",
        createdAt="now",
        updatedAt="now",
        startedAt="",
        finishedAt="",
    )


class _FakeMediaClient:
    async def aclose(self) -> None:
        return None

    async def list_library_assets(self, workspace_id, **kwargs):  # noqa: ANN001, ANN201
        assert workspace_id == "demo_workspace"
        return MediaLibraryResponse(items=[_library_item()], page=1, pageSize=48, total=1)

    async def reconcile_library_assets(self, workspace_id):  # noqa: ANN001, ANN201
        assert workspace_id == "demo_workspace"
        return MediaLibraryReconcileResponse(
            workspaceId=workspace_id,
            scannedBlobs=3,
            removedBlobs=1,
            removedAssets=2,
            removedLibraryItems=2,
            removedGalleryItems=1,
            clearedBackgrounds=1,
        )

    async def get_library_facets(self, workspace_id):  # noqa: ANN001, ANN201
        return MediaLibraryFacetsResponse(
            mediaTypes=[MediaLibraryFacetValueResponse(value="background", count=1)],
            tags=[MediaLibraryFacetValueResponse(value="forest", count=1)],
            scopes=[MediaLibraryFacetValueResponse(value="story", count=1)],
            origins=[MediaLibraryFacetValueResponse(value="upload", count=1)],
            stories=[MediaLibraryStoryFacetResponse(storyId=1, count=1)],
        )

    async def batch_update_library_assets(self, workspace_id, body):  # noqa: ANN001, ANN201
        return MediaLibraryBatchResponse(succeededItemIds=body.item_ids, failed=[])

    async def batch_delete_library_assets(self, workspace_id, body):  # noqa: ANN001, ANN201
        return MediaLibraryBatchResponse(succeededItemIds=body.item_ids, failed=[])

    async def analyze_library_image(self, workspace_id, **kwargs):  # noqa: ANN001, ANN201
        assert workspace_id == "demo_workspace"
        assert kwargs["content"] == b"png-bytes"
        return MediaImageMetadataResponse(
            title="Forest",
            description="Moonlit forest",
            tags=["forest", "night"],
        )

    async def upload_library_asset(self, workspace_id, **kwargs):  # noqa: ANN001, ANN201
        assert kwargs["content"] == b"png-bytes"
        assert kwargs["tags"] == ["forest", "night"]
        return _library_item()

    async def update_library_asset(self, workspace_id, item_id, body):  # noqa: ANN001, ANN201
        return _library_item()

    async def delete_library_asset(self, workspace_id, item_id):  # noqa: ANN001, ANN201
        return MediaLibraryDeleteResponse(itemId=item_id, deleted=True)

    async def stream_library_asset_content(self, workspace_id, item_id):  # noqa: ANN001, ANN201
        async def chunks():  # noqa: ANN202
            yield b"png-bytes"

        return MediaContentStream(
            media_type="image/png",
            content_length=9,
            chunks=chunks(),
        )

    async def list_providers(self, session_id: str) -> MediaProviderCatalogResponse:
        assert session_id == "s_forest001"
        return MediaProviderCatalogResponse(
            defaultKey="local_file",
            providers=[
                MediaProviderResponse(
                    key="local_file",
                    displayName="Local",
                    kind="local_file",
                    available=True,
                )
            ],
        )

    async def list_source_turns(self, session_id: str) -> MediaSourceTurnsResponse:
        return MediaSourceTurnsResponse(
            turns=[
                MediaSourceTurnResponse(
                    turnId=1,
                    roles=["user", "assistant"],
                    preview="preview",
                    messageCount=2,
                )
            ]
        )

    async def create_brief(self, session_id, body):  # noqa: ANN001, ANN201
        return MediaBriefResponse(
            startTurnId=body.start_turn_id,
            endTurnId=body.end_turn_id,
            sourceFingerprint="a" * 64,
            brief=_brief(),
        )

    async def create_job(self, session_id, body):  # noqa: ANN001, ANN201
        return _job()

    async def get_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return _job("running")

    async def cancel_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return _job("cancelling")

    async def retry_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return _job("queued")

    async def get_gallery(self, session_id: str) -> MediaGalleryResponse:
        return MediaGalleryResponse(items=[_asset()], activeJobs=[_job()], recentJobs=[_job()])

    async def get_background(self, session_id: str) -> MediaBackgroundResponse:
        return MediaBackgroundResponse(
            background=MediaDisplayAssetResponse(
                assetId="asset1",
                origin="generated",
                mimeType="image/png",
                byteSize=12,
                title="forest",
                tags=[],
                createdAt="now",
            ),
            sourceMode="manual",
            manualLocked=True,
            revisionToken="manual:1:asset1",
        )

    async def set_background(self, session_id, body):  # noqa: ANN001, ANN201
        return await self.get_background(session_id)

    async def clear_background(self, session_id: str) -> MediaBackgroundResponse:
        return MediaBackgroundResponse(
            background=None,
            sourceMode="none",
            manualLocked=False,
            revisionToken="none:2",
        )

    async def queue_background_evaluation(self, session_id, body):  # noqa: ANN001, ANN201
        return _evaluation()

    async def get_background_evaluation(self, session_id, evaluation_id):  # noqa: ANN001, ANN201
        return _evaluation("succeeded")

    async def get_asset(self, session_id: str, asset_id: str) -> MediaGalleryItemResponse:
        return _asset()

    async def delete_asset(self, session_id: str, asset_id: str) -> MediaAssetDeleteResponse:
        return MediaAssetDeleteResponse(assetId=asset_id, deleted=True)

    async def stream_asset_content(
        self,
        session_id: str,
        asset_id: str,
    ) -> MediaContentStream:
        async def chunks():  # noqa: ANN202
            yield b"png-"
            yield b"bytes"

        return MediaContentStream(
            media_type="image/png",
            content_length=9,
            chunks=chunks(),
        )


def _prepare(tmp_path, monkeypatch, fake) -> None:  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "play.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    monkeypatch.setattr(media_client, "_client", fake)


def test_play_media_proxy_contract_and_content_stream(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _FakeMediaClient())
    with TestClient(app) as client:
        providers = client.get(
            "/play-api/v1/sessions/s_forest001/media/providers"
        )
        assert providers.status_code == 200
        assert providers.json()["defaultKey"] == "local_file"

        brief = client.post(
            "/play-api/v1/sessions/s_forest001/media/briefs",
            json={"startTurnId": 1, "endTurnId": 1},
        )
        assert brief.status_code == 200
        assert brief.json()["sourceFingerprint"] == "a" * 64

        gallery = client.get(
            "/play-api/v1/sessions/s_forest001/media/gallery"
        )
        assert gallery.status_code == 200
        assert gallery.json()["items"][0]["assetId"] == "asset1"

        content = client.get(
            "/play-api/v1/sessions/s_forest001/media/assets/asset1/content"
        )
        assert content.status_code == 200
        assert content.content == b"png-bytes"
        assert content.headers["content-type"].startswith("image/png")
        assert content.headers["x-content-type-options"] == "nosniff"

        library = client.get(
            "/play-api/v1/workspaces/demo_workspace/media/library",
            params={"scope": "story", "storyId": 1},
        )
        assert library.status_code == 200
        assert library.json()["items"][0]["itemId"] == "item1"

        facets = client.get(
            "/play-api/v1/workspaces/demo_workspace/media/library/facets"
        )
        assert facets.status_code == 200
        assert facets.json()["mediaTypes"] == [{"value": "background", "count": 1}]

        batch_updated = client.patch(
            "/play-api/v1/workspaces/demo_workspace/media/library/batch",
            json={"itemIds": ["item1"], "mediaType": "avatar"},
        )
        assert batch_updated.status_code == 200
        assert batch_updated.json()["succeededItemIds"] == ["item1"]

        batch_deleted = client.post(
            "/play-api/v1/workspaces/demo_workspace/media/library/batch-delete",
            json={"itemIds": ["item1"]},
        )
        assert batch_deleted.status_code == 200

        reconciled = client.post(
            "/play-api/v1/workspaces/demo_workspace/media/library/reconcile"
        )
        assert reconciled.status_code == 200
        assert reconciled.json()["scannedBlobs"] == 3
        assert reconciled.json()["removedAssets"] == 2
        assert reconciled.json()["clearedBackgrounds"] == 1

        analyzed = client.post(
            "/play-api/v1/workspaces/demo_workspace/media/library/analyze",
            files={"file": ("forest.png", b"png-bytes", "image/png")},
        )
        assert analyzed.status_code == 200
        assert analyzed.json()["tags"] == ["forest", "night"]

        uploaded = client.post(
            "/play-api/v1/workspaces/demo_workspace/media/library",
            data={
                "scope": "story",
                "mediaType": "background",
                "storyId": "1",
                "title": "Forest",
                "description": "Moonlit forest",
                "tags": '["forest", "night"]',
                "isDefault": "true",
            },
            files={"file": ("forest.png", b"png-bytes", "image/png")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["assetId"] == "library-asset1"

        library_content = client.get(
            "/play-api/v1/workspaces/demo_workspace/media/library/item1/content"
        )
        assert library_content.status_code == 200
        assert library_content.content == b"png-bytes"

        queued = client.post(
            "/play-api/v1/sessions/s_forest001/media/background-evaluations",
            json={"observedTurnId": 1},
        )
        assert queued.status_code == 200
        assert queued.json()["evaluationId"] == "evaluation1"


class _UnavailableMediaClient(_FakeMediaClient):
    async def list_providers(self, session_id: str) -> MediaProviderCatalogResponse:
        raise MediaServiceUnavailable("offline")


def test_media_outage_maps_to_503(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _UnavailableMediaClient())
    with TestClient(app) as client:
        response = client.get(
            "/play-api/v1/sessions/s_forest001/media/providers"
        )
        assert response.status_code == 503
        assert response.json()["detail"]["errorCode"] == "MEDIA_SERVICE_UNAVAILABLE"


class _InUseMediaClient(_FakeMediaClient):
    async def delete_asset(self, session_id: str, asset_id: str) -> MediaAssetDeleteResponse:
        raise MediaClientError(
            "in use",
            status_code=409,
            error_code="MEDIA_ASSET_IN_USE",
        )


class _UnsupportedAnalysisMediaClient(_FakeMediaClient):
    async def analyze_library_image(self, workspace_id, **kwargs):  # noqa: ANN001, ANN201
        raise MediaClientError(
            "no image support",
            status_code=422,
            error_code="MEDIA_IMAGE_ANALYSIS_UNSUPPORTED",
        )


def test_media_business_error_is_preserved(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _InUseMediaClient())
    with TestClient(app) as client:
        response = client.delete(
            "/play-api/v1/sessions/s_forest001/media/assets/asset1"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["errorCode"] == "MEDIA_ASSET_IN_USE"


def test_media_image_analysis_unsupported_is_preserved(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _UnsupportedAnalysisMediaClient())
    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/workspaces/demo_workspace/media/library/analyze",
            files={"file": ("forest.png", b"png-bytes", "image/png")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["errorCode"] == "MEDIA_IMAGE_ANALYSIS_UNSUPPORTED"
