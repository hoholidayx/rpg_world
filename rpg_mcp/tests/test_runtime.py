from __future__ import annotations

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from rpg_mcp.composition import build_runtime_composition
from rpg_mcp.contracts import StoryDesignDocument, StoryPack
from rpg_mcp.design_store import DesignProjectStore
from rpg_mcp.runtime import StoryPackRuntimeError


def _pack() -> dict:
    return {
        "schemaVersion": "rpg-story-pack/2.0",
        "contractVersion": "2.0",
        "packId": "test-project-r000002-full",
        "projectId": "test-project",
        "storyStableId": "story-main",
        "sourceRevision": "r000002",
        "sourceDigest": "a" * 64,
        "generatedAt": "2026-07-23T00:00:00Z",
        "target": {
            "workspaceId": "test_world",
            "workspaceName": "测试世界",
            "workspaceRoot": "data/test_world",
            "storyId": None,
            "allowCreateWorkspace": True,
        },
        "includedSections": [
            "story",
            "openings",
            "characters",
            "lorebook",
            "statusTables",
            "composer",
            "rpModules",
            "plotSchedule",
            "visualCatalog",
        ],
        "story": {
            "stableId": "story-main",
            "title": "测试故事",
            "summary": "用于 Story Pack 集成测试。",
            "storyPrompt": "保持玩家选择，不替玩家决定行动。",
            "timeSetting": "2019 年上海",
            "logline": "一次失踪调查揭开被修改的记忆。",
            "themes": ["信任"],
            "boundaries": ["不替玩家决定行动"],
            "metadata": {"genre": "mystery"},
        },
        "resources": {
            "openings": [
                {
                    "stableId": "opening-main",
                    "title": "雨夜",
                    "message": "2019 年 1 月 1 日，{USER_PLAY_ROLE_NAME}抵达车站。",
                    "sortOrder": 10,
                }
            ],
            "characters": [
                {
                    "stableId": "character-player",
                    "name": "林澈",
                    "description": "玩家候选角色，曾经是调查记者。",
                    "aliases": [],
                    "details": [
                        {
                            "stableId": "character-player-background",
                            "name": "背景",
                            "content": "曾经是调查记者。",
                            "tags": ["kind:background"],
                            "sortOrder": 10,
                        },
                        {
                            "stableId": "character-player-personality",
                            "name": "性格",
                            "content": "谨慎而敏锐。",
                            "tags": [
                                "kind:personality",
                                "scope:npc_portrayal",
                            ],
                            "sortOrder": 20,
                        }
                    ],
                    "visual": {"identityAnchors": ["黑色短发", "银色录音笔"]},
                    "sortOrder": 10,
                    "metadata": {},
                }
            ],
            "lorebook": [
                {
                    "stableId": "lore-station",
                    "name": "旧车站",
                    "content": "城市边缘的废弃车站。",
                    "description": "开场地点",
                    "tags": ["地点"],
                    "visual": {"anchors": ["湿润站台", "钨丝灯"]},
                    "sortOrder": 10,
                    "metadata": {},
                }
            ],
            "statusTables": [
                {
                    "stableId": "status-scene",
                    "name": "当前场景",
                    "statusKind": "scene",
                    "characterRef": None,
                    "description": "Scene 真源",
                    "rows": [
                        {
                            "key": "时间",
                            "value": "2019 年 1 月 1 日 9 时",
                            "runtimeKeyLocked": True,
                            "updateRule": "",
                            "metadata": {},
                        },
                        {
                            "key": "位置",
                            "value": "旧车站",
                            "runtimeKeyLocked": True,
                            "updateRule": "",
                            "metadata": {},
                        },
                        {
                            "key": "在场人物",
                            "value": "林澈",
                            "runtimeKeyLocked": True,
                            "updateRule": "",
                            "metadata": {},
                        },
                    ],
                    "sortOrder": 0,
                    "metadata": {},
                },
                {
                    "stableId": "status-player",
                    "name": "林澈状态",
                    "statusKind": "normal",
                    "characterRef": "character-player",
                    "description": "角色状态",
                    "rows": [
                        {
                            "key": "信任",
                            "value": "谨慎",
                            "runtimeKeyLocked": False,
                            "updateRule": "关系发生明确变化时更新。",
                            "metadata": {},
                        }
                    ],
                    "sortOrder": 10,
                    "metadata": {},
                },
            ],
            "narrativeStyles": [
                {
                    "stableId": "style-noir",
                    "name": "都市悬疑",
                    "prompt": "克制、具象，强调环境细节。",
                    "isBase": True,
                    "sortOrder": 10,
                }
            ],
            "quickReplies": [
                {
                    "stableId": "reply-observe",
                    "title": "观察",
                    "message": "仔细观察当前环境。",
                    "enabled": True,
                    "sortOrder": 10,
                }
            ],
            "rpModules": [
                {
                    "moduleName": "plot_scheduler",
                    "enabled": True,
                    "config": {},
                }
            ],
            "plotSchedule": {
                "pools": [
                    {
                        "stableId": "pool-main",
                        "name": "主线素材",
                        "description": "",
                        "selectionMode": "sequential",
                        "priority": 10,
                        "cooldownMinutes": 4320,
                        "enabled": False,
                    }
                ],
                "events": [
                    {
                        "stableId": "event-arrival",
                        "poolRef": "pool-main",
                        "title": "抵达车站",
                        "directive": "让玩家发现一条可调查的线索，不决定玩家行动。",
                        "description": "开局事件",
                        "suitabilityHint": "当前地点为旧车站且故事刚开始。",
                        "dispatchMode": "soft",
                        "scheduledTime": None,
                        "deadlineTime": None,
                        "position": 0,
                        "enabled": True,
                        "allowRepeat": False,
                        "repeatCooldownMinutes": 0,
                    }
                ],
                "outlines": [
                    {
                        "stableId": "outline-main",
                        "name": "主线",
                        "description": "",
                        "priority": 10,
                        "enabled": True,
                        "nodes": [
                            {
                                "stableId": "node-arrival",
                                "eventRef": "event-arrival",
                                "scheduledTime": "2019 年 1 月 1 日 9 时",
                                "dispatchMode": "soft",
                                "position": 0,
                                "enabled": True,
                            }
                        ],
                    }
                ],
            },
            "visualCatalog": [
                {
                    "stableId": "visual-station",
                    "assetType": "location",
                    "title": "雨夜旧车站",
                    "prompt": "2019 年上海郊外，雨夜废弃站台。",
                    "negativePrompt": "",
                    "subjectRefs": ["lore-station"],
                    "visualAnchors": ["湿润站台", "钨丝灯"],
                    "metadata": {},
                }
            ],
        },
        "applyPolicy": {"mode": "merge", "deleteMissing": False},
    }


