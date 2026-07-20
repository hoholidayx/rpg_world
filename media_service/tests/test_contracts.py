from __future__ import annotations

import time

from fastapi.testclient import TestClient

from media_service.main import MediaRuntime, app, set_runtime_for_tests
from media_service.worker import MediaJobWorker
from rpg_core.scene.status import SceneStatusService
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.errors import MediaImageAnalysisUnsupportedError
from rpg_media.service import MediaApplicationService
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.types import MediaBackgroundDecision, MediaImageMetadata

PNG = b"\x89PNG\r\n\x1a\nservice"


class _LibraryMatcher:
    def __init__(self, data) -> None:  # noqa: ANN001
        self._data = data

    async def decide(self, source):  # noqa: ANN001, ANN201
        items = self._data.list_library_assets(
            source.workspace_id,
            scope=models.MEDIA_LIBRARY_SCOPE_STORY,
            story_id=source.story_id,
        )
        if not items:
            return MediaBackgroundDecision(decision="keep", reason="no candidate")
        return MediaBackgroundDecision(
            decision="switch",
            asset_id=items[0].asset.id,
            reason="scene changed",
        )


class _ImageAnalyzer:
    async def analyze(self, image):  # noqa: ANN001, ANN201
        assert image.mime_type == "image/png"
        return MediaImageMetadata(
            title="月光森林",
            description="月光照亮林间石门。",
            tags=("森林", "夜晚"),
        )


def _runtime(tmp_path, *, image_analyzer=None):  # noqa: ANN001, ANN202
    gateway = get_data_service_gateway(tmp_path / "service.sqlite3")
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(tmp_path / "workspace"),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="service")
    assert session is not None
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "月光下的森林入口",
        turn_id=1,
        seq_in_turn=1,
    )
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    (provider_dir / "image.png").write_bytes(PNG)
    service = MediaApplicationService(
        data=gateway.media,
        catalog=gateway.catalog,
        planner=DemoVisualBriefPlanner(),
        providers=MediaProviderCatalog(
            (LocalFileProvider(provider_dir),),
            default_key="local_file",
        ),
        status=SceneStatusService(gateway.status),
        background_matcher=_LibraryMatcher(gateway.media),
        image_analyzer=image_analyzer or _ImageAnalyzer(),
    )
    worker = MediaJobWorker(
        service=service,
        concurrency=1,
    )
    return gateway, session, message, MediaRuntime(
        gateway=gateway,
        service=service,
        worker=worker,
    )


