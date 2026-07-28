from __future__ import annotations

import http.client
import importlib.util
import json
import shutil
import threading
from pathlib import Path
from types import ModuleType
from typing import Any


def _viewer_module() -> ModuleType:
    path = Path("DesignProject/viewer/serve.py").resolve()
    spec = importlib.util.spec_from_file_location("design_project_viewer", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_project(tmp_path: Path) -> Path:
    root = tmp_path / "DesignProject"
    shutil.copytree("DesignProject", root)
    return root


def _request(
    port: int,
    method: str,
    path: str,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        port,
        timeout=3,
    )
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def _start_server(module: ModuleType, root: Path):
    server = module.create_server(root, port=0)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    return server, thread


def _stop_server(server, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    assert not thread.is_alive()


def _read_sse_event(
    response: http.client.HTTPResponse,
) -> tuple[str, dict[str, Any]]:
    event_name = ""
    data = ""
    while True:
        line = response.readline().decode("utf-8")
        if not line:
            raise AssertionError("SSE connection ended before an event")
        if line == "\n":
            if event_name and data:
                return event_name, json.loads(data)
            continue
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            data = line.removeprefix("data: ").strip()


def test_viewer_serves_only_read_only_loopback_apis(tmp_path) -> None:
    module = _viewer_module()
    root = _copy_project(tmp_path)
    server, thread = _start_server(module, root)
    port = server.server_address[1]
    try:
        status, headers, body = _request(port, "GET", "/api/project")
        assert status == 200
        assert "default-src 'self'" in headers["content-security-policy"]
        project = json.loads(body)
        assert project["viewerVersion"] == "story-design-viewer/2.0"
        assert project["live"]["currentRevision"] == "r000001"
        assert project["live"]["authoringAssetsDigest"]

        status, headers, body = _request(port, "GET", "/")
        assert status == 200
        assert headers["content-type"] == "text/html; charset=utf-8"
        assert b"Story Design Viewer" in body

        status, _, body = _request(port, "GET", "/app.js")
        assert status == 200
        assert b"connectRevisionStream" in body
        assert b"renderFieldGuide" in body
        assert b"authoring-rules" in body
        assert b"invalidateSchemaCache" in body

        status, _, body = _request(port, "GET", "/api/revisions")
        assert status == 200
        assert json.loads(body)["revisions"][0]["revisionId"] == "r000001"

        status, _, body = _request(
            port,
            "GET",
            "/api/schemas/story-design",
        )
        assert status == 200
        assert json.loads(body)["$id"] == "story-design-v2.schema.json"

        status, _, body = _request(
            port,
            "GET",
            "/api/authoring-rules",
        )
        assert status == 200
        rules = json.loads(body)
        assert rules["authoringRulesVersion"] == "1.2"
        assert len(rules["fields"]) >= 150

        status, _, body = _request(
            port,
            "GET",
            "/api/diagnostics?revision=r000001&profile=package",
        )
        assert status == 200
        diagnostics = json.loads(body)
        assert diagnostics["valid"] is False
        assert {
            "package.story-title-required",
            "package.workspace-required",
        }.issubset({
            item["ruleId"] for item in diagnostics["diagnostics"]
        })

        status, headers, body = _request(port, "POST", "/api/project")
        assert status == 405
        assert headers["allow"] == "GET, HEAD"
        assert json.loads(body)["message"] == (
            "Story Design Viewer is read-only"
        )

        status, _, _ = _request(
            port,
            "GET",
            "/api/story-packs/%2e%2e%2fdesign-project.json",
        )
        assert status == 404
    finally:
        _stop_server(server, thread)


def test_sse_stream_announces_manifest_revision_changes(tmp_path) -> None:
    module = _viewer_module()
    root = _copy_project(tmp_path)
    server, thread = _start_server(module, root)
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        server.server_address[1],
        timeout=3,
    )
    try:
        connection.request(
            "GET",
            "/events",
            headers={"Accept": "text/event-stream"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == (
            "text/event-stream; charset=utf-8"
        )
        event_name, snapshot = _read_sse_event(response)
        assert event_name == "snapshot"
        assert snapshot["currentRevision"] == "r000001"

        manifest_path = root / "design-project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "currentRevision": "r000002",
            "headDigest": "b" * 64,
            "updatedAt": "2026-07-23T09:30:00Z",
        })
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )

        event_name, snapshot = _read_sse_event(response)
        assert event_name == "revision"
        assert snapshot["currentRevision"] == "r000002"
        assert snapshot["headDigest"] == "b" * 64
    finally:
        connection.close()
        _stop_server(server, thread)


