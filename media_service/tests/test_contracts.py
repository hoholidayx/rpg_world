from __future__ import annotations

import time

from fastapi.testclient import TestClient

from media_service.main import MediaRuntime, app, set_runtime_for_tests
from media_service.worker import MediaJobWorker
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.facade import MediaFacade
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.providers.local_file import LocalFileProvider

PNG = b"\x89PNG\r\n\x1a\nservice"


def _runtime(tmp_path):  # noqa: ANN202
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
    facade = MediaFacade(
        data=gateway.media,
        catalog=gateway.catalog,
        planner=DemoVisualBriefPlanner(),
        providers=MediaProviderCatalog(
            (LocalFileProvider(provider_dir),),
            default_key="local_file",
        ),
    )
    worker = MediaJobWorker(
        data=gateway.media,
        facade=facade,
        concurrency=1,
    )
    return gateway, session, message, MediaRuntime(
        gateway=gateway,
        facade=facade,
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
