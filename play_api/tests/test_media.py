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
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
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


class _FakeMediaClient:
    async def aclose(self) -> None:
        return None

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
        return MediaBackgroundResponse(background=_asset())

    async def set_background(self, session_id, body):  # noqa: ANN001, ANN201
        return MediaBackgroundResponse(background=_asset())

    async def clear_background(self, session_id: str) -> MediaBackgroundResponse:
        return MediaBackgroundResponse(background=None)

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


def test_media_business_error_is_preserved(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _InUseMediaClient())
    with TestClient(app) as client:
        response = client.delete(
            "/play-api/v1/sessions/s_forest001/media/assets/asset1"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["errorCode"] == "MEDIA_ASSET_IN_USE"