def test_media_service_manual_generation_contract(tmp_path) -> None:
    gateway, session, _message, runtime = _runtime(tmp_path)
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            providers = client.get(
                f"/media/v1/sessions/{session.id}/providers"
            )
            assert providers.status_code == 200
            assert providers.json()["defaultKey"] == "local_file"
            assert providers.json()["providers"][0]["available"] is True

            turns = client.get(
                f"/media/v1/sessions/{session.id}/source-turns"
            )
            assert turns.status_code == 200
            assert turns.json()["shortcuts"] == [1, 5, 10, 20]
            assert turns.json()["turns"][0]["turnId"] == 1

            brief_response = client.post(
                f"/media/v1/sessions/{session.id}/briefs",
                json={"startTurnId": 1, "endTurnId": 1},
            )
            assert brief_response.status_code == 200
            brief_payload = brief_response.json()
            brief_payload["brief"]["style"] = "edited"

            created = client.post(
                f"/media/v1/sessions/{session.id}/jobs",
                json={
                    "providerKey": "local_file",
                    "startTurnId": 1,
                    "endTurnId": 1,
                    "sourceFingerprint": brief_payload["sourceFingerprint"],
                    "visualBrief": brief_payload["brief"],
                    "generationParams": {},
                },
            )
            assert created.status_code == 200
            job_id = created.json()["jobId"]

            job_payload = created.json()
            for _ in range(100):
                current = client.get(
                    f"/media/v1/sessions/{session.id}/jobs/{job_id}"
                )
                assert current.status_code == 200
                job_payload = current.json()
                if job_payload["status"] not in {"queued", "running", "cancelling"}:
                    break
                time.sleep(0.01)
            assert job_payload["status"] == "succeeded"

            retried = client.post(
                f"/media/v1/sessions/{session.id}/jobs/{job_id}/retry"
            )
            assert retried.status_code == 200
            retry_payload = retried.json()
            assert retry_payload["retryOfJobId"] == job_id
            retry_job_id = retry_payload["jobId"]
            for _ in range(100):
                current = client.get(
                    f"/media/v1/sessions/{session.id}/jobs/{retry_job_id}"
                )
                assert current.status_code == 200
                retry_payload = current.json()
                if retry_payload["status"] not in {"queued", "running", "cancelling"}:
                    break
                time.sleep(0.01)
            assert retry_payload["status"] == "succeeded"

            gallery = client.get(
                f"/media/v1/sessions/{session.id}/gallery"
            )
            assert gallery.status_code == 200
            gallery_payload = gallery.json()
            assert gallery_payload["activeJobs"] == []
            assert len(gallery_payload["items"]) == 2
            item = gallery_payload["items"][0]
            assert item["visualBrief"]["style"] == "edited"
            asset_id = item["assetId"]

            background = client.put(
                f"/media/v1/sessions/{session.id}/background",
                json={"assetId": asset_id},
            )
            assert background.status_code == 200
            assert background.json()["background"]["assetId"] == asset_id

            blocked = client.delete(
                f"/media/v1/sessions/{session.id}/assets/{asset_id}"
            )
            assert blocked.status_code == 409
            assert blocked.json()["detail"]["errorCode"] == "MEDIA_ASSET_IN_USE"

            content = client.get(
                f"/media/v1/sessions/{session.id}/assets/{asset_id}/content"
            )
            assert content.status_code == 200
            assert content.headers["content-type"].startswith("image/png")
            assert content.content == PNG

            cleared = client.delete(
                f"/media/v1/sessions/{session.id}/background"
            )
            assert cleared.status_code == 200
            deleted = client.delete(
                f"/media/v1/sessions/{session.id}/assets/{asset_id}"
            )
            assert deleted.status_code == 200
            assert deleted.json() == {"assetId": asset_id, "deleted": True}
    finally:
        set_runtime_for_tests(None)


def test_job_creation_returns_source_changed_error(tmp_path) -> None:
    gateway, session, message, runtime = _runtime(tmp_path)
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            brief = client.post(
                f"/media/v1/sessions/{session.id}/briefs",
                json={"startTurnId": 1, "endTurnId": 1},
            ).json()
            gateway.messages.update(message.id, content="source changed")
            response = client.post(
                f"/media/v1/sessions/{session.id}/jobs",
                json={
                    "startTurnId": 1,
                    "endTurnId": 1,
                    "sourceFingerprint": brief["sourceFingerprint"],
                    "visualBrief": brief["brief"],
                },
            )
            assert response.status_code == 409
            assert response.json()["detail"]["errorCode"] == "MEDIA_SOURCE_CHANGED"
    finally:
        set_runtime_for_tests(None)