def test_checked_in_story_pack_schema_accepts_runtime_fixture() -> None:
    import json
    from pathlib import Path

    schema = json.loads(
        Path("DesignProject/schemas/story-pack-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_pack())


def test_legacy_story_pack_defaults_missing_pool_cooldown_to_zero() -> None:
    legacy = _pack()
    legacy["resources"]["plotSchedule"]["pools"][0].pop(
        "cooldownMinutes"
    )

    parsed = StoryPack.model_validate(legacy)

    assert (
        parsed.resources.plot_schedule.pools[0].cooldown_minutes
        == 0
    )


def test_story_pack_validation_catches_runtime_owned_text_and_removed_status_fields(
    tmp_path,
) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        invalid_template = deepcopy(_pack())
        invalid_template["resources"]["openings"][0]["message"] = (
            "欢迎，{UNKNOWN_ROLE}。"
        )
        result = composition.application.validate_story_pack(invalid_template)
        assert result["valid"] is False
        assert "unsupported Story template variable" in result["errors"][0]

        invalid_scene = deepcopy(_pack())
        invalid_scene["resources"]["statusTables"][0]["rows"][0].update({
            "updateFrequency": "deferred",
        })
        result = composition.application.validate_story_pack(invalid_scene)
        assert result["valid"] is False
        assert "updateFrequency" in result["errors"][0]
    finally:
        composition.close()


def test_story_pack_preview_apply_and_idempotency(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        pack = _pack()
        preview = composition.application.preview_story_pack(pack)
        assert preview["status"] == "previewed"
        assert preview["plan"]["conflicts"] == []
        assert preview["requiresConfirmation"] is True

        applied = composition.application.apply_story_pack(
            preview["operationId"]
        )
        assert applied["status"] == "applied"
        story_id = applied["result"]["storyId"]
        assert applied["result"]["idMapping"]["character"]["character-player"]
        assert len(applied["result"]["archivedVisualSpecifications"]) == 1

        repeated = composition.application.apply_story_pack(
            preview["operationId"]
        )
        assert repeated["status"] == "applied"
        same_pack = composition.application.preview_story_pack(pack)
        assert same_pack["alreadyApplied"] is True

        snapshot = composition.application.export_story_snapshot(
            "test_world",
            story_id,
        )
        document = snapshot["designDocument"]
        assert document["story"]["title"] == "测试故事"
        assert document["story"]["timeSetting"] == "2019 年上海"
        assert document["story"]["logline"] == (
            "一次失踪调查揭开被修改的记忆。"
        )
        assert document["story"]["themes"] == ["信任"]
        assert document["story"]["boundaries"] == ["不替玩家决定行动"]
        assert document["story"]["metadata"] == {"genre": "mystery"}
        assert document["resources"]["characters"][0]["stableId"] == (
            "character-player"
        )
        assert document["resources"]["statusTables"][0]["rows"]
        assert document["resources"]["visualCatalog"] == []
        assert (
            document["resources"]["plotSchedule"]["pools"][0]
            ["cooldownMinutes"]
            == 4320
        )

        no_base = deepcopy(pack)
        no_base["packId"] = "test-project-r000003-no-base-style"
        no_base["sourceRevision"] = "r000003"
        no_base["sourceDigest"] = "b" * 64
        no_base["resources"]["narrativeStyles"][0]["isBase"] = False
        no_base_preview = composition.application.preview_story_pack(no_base)
        assert no_base_preview["plan"]["conflicts"] == []
        composition.application.apply_story_pack(
            no_base_preview["operationId"]
        )
        no_base_snapshot = composition.application.export_story_snapshot(
            "test_world",
            story_id,
        )
        assert (
            no_base_snapshot["designDocument"]["resources"]
            ["narrativeStyles"][0]["isBase"]
            is False
        )
    finally:
        composition.close()


def test_apply_rejects_operation_from_a_different_preview_lane(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        preview = composition.application.preview_story_pack(
            _pack(),
            operation_kind="changes",
        )

        with pytest.raises(
            StoryPackRuntimeError,
            match="matching apply tool",
        ):
            composition.application.apply_story_pack(
                preview["operationId"],
                expected_operation_kind="story_pack",
            )

        applied = composition.application.apply_story_pack(
            preview["operationId"],
            expected_operation_kind="changes",
        )
        assert applied["result"]["operationKind"] == "changes"

        separate_lane = composition.application.preview_story_pack(
            _pack(),
            operation_kind="story_pack",
        )
        assert separate_lane["status"] == "previewed"
        assert "alreadyApplied" not in separate_lane
        applied = composition.application.apply_story_pack(
            separate_lane["operationId"],
            expected_operation_kind="story_pack",
        )
        assert applied["result"]["operationKind"] == "story_pack"
    finally:
        composition.close()


def test_story_pack_update_and_runtime_drift_conflict(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        pack = _pack()
        first = composition.application.preview_story_pack(pack)
        applied = composition.application.apply_story_pack(first["operationId"])
        story_id = int(applied["result"]["storyId"])

        changed = deepcopy(pack)
        changed["packId"] = "test-project-r000003-characters"
        changed["sourceRevision"] = "r000003"
        changed["sourceDigest"] = "b" * 64
        changed["resources"]["characters"][0]["description"] = (
            "玩家候选角色，曾经是调查记者，也更擅长快速决断。"
        )
        update_preview = composition.application.preview_story_pack(changed)
        character_change = next(
            item
            for item in update_preview["plan"]["changes"]
            if item["kind"] == "character"
        )
        assert character_change["action"] == "update"
        composition.application.apply_story_pack(update_preview["operationId"])

        character = composition.gateway.character_management.list_characters(
            "test_world",
            story_id,
        )[0]
        composition.gateway.character_management.update_character(
            "test_world",
            story_id,
            character.id,
            description="运行时人工修改。",
        )
        conflicted = deepcopy(changed)
        conflicted["packId"] = "test-project-r000004-characters"
        conflicted["sourceRevision"] = "r000004"
        conflicted["sourceDigest"] = "c" * 64
        conflicted["resources"]["characters"][0]["description"] = (
            "玩家候选角色，沉着冷静。"
        )
        conflict_preview = composition.application.preview_story_pack(
            conflicted
        )
        assert any(
            item["code"] == "concurrent_runtime_change"
            for item in conflict_preview["plan"]["conflicts"]
        )
        assert conflict_preview["requiresConfirmation"] is False
    finally:
        composition.close()


def test_narrative_style_mount_drift_is_preserved(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        pack = _pack()
        first = composition.application.preview_story_pack(pack)
        applied = composition.application.apply_story_pack(first["operationId"])
        story_id = int(applied["result"]["storyId"])
        composition.gateway.session_composer.set_story_base_style(
            "test_world",
            story_id,
            None,
        )

        changed = deepcopy(pack)
        changed["packId"] = "test-project-r000003-character-update"
        changed["sourceRevision"] = "r000003"
        changed["sourceDigest"] = "b" * 64
        changed["resources"]["characters"][0]["description"] = (
            "玩家候选角色，拥有新的公开经历。"
        )
        preview = composition.application.preview_story_pack(changed)
        style_change = next(
            item
            for item in preview["plan"]["changes"]
            if item["kind"] == "narrative_style"
        )
        assert style_change["action"] == "runtime_modified"

        composition.application.apply_story_pack(preview["operationId"])
        snapshot = composition.application.export_story_snapshot(
            "test_world",
            story_id,
        )
        assert (
            snapshot["designDocument"]["resources"]
            ["narrativeStyles"][0]["isBase"]
            is False
        )
    finally:
        composition.close()


def test_stable_bindings_cannot_be_hijacked_by_another_project(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        pack = _pack()
        first = composition.application.preview_story_pack(pack)
        applied = composition.application.apply_story_pack(first["operationId"])
        foreign = deepcopy(pack)
        foreign["projectId"] = "other-project"
        foreign["packId"] = "other-project-r000001-full"
        foreign["target"]["storyId"] = applied["result"]["storyId"]
        preview = composition.application.preview_story_pack(foreign)
        assert any(
            item["code"] == "story_project_binding_conflict"
            for item in preview["plan"]["conflicts"]
        )
        assert preview["requiresConfirmation"] is False
    finally:
        composition.close()


def test_section_pack_updates_only_included_resources(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        full = _pack()
        first = composition.application.preview_story_pack(full)
        applied = composition.application.apply_story_pack(first["operationId"])
        story_id = int(applied["result"]["storyId"])

        partial = deepcopy(full)
        partial["packId"] = "test-project-r000003-lorebook"
        partial["sourceRevision"] = "r000003"
        partial["sourceDigest"] = "d" * 64
        partial["includedSections"] = ["lorebook"]
        partial["story"]["title"] = "不应更新的标题"
        partial["resources"] = {
            "lorebook": deepcopy(full["resources"]["lorebook"])
        }
        partial["resources"]["lorebook"][0]["content"] = "更新后的车站设定。"
        preview = composition.application.preview_story_pack(partial)
        changed_kinds = {
            item["kind"]
            for item in preview["plan"]["changes"]
            if item["action"] in {"create", "update", "adopt_update"}
        }
        assert changed_kinds == {"lorebook"}
        composition.application.apply_story_pack(preview["operationId"])
        story = composition.gateway.catalog.get_story("test_world", story_id)
        assert story.title == "测试故事"
        assert len(
            composition.gateway.character_management.list_characters(
                "test_world",
                story_id,
            )
        ) == 1
        lore = composition.gateway.lorebook_management.list_entries(
            "test_world",
            story_id,
        )[0]
        assert lore.content == "更新后的车站设定。"
    finally:
        composition.close()


def test_status_only_pack_resolves_character_from_existing_binding(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        full = _pack()
        first = composition.application.preview_story_pack(full)
        applied = composition.application.apply_story_pack(first["operationId"])
        story_id = int(applied["result"]["storyId"])

        partial = deepcopy(full)
        partial["packId"] = "test-project-r000003-status"
        partial["sourceRevision"] = "r000003"
        partial["sourceDigest"] = "e" * 64
        partial["includedSections"] = ["statusTables"]
        partial["resources"] = {
            "statusTables": deepcopy(full["resources"]["statusTables"])
        }
        partial["resources"]["statusTables"][1]["rows"][0]["value"] = "信任"

        preview = composition.application.preview_story_pack(partial)
        assert preview["plan"]["conflicts"] == []
        composition.application.apply_story_pack(preview["operationId"])

        tables = composition.gateway.status.list_story_tables(
            "test_world",
            story_id,
        )
        player = next(item for item in tables if item.name == "林澈状态")
        assert player.document.rows[0].value == "信任"
        assert player.story_character_id is not None
    finally:
        composition.close()


def test_status_only_pack_previews_missing_character_binding_as_conflict(
    tmp_path,
) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        partial = deepcopy(_pack())
        partial["packId"] = "test-project-r000003-status"
        partial["sourceRevision"] = "r000003"
        partial["sourceDigest"] = "f" * 64
        partial["includedSections"] = ["statusTables"]
        partial["resources"] = {
            "statusTables": deepcopy(partial["resources"]["statusTables"])
        }

        preview = composition.application.preview_story_pack(partial)

        assert preview["requiresConfirmation"] is False
        assert any(
            item["code"] == "missing_character_binding"
            for item in preview["plan"]["conflicts"]
        )
    finally:
        composition.close()


def test_preview_rejects_unknown_rp_module(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        pack = _pack()
        pack["resources"]["rpModules"][0]["moduleName"] = "missing_module"

        preview = composition.application.preview_story_pack(pack)

        assert preview["requiresConfirmation"] is False
        assert any(
            item["code"] == "unknown_rp_module"
            for item in preview["plan"]["conflicts"]
        )
    finally:
        composition.close()


def test_local_sync_failure_retries_without_reapplying_database(tmp_path) -> None:
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        preview = composition.application.preview_story_pack(_pack())

        def fail(_operation):
            raise OSError("project moved")

        pending = composition.application.apply_story_pack(
            preview["operationId"],
            local_sync=fail,
        )
        assert pending["status"] == "applied_with_local_sync_pending"
        story_count = len(
            composition.gateway.catalog.list_stories("test_world") or []
        )

        recovered_statuses = []

        def recover(operation):
            recovered_statuses.append(operation["status"])
            return {
                "integrationPath": "integrations/rpg-world.json",
                "reportPath": "reports/operation.json",
            }

        recovered = composition.application.apply_story_pack(
            preview["operationId"],
            local_sync=recover,
        )
        assert recovered["status"] == "applied"
        assert recovered_statuses == ["applied"]
        assert recovered["result"]["localSync"]["completed"] is True
        assert len(
            composition.gateway.catalog.list_stories("test_world") or []
        ) == story_count
    finally:
        composition.close()


def test_apply_updates_portable_integration_after_database_commit(tmp_path) -> None:
    document = StoryDesignDocument.model_validate({
        "project": {
            "projectId": "test-project",
            "name": "Test Project",
            "language": "zh-CN",
            "phase": "package_ready",
        },
        "target": {},
        "story": {"stableId": "story-main"},
        "resources": {},
    })
    store = DesignProjectStore.initialize(
        tmp_path / "DesignProject",
        document,
        project_name="Test Project",
    )
    composition = build_runtime_composition(tmp_path / "runtime.sqlite3")
    try:
        preview = composition.application.preview_story_pack(_pack())
        applied = composition.application.apply_story_pack(
            preview["operationId"],
            local_sync=store.write_runtime_integration,
        )
        assert applied["status"] == "applied"
        assert applied["result"]["localSync"]["completed"] is True
        integration = (
            tmp_path / "DesignProject/integrations/rpg-world.json"
        )
        report = (
            tmp_path
            / "DesignProject/reports"
            / f"runtime-operation-{preview['operationId']}.json"
        )
        assert integration.is_file()
        assert report.is_file()
        assert '"completed": true' in report.read_text(encoding="utf-8")
    finally:
        composition.close()
