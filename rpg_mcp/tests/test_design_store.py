from __future__ import annotations

import json
import shutil

import pytest
from jsonschema import Draft202012Validator

import rpg_mcp.design_store as design_store_module
from rpg_mcp.contracts import StoryDesignDocument
from rpg_mcp.design_store import DesignConflictError, DesignProjectStore


def _document() -> StoryDesignDocument:
    return StoryDesignDocument.model_validate({
        "schemaVersion": "story-design/1.0",
        "project": {
            "projectId": "portable-test",
            "name": "Portable Test",
            "language": "zh-CN",
            "phase": "architecture",
        },
        "target": {
            "workspaceId": "portable_world",
            "workspaceName": "Portable World",
            "workspaceRoot": "data/portable_world",
            "storyId": None,
            "allowCreateWorkspace": True,
        },
        "story": {
            "stableId": "story-main",
            "title": "可移动故事",
            "summary": "",
            "storyPrompt": "",
            "timeSetting": "2020 年",
            "logline": "",
            "themes": [],
            "boundaries": [],
            "metadata": {},
        },
        "resources": {},
        "decisions": [],
        "openQuestions": [],
        "sources": [],
        "notes": [],
    })


def test_linear_revisions_expected_head_and_restore(tmp_path) -> None:
    store = DesignProjectStore.initialize(
        tmp_path / "project",
        _document(),
        project_name="Portable Test",
    )
    first = store.get_current()
    assert first["revision"] == "r000001"

    changed = store.patch(
        expected_head="r000001",
        reason="Confirm logline",
        operations=[
            {
                "op": "replace",
                "path": "/story/logline",
                "value": "主角必须在城市停电前找到被隐藏的证词。",
            },
            {
                "op": "add",
                "path": "/decisions/-",
                "value": {
                    "id": "decision-logline",
                    "topic": "核心钩子",
                    "decision": "停电前找到证词。",
                    "rationale": "提供明确时限。",
                    "status": "confirmed",
                    "decidedAt": "2026-07-23T00:00:00Z",
                },
            },
        ],
    )
    assert changed["revision"] == "r000002"
    with pytest.raises(DesignConflictError, match="stale design head"):
        store.patch(
            expected_head="r000001",
            reason="Stale writer",
            operations=[
                {"op": "replace", "path": "/story/summary", "value": "stale"}
            ],
        )
    checkpoint = store.create_checkpoint(
        "architecture-v1",
        expected_head="r000002",
    )
    assert checkpoint["revision"] == "r000002"
    restored = store.restore_revision(
        "r000001",
        expected_head="r000002",
        reason="Return to initial architecture",
    )
    assert restored["revision"] == "r000003"
    assert store.get_current()["document"]["story"]["logline"] == ""
    assert (tmp_path / "project/design/revisions/r000002.json").is_file()


def test_project_identity_change_updates_manifest_atomically(tmp_path) -> None:
    root = tmp_path / "project"
    store = DesignProjectStore.initialize(
        root,
        _document(),
        project_name="Portable Test",
    )

    store.patch(
        expected_head="r000001",
        reason="Name the durable design project",
        operations=[
            {
                "op": "replace",
                "path": "/project/projectId",
                "value": "portable-test-renamed",
            },
            {
                "op": "replace",
                "path": "/project/name",
                "value": "Renamed Portable Test",
            },
        ],
    )

    manifest = json.loads(
        (root / "design-project.json").read_text(encoding="utf-8")
    )
    assert manifest["projectId"] == "portable-test-renamed"
    assert manifest["name"] == "Renamed Portable Test"
    assert store.doctor()["healthy"] is True