def test_library_upload_and_async_background_contract(tmp_path) -> None:
    gateway, session, _message, runtime = _runtime(tmp_path)
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            analyzed = client.post(
                "/media/v1/workspaces/demo_workspace/library/analyze",
                files={"file": ("forest.png", PNG, "image/png")},
            )
            assert analyzed.status_code == 200
            assert analyzed.json() == {
                "title": "月光森林",
                "description": "月光照亮林间石门。",
                "tags": ["森林", "夜晚"],
            }
            assert gateway.media.list_workspace_blobs("demo_workspace") == []

            uploaded = client.post(
                "/media/v1/workspaces/demo_workspace/library",
                data={
                    "scope": "story",
                    "mediaType": "background",
                    "storyId": "1",
                    "title": "月光森林",
                    "description": "夜晚的森林入口，石门被月光照亮。",
                    "tags": '["森林", "夜晚"]',
                    "isDefault": "true",
                },
                files={"file": ("forest.png", PNG, "image/png")},
            )
            assert uploaded.status_code == 200
            item = uploaded.json()
            assert item["scope"] == "story"
            assert item["isDefault"] is True
            assert item["origin"] == "upload"
            assert set(item["tags"]) == {"夜晚", "森林"}

            library = client.get(
                "/media/v1/workspaces/demo_workspace/library",
                params={"scope": "story", "storyId": 1},
            )
            assert library.status_code == 200
            assert library.json()["items"][0]["itemId"] == item["itemId"]

            initial = client.get(f"/media/v1/sessions/{session.id}/background")
            assert initial.status_code == 200
            assert initial.json()["sourceMode"] == "story_default"
            assert initial.json()["background"]["assetId"] == item["assetId"]

            queued = client.post(
                f"/media/v1/sessions/{session.id}/background-evaluations",
                json={"observedTurnId": 1},
            )
            assert queued.status_code == 200
            evaluation_id = queued.json()["evaluationId"]
            evaluation = queued.json()
            for _ in range(100):
                response = client.get(
                    f"/media/v1/sessions/{session.id}/background-evaluations/{evaluation_id}"
                )
                assert response.status_code == 200
                evaluation = response.json()
                if evaluation["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)
            assert evaluation["status"] == "succeeded"
            assert evaluation["decision"] == "switch"

            automatic = client.get(f"/media/v1/sessions/{session.id}/background")
            assert automatic.json()["sourceMode"] == "auto"
            assert automatic.json()["manualLocked"] is False

            manual = client.put(
                f"/media/v1/sessions/{session.id}/background",
                json={"assetId": item["assetId"]},
            )
            assert manual.json()["sourceMode"] == "manual"
            assert manual.json()["manualLocked"] is True

            cleared = client.delete(f"/media/v1/sessions/{session.id}/background")
            assert cleared.status_code == 200
            assert cleared.json()["background"] is None
            assert cleared.json()["sourceMode"] == "none"

            gateway.messages.append(
                session.id,
                models.MESSAGE_ROLE_ASSISTANT,
                "走入森林深处。",
                turn_id=2,
                seq_in_turn=1,
            )
            resumed = client.post(
                f"/media/v1/sessions/{session.id}/background-evaluations",
                json={"observedTurnId": 2},
            )
            evaluation_id = resumed.json()["evaluationId"]
            for _ in range(100):
                response = client.get(
                    f"/media/v1/sessions/{session.id}/background-evaluations/{evaluation_id}"
                )
                if response.json()["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)
            restored = client.get(f"/media/v1/sessions/{session.id}/background")
            assert restored.json()["sourceMode"] == "auto"

            content = client.get(
                f"/media/v1/workspaces/demo_workspace/library/{item['itemId']}/content"
            )
            assert content.status_code == 200
            assert content.content == PNG
    finally:
        set_runtime_for_tests(None)


def test_library_analysis_unsupported_is_a_non_persistent_business_error(tmp_path) -> None:
    class UnsupportedAnalyzer:
        async def analyze(self, image):  # noqa: ANN001, ANN201
            raise MediaImageAnalysisUnsupportedError()

    gateway, _session, _message, runtime = _runtime(
        tmp_path,
        image_analyzer=UnsupportedAnalyzer(),
    )
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/media/v1/workspaces/demo_workspace/library/analyze",
                files={"file": ("forest.png", PNG, "image/png")},
            )
            assert response.status_code == 422
            assert response.json()["detail"]["errorCode"] == "MEDIA_IMAGE_ANALYSIS_UNSUPPORTED"
            assert gateway.media.list_workspace_blobs("demo_workspace") == []
    finally:
        set_runtime_for_tests(None)


def test_media_library_filters_facets_and_partial_batch_delete(tmp_path) -> None:
    _gateway, session, _message, runtime = _runtime(tmp_path)
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            def upload(name: str, payload: bytes, media_type: str):
                response = client.post(
                    "/media/v1/workspaces/demo_workspace/library",
                    data={
                        "scope": "story",
                        "mediaType": media_type,
                        "storyId": "1",
                        "title": name,
                        "description": f"{name} description",
                        "tags": '["forest", "night"]',
                        "isDefault": "false",
                    },
                    files={"file": (f"{name}.png", payload, "image/png")},
                )
                assert response.status_code == 200
                return response.json()

            background = upload("Background", PNG + b"-background", "background")
            candidate = upload("Candidate", PNG + b"-candidate", "map")
            selected = client.put(
                f"/media/v1/sessions/{session.id}/background",
                json={"assetId": background["assetId"]},
            )
            assert selected.status_code == 200

            updated = client.patch(
                "/media/v1/workspaces/demo_workspace/library/batch",
                json={
                    "itemIds": [candidate["itemId"]],
                    "mediaType": "avatar",
                    "addTags": ["curated"],
                    "removeTags": ["night"],
                },
            )
            assert updated.status_code == 200
            assert updated.json()["succeededItemIds"] == [candidate["itemId"]]

            filtered = client.get(
                "/media/v1/workspaces/demo_workspace/library",
                params={"mediaTypes": "avatar", "tags": "curated", "pageSize": 1},
            )
            assert filtered.status_code == 200
            assert filtered.json()["total"] == 1
            assert filtered.json()["items"][0]["mediaType"] == "avatar"
            facets = client.get(
                "/media/v1/workspaces/demo_workspace/library/facets"
            )
            assert facets.status_code == 200
            assert {entry["value"] for entry in facets.json()["mediaTypes"]} == {
                "avatar",
                "background",
            }

            deleted = client.post(
                "/media/v1/workspaces/demo_workspace/library/batch-delete",
                json={"itemIds": [background["itemId"], candidate["itemId"]]},
            )
            assert deleted.status_code == 200
            assert deleted.json()["succeededItemIds"] == [candidate["itemId"]]
            assert deleted.json()["failed"] == [{
                "itemId": background["itemId"],
                "errorCode": "MEDIA_ASSET_IN_USE",
                "message": f"Media asset is still used by a typed binding: {background['itemId']}",
            }]
    finally:
        set_runtime_for_tests(None)


def test_media_service_reconcile_contract(tmp_path) -> None:
    _gateway, _session, _message, runtime = _runtime(tmp_path)
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            uploaded = client.post(
                "/media/v1/workspaces/demo_workspace/library",
                data={
                    "scope": "story",
                    "mediaType": "background",
                    "storyId": "1",
                    "title": "Missing forest",
                    "description": "The indexed source file will be removed.",
                    "tags": '["forest"]',
                    "isDefault": "false",
                },
                files={"file": ("forest.png", PNG, "image/png")},
            )
            assert uploaded.status_code == 200
            item = uploaded.json()
            path, _ = runtime.service.resolve_library_asset_content(
                "demo_workspace",
                item["itemId"],
            )
            path.unlink()

            reconciled = client.post(
                "/media/v1/workspaces/demo_workspace/library/reconcile"
            )

            assert reconciled.status_code == 200
            assert reconciled.json() == {
                "workspaceId": "demo_workspace",
                "scannedBlobs": 1,
                "removedBlobs": 1,
                "removedAssets": 1,
                "removedLibraryItems": 1,
                "removedGalleryItems": 0,
                "clearedBackgrounds": 0,
            }
            repeated = client.post(
                "/media/v1/workspaces/demo_workspace/library/reconcile"
            )
            assert repeated.status_code == 200
            assert repeated.json()["scannedBlobs"] == 0
            assert repeated.json()["removedBlobs"] == 0
    finally:
        set_runtime_for_tests(None)