def test_sse_stream_announces_authoring_asset_changes(tmp_path) -> None:
    module = _viewer_module()
    root = _copy_project(tmp_path)
    server, thread = _start_server(module, root)
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        server.server_address[1],
        timeout=3,
    )
    try:
        connection.request(
            "GET",
            "/events",
            headers={"Accept": "text/event-stream"},
        )
        response = connection.getresponse()
        assert response.status == 200
        event_name, snapshot = _read_sse_event(response)
        assert event_name == "snapshot"
        assert snapshot["authoringAssetsDigest"]

        manifest_path = root / "design-project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["authoringAssetsDigest"] = "c" * 64
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )

        event_name, snapshot = _read_sse_event(response)
        assert event_name == "authoring-rules"
        assert snapshot["authoringAssetsDigest"] == "c" * 64
    finally:
        connection.close()
        _stop_server(server, thread)


def test_manifest_switch_is_the_revision_visibility_boundary(tmp_path) -> None:
    module = _viewer_module()
    root = _copy_project(tmp_path)
    reader = module.ProjectReader(root)
    initial = reader.snapshot()
    assert initial["currentRevision"] == "r000001"

    revision_one = reader.revision("r000001")
    document = json.loads(json.dumps(revision_one["document"]))
    document["story"]["title"] = "雨中的白鸢咖啡馆"
    digest = module._json_digest(document)
    revision_two = {
        "schemaVersion": "story-design-project/2.0",
        "revisionId": "r000002",
        "revisionNumber": 2,
        "parentRevision": "r000001",
        "parentDigest": revision_one["documentDigest"],
        "documentDigest": digest,
        "createdAt": "2026-07-23T09:00:00Z",
        "reason": "Set the Story title",
        "document": document,
    }
    revision_path = root / "design/revisions/r000002.json"
    revision_path.write_text(
        json.dumps(revision_two, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "design/current.json").write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )

    before_manifest_switch = reader.snapshot()
    assert before_manifest_switch["currentRevision"] == "r000001"

    manifest_path = root / "design-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "currentRevision": "r000002",
        "headDigest": digest,
        "name": "雨中的白鸢咖啡馆",
        "updatedAt": "2026-07-23T09:00:00Z",
    })
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    after_manifest_switch = reader.snapshot()
    assert after_manifest_switch["currentRevision"] == "r000002"
    assert reader.history()["revisions"][0]["revisionId"] == "r000002"
    difference = reader.diff("r000001", "r000002")
    assert difference["changed"] is True
    assert difference["changedSections"] == [
        {
            "section": "story",
            "beforeDigest": module._json_digest(
                revision_one["document"]["story"]
            ),
            "afterDigest": module._json_digest(document["story"]),
        }
    ]
    assert "雨中的白鸢咖啡馆" in difference["unifiedDiff"]


def test_story_pack_archive_is_whitelisted_and_summarized(tmp_path) -> None:
    module = _viewer_module()
    root = _copy_project(tmp_path)
    pack = {
        "schemaVersion": "story-pack/1.0",
        "packId": "pack-demo",
        "projectId": "story-design-template",
        "storyStableId": "story",
        "sourceRevision": "r000001",
        "sourceDigest": "a" * 64,
        "generatedAt": "2026-07-23T09:15:00Z",
        "includedSections": ["story", "characters"],
        "target": {"workspaceId": "demo"},
        "story": {"title": "Demo Story"},
        "resources": {"characters": []},
    }
    pack_path = root / "artifacts/story-packs/pack-demo.json"
    pack_path.write_text(
        json.dumps(pack, ensure_ascii=False),
        encoding="utf-8",
    )

    reader = module.ProjectReader(root)
    archive = reader.story_packs()
    assert archive["packs"] == [{
        "filename": "pack-demo.json",
        "packId": "pack-demo",
        "projectId": "story-design-template",
        "storyStableId": "story",
        "storyTitle": "Demo Story",
        "sourceRevision": "r000001",
        "sourceDigest": "a" * 64,
        "generatedAt": "2026-07-23T09:15:00Z",
        "includedSections": ["story", "characters"],
        "target": {"workspaceId": "demo"},
        "sizeBytes": pack_path.stat().st_size,
    }]
    assert reader.story_pack("pack-demo.json")["packId"] == "pack-demo"

    try:
        reader.story_pack("../design-project.json")
    except module.ViewerValidationError:
        pass
    else:
        raise AssertionError("path traversal must be rejected")