def test_interrupted_revision_commit_recovers_on_reopen(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "project"
    store = DesignProjectStore.initialize(
        root,
        _document(),
        project_name="Portable Test",
    )
    original_write = design_store_module._atomic_write_json
    crashed = False

    def crash_after_current_write(path, value):
        nonlocal crashed
        original_write(path, value)
        if path == store.current_path and not crashed:
            crashed = True
            raise KeyboardInterrupt("simulated process exit")

    monkeypatch.setattr(
        design_store_module,
        "_atomic_write_json",
        crash_after_current_write,
    )
    with pytest.raises(KeyboardInterrupt, match="simulated process exit"):
        store.patch(
            expected_head="r000001",
            reason="Confirm durable change",
            operations=[
                {
                    "op": "replace",
                    "path": "/story/logline",
                    "value": "一次可恢复的设计提交。",
                }
            ],
        )
    assert (root / ".design-transaction.json").is_file()

    monkeypatch.setattr(
        design_store_module,
        "_atomic_write_json",
        original_write,
    )
    recovered = DesignProjectStore(root)

    assert recovered.get_current()["revision"] == "r000002"
    assert recovered.get_current()["document"]["story"]["logline"] == (
        "一次可恢复的设计提交。"
    )
    assert not (root / ".design-transaction.json").exists()
    assert recovered.doctor()["healthy"] is True


def test_pack_sections_and_relocation_are_portable(tmp_path) -> None:
    source = tmp_path / "source"
    store = DesignProjectStore.initialize(
        source,
        _document(),
        project_name="Portable Test",
    )
    built = store.build_pack(
        expected_head="r000001",
        included_sections=["story", "characters", "visualCatalog"],
    )
    assert built["pack"]["includedSections"] == [
        "story",
        "characters",
        "visualCatalog",
    ]
    assert built["pack"]["applyPolicy"] == {
        "mode": "merge",
        "deleteMissing": False,
    }
    assert (source / built["path"]).is_file()

    moved = tmp_path / "moved" / "DesignProject"
    shutil.copytree(source, moved)
    relocated = DesignProjectStore(moved)
    assert relocated.doctor()["healthy"] is True
    manifest = json.loads(
        (moved / "design-project.json").read_text(encoding="utf-8")
    )
    assert all(
        not value.startswith("/")
        for value in manifest["paths"].values()
    )


def test_pack_build_is_repeatable_and_target_scoped(tmp_path) -> None:
    root = tmp_path / "project"
    store = DesignProjectStore.initialize(
        root,
        _document(),
        project_name="Portable Test",
    )

    first = store.build_pack(
        expected_head="r000001",
        included_sections=["story", "characters"],
    )
    repeated = store.build_pack(
        expected_head="r000001",
        included_sections=["story", "characters"],
    )
    other_target = store.build_pack(
        expected_head="r000001",
        included_sections=["story", "characters"],
        target_overrides={"workspaceId": "another_world"},
    )

    assert repeated["path"] == first["path"]
    assert repeated["packDigest"] == first["packDigest"]
    assert repeated["pack"] == first["pack"]
    assert other_target["path"] != first["path"]
    assert other_target["pack"]["target"]["workspaceId"] == "another_world"


def test_status_only_pack_keeps_external_character_reference(tmp_path) -> None:
    value = _document().model_dump(by_alias=True)
    value["resources"]["characters"] = [{
        "stableId": "character-player",
        "name": "林澈",
    }]
    value["resources"]["statusTables"] = [{
        "stableId": "status-player",
        "name": "林澈状态",
        "statusKind": "normal",
        "characterRef": "character-player",
        "rows": [],
    }]
    document = StoryDesignDocument.model_validate(value)
    store = DesignProjectStore.initialize(
        tmp_path / "project",
        document,
        project_name="Portable Test",
    )

    built = store.build_pack(
        expected_head="r000001",
        included_sections=["statusTables"],
    )

    assert built["pack"]["resources"]["characters"] == []
    assert (
        built["pack"]["resources"]["statusTables"][0]["characterRef"]
        == "character-player"
    )


def test_design_rejects_status_reference_to_unknown_character() -> None:
    value = _document().model_dump(by_alias=True)
    value["resources"]["statusTables"] = [{
        "stableId": "status-player",
        "name": "林澈状态",
        "statusKind": "normal",
        "characterRef": "missing-character",
        "rows": [],
    }]

    with pytest.raises(ValueError, match="references unknown character"):
        StoryDesignDocument.model_validate(value)


def test_design_requires_story_wide_character_detail_ids() -> None:
    value = _document().model_dump(by_alias=True)
    value["resources"]["characters"] = [
        {
            "stableId": "character-one",
            "name": "角色一",
            "details": [
                {"stableId": "detail-shared", "name": "角色一经历"}
            ],
        },
        {
            "stableId": "character-two",
            "name": "角色二",
            "details": [
                {"stableId": "detail-shared", "name": "角色二经历"}
            ],
        },
    ]

    with pytest.raises(ValueError, match="character detail ids must be unique"):
        StoryDesignDocument.model_validate(value)


def test_design_requires_story_wide_plot_node_ids() -> None:
    value = _document().model_dump(by_alias=True)
    value["resources"]["plotSchedule"] = {
        "pools": [
            {
                "stableId": "pool-main",
                "name": "主线池",
            }
        ],
        "events": [
            {
                "stableId": "event-one",
                "poolRef": "pool-main",
                "title": "事件一",
                "directive": "推进事件一。",
            },
            {
                "stableId": "event-two",
                "poolRef": "pool-main",
                "title": "事件二",
                "directive": "推进事件二。",
            },
        ],
        "outlines": [
            {
                "stableId": "outline-one",
                "name": "大纲一",
                "nodes": [
                    {
                        "stableId": "node-shared",
                        "eventRef": "event-one",
                        "scheduledTime": "第 2020 年 1 月 1 日 9 时",
                    }
                ],
            },
            {
                "stableId": "outline-two",
                "name": "大纲二",
                "nodes": [
                    {
                        "stableId": "node-shared",
                        "eventRef": "event-two",
                        "scheduledTime": "第 2020 年 1 月 2 日 9 时",
                    }
                ],
            },
        ],
    }

    with pytest.raises(ValueError, match="plot node ids must be unique"):
        StoryDesignDocument.model_validate(value)


def test_design_rejects_reserved_story_metadata_key() -> None:
    value = _document().model_dump(by_alias=True)
    value["story"]["metadata"]["_rpgStoryDesign"] = {}

    with pytest.raises(ValueError, match="is reserved"):
        StoryDesignDocument.model_validate(value)


@pytest.mark.parametrize(
    "locator",
    [
        "/Users/example/story.md",
        "C:\\Users\\example\\story.md",
        "../outside/story.md",
        "file:///tmp/story.md",
    ],
)
def test_design_rejects_non_portable_source_locator(locator: str) -> None:
    value = _document().model_dump(by_alias=True)
    value["sources"] = [
        {
            "id": "source-story",
            "title": "故事源",
            "locator": locator,
        }
    ]

    with pytest.raises(ValueError, match="DesignProject-relative"):
        StoryDesignDocument.model_validate(value)


def test_checked_in_design_schema_accepts_current_project() -> None:
    root = __import__("pathlib").Path("DesignProject")
    schema = json.loads(
        (root / "schemas/story-design-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    current = json.loads(
        (root / "design/current.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(current)
