from __future__ import annotations

import hashlib
import json
import runpy
import shutil
from pathlib import Path

import pytest

from rpg_mcp.authoring_rules import (
    AUTHORING_RULES_VERSION,
    authoring_rules_catalog,
    evaluate_authoring_diagnostics,
)
from rpg_mcp.contracts import (
    StoryDesignDocument,
    build_story_pack,
    digest_json,
)
from rpg_mcp.design_store import (
    DesignConflictError,
    DesignProjectStore,
    DesignStoreError,
    DesignValidationError,
)
from rpg_mcp.generate_design_assets import (
    build_managed_authoring_assets,
)


def _document() -> StoryDesignDocument:
    return StoryDesignDocument.model_validate({
        "schemaVersion": "story-design/2.0",
        "project": {
            "projectId": "rule-test",
            "name": "Rule Test",
            "language": "zh-CN",
            "phase": "resource_design",
        },
        "target": {
            "workspaceId": "rule_world",
            "workspaceName": "Rule World",
            "workspaceRoot": "data/rule_world",
            "storyId": None,
            "allowCreateWorkspace": True,
        },
        "story": {
            "stableId": "story-main",
            "title": "规则测试故事",
            "summary": "用于字段语义验证。",
            "storyPrompt": "保留玩家选择。",
            "timeSetting": "2020 年上海",
            "logline": "调查员在停电前找到证词。",
            "themes": [],
            "boundaries": ["不得替玩家决定行动。"],
            "metadata": {},
        },
        "resources": {
            "openings": [{
                "stableId": "opening-main",
                "title": "雨夜",
                "message": "雨夜开始了。",
            }]
        },
        "decisions": [],
        "openQuestions": [],
        "sources": [],
        "notes": [],
    })


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rule_catalog_covers_every_generated_schema_field() -> None:
    catalog = authoring_rules_catalog()
    payload = dict(catalog)
    declared_digest = payload.pop("catalogDigest")

    assert AUTHORING_RULES_VERSION == "1.5"
    assert catalog["authoringRulesVersion"] == AUTHORING_RULES_VERSION
    assert digest_json(payload) == declared_digest
    assert len(catalog["fields"]) >= 150
    assert {
        "draft",
        "package",
    } == set(catalog["profiles"])

    assets = build_managed_authoring_assets()
    for relative in (
        "schemas/story-design-v2.schema.json",
        "schemas/story-pack-v2.schema.json",
    ):
        schema = json.loads(assets[relative])
        assert schema["x-authoringRulesVersion"] == AUTHORING_RULES_VERSION
        assert schema["x-authoringRulesDigest"] == declared_digest
        objects = [schema, *schema.get("$defs", {}).values()]
        for definition in objects:
            for field in definition.get("properties", {}).values():
                assert field["description"]
                assert field["examples"]
                assert field["x-authoringRuleId"].startswith("field.")
                assert field["x-runtimeEffect"]


def test_rule_catalog_uses_model_specific_semantic_examples() -> None:
    rules = {
        (item["model"], item["field"]): item
        for item in authoring_rules_catalog()["fields"]
    }
    fields = {
        identity: item["examples"][0]
        for identity, item in rules.items()
    }

    assert fields[("NarrativeStyleSpec", "name")] == "克制悬疑"
    assert fields[("QuickReplySpec", "message")] == (
        "我先检查信封和门外是否留下痕迹。"
    )
    assert fields[("SourceRecord", "notes")] == (
        "仅作为背景参考，正式内容需写入当前 revision。"
    )
    assert fields[("OpenQuestion", "status")] == "open"
    assert fields[("LorebookSpec", "stableId")] == "lore-white-kite-cafe"
    assert fields[("StatusTableSpec", "characterRef")] is None
    assert "value 格式" in (
        rules[("StatusTableSpec", "description")]["description"]
    )
    assert "动态 key" in (
        rules[("StatusTableSpec", "description")]["description"]
    )
    assert "不妨碍同表新增其他未锁字段" in (
        rules[("StatusRowSpec", "runtimeKeyLocked")]["description"]
    )
    assert "字段专属" in (
        rules[("StatusRowSpec", "updateRule")]["description"]
    )
    assert "可按表约定表示数值、枚举、列表、简短描述或当前事实状态" in (
        rules[("StatusRowSpec", "value")]["description"]
    )
    assert "不要预设 value 是数值" in (
        rules[("StatusRowSpec", "updateRule")]["avoid"]
    )
    assert "当前事实、承诺、联系或事件状态可以成为字段" in (
        rules[("StatusTableSpec", "description")]["avoid"]
    )
    assert rules[("StoryResources", "characters")]["runtimeEffect"] == (
        rules[("CharacterSpec", "name")]["runtimeEffect"]
    )
    assert "只影响 DesignProject" not in (
        rules[("StoryResources", "plotSchedule")]["runtimeEffect"]
    )
    assert "每个可推进世界 turn" not in (
        rules[("StoryCore", "storyPrompt")]["description"]
    )
    assert "不是定时器" in (
        rules[("PlotEventSpec", "scheduledTime")]["description"]
    )
    assert "Scene 调度机会" in (
        rules[("PlotEventSpec", "dispatchMode")]["description"]
    )
    assert "手动标记忽略" in (
        rules[("PlotEventSpec", "allowRepeat")]["description"]
    )
    assert "事件级冷却锚点" in (
        rules[("PlotEventSpec", "repeatCooldownMinutes")]["description"]
    )
    assert "不影响池级冷却" in (
        rules[("PlotEventSpec", "repeatCooldownMinutes")]["description"]
    )
    assert "整个池" in (
        rules[("PlotPoolSpec", "cooldownMinutes")]["description"]
    )
    assert "手动标记、大纲注入、延期和错误" in (
        rules[("PlotPoolSpec", "cooldownMinutes")]["description"]
    )
    assert "日常现实扰动建议半天到一天" in (
        rules[("PlotPoolSpec", "cooldownMinutes")]["description"]
    )
    assert "改变关系结构的戏剧性巧合建议十天到数周" in (
        rules[("PlotPoolSpec", "cooldownMinutes")]["description"]
    )
    assert "长期概率" in (
        rules[("PlotPoolSpec", "selectionWeight")]["description"]
    )
    assert "范围 1–5、默认 3" in (
        rules[("PlotPoolSpec", "candidateBatchSize")]["description"]
    )
    assert "最终注入仍由场景适宜性重排决定" in (
        rules[("PlotEventSpec", "selectionWeight")]["description"]
    )
    assert "Scene 调度机会" in (
        rules[("PlotOutlineSpec", "enabled")]["description"]
    )
    assert "手动标记事件不读取节点字段" in (
        rules[("PlotNodeSpec", "dispatchMode")]["description"]
    )


def test_plot_scheduling_rules_model_scene_opportunities_and_runtime_marks() -> None:
    catalog = authoring_rules_catalog()
    principles = {
        item["ruleId"]: item
        for item in catalog["principles"]
    }
    scene_rule = principles["principle.plot-scene-opportunity"]
    manual_rule = principles[
        "principle.plot-manual-snapshot-runtime-only"
    ]
    binding_rule = principles[
        "principle.plot-outline-binding-isolates-pool-lane"
    ]
    pool_cooldown_rule = principles["principle.plot-pool-cooldown"]
    status_crud_rule = principles["principle.status-normal-field-crud"]

    assert "整个 active Scene document" in scene_rule["description"]
    assert "下一次 neutral、ic 或 gm turn" in scene_rule["runtimeEffect"]
    assert "无机会时不运行 selector" in scene_rule["runtimeEffect"]
    assert "不是 Story Design 或 Story Pack 字段" in (
        manual_rule["description"]
    )
    assert "忽略 Scene 调度机会" in manual_rule["runtimeEffect"]
    assert "解除该事件已有的事件级冷却" in manual_rule["runtimeEffect"]
    assert "不会启动、刷新或清除事件池级冷却" in (
        manual_rule["runtimeEffect"]
    )
    assert "任意大纲节点引用" in binding_rule["description"]
    assert "Session 手动标记仍可绕过" in binding_rule["runtimeEffect"]
    assert "elapsed 小于当前池配置" in pool_cooldown_rule["description"]
    assert "已有关系、信息或利益张力" in (
        pool_cooldown_rule["description"]
    )
    assert "selectionOrigin=scheduler" in (
        pool_cooldown_rule["runtimeEffect"]
    )
    assert "不能创建、删除或重命名整张表" in (
        status_crud_rule["description"]
    )
    assert "status_table_edit_fields" in status_crud_rule["runtimeEffect"]

    assets = build_managed_authoring_assets()
    contract = json.loads(assets["schemas/rpg-mcp-contract-v2.json"])
    status_policy = contract["statusTables"]
    policy = contract["plotScheduling"]

    assert status_policy == {
        "documentSchemaVersion": 2,
        "worldAdvancingModes": ["neutral", "ic", "gm"],
        "oocAndCommandsAreReadOnly": True,
        "readSource": "current_turn_context",
        "normal": {
            "scope": "existing_session_tables",
            "tableCrud": False,
            "fieldCrud": [
                "create",
                "read",
                "update",
                "rename",
                "delete",
            ],
            "valueTool": "status_table_set_values",
            "structureTool": "status_table_edit_fields",
            "emptyTableCanCreateFirstField": True,
            "newFieldDefaults": {
                "runtimeKeyLocked": False,
                "updateRule": "",
                "metadata": {},
            },
            "runtimeKeyLocked": {
                "blocks": ["rename", "delete"],
                "allowsValueUpdate": True,
                "allowsOtherFieldCreation": True,
            },
            "authorPolicyFieldsMutableByLlm": False,
        },
        "scene": {
            "usesNormalStatusTools": False,
            "structurePolicySetting": (
                "agent.scene.allow_runtime_key_changes"
            ),
            "defaultAllowsExistingValueUpdatesOnly": True,
            "runtimeKeyLockedBlocks": ["rename", "delete"],
        },
    }
    assert policy["sceneTimeFormat"] == "Y 年 M 月 D 日 H 时 [M 分]"
    assert policy["sceneTimeUsesOrdinalPrefix"] is False
    assert policy["nonOocModes"] == ["neutral", "ic", "gm"]
    assert policy["automatic"] == {
        "selectionTrigger": "committed_active_scene_net_change",
        "selectionTurn": "next_non_ooc_turn",
        "selectionPhase": "after_status_preflight",
        "sceneChangeCoversEntireDocument": True,
        "requiresSceneOpportunity": True,
        "scheduledTimeRole": "eligibility_gate",
        "deadlineTimeRole": "exclusive_eligibility_gate",
        "timeFieldsAreTimers": False,
        "maxSelectionsPerOpportunity": {"outline": 1, "pool": 1},
        "sameEventMayUseBothLanes": False,
        "outlineReferencedEventsParticipateInPoolLane": False,
        "outlineBindingUsesAllNodeReferences": True,
        "poolSelection": {
            "field": "selectionWeight",
            "default": 1,
            "minimum": 1,
            "mode": "stable_weighted",
            "finiteTurnFairnessGuarantee": False,
        },
        "randomPoolEventSelection": {
            "weightField": "selectionWeight",
            "weightDefault": 1,
            "weightMinimum": 1,
            "weightControls": "batch_recall_probability",
            "batchSizeField": "candidateBatchSize",
            "batchSizeDefault": 3,
            "batchSizeMinimum": 1,
            "batchSizeMaximum": 5,
            "sampling": "stable_weighted_without_replacement",
            "rerankCallsPerOpportunity": 1,
            "sequentialPoolsIgnoreWeightAndBatch": True,
            "forcedPrimaryBypassesRerank": True,
        },
        "poolCooldown": {
            "field": "cooldownMinutes",
            "default": 0,
            "unit": "scene_time_minutes",
            "scope": "whole_pool",
            "anchorSourceKind": "pool",
            "anchorSelectionOrigin": "scheduler",
            "anchorDecisionStatus": "triggered",
            "anchorPoolIdentityField": "container_id",
            "readyWhenElapsedGreaterThanOrEqual": True,
            "currentConfigurationAppliesToExistingAnchor": True,
        },
        "oocConsumesOrCreatesOpportunity": False,
        "commandsConsumeOrCreateOpportunity": False,
        "disabledPlotSchedulingConsumesOrCreatesOpportunity": False,
        "failedOrCancelledTurnsConsumeOrCreateOpportunity": False,
    }
    assert policy["manualPendingInjection"]["availableModes"] == [
        "ooc",
        "gm",
    ]
    assert policy["manualPendingInjection"]["storySchemaField"] is False
    assert policy["manualPendingInjection"]["clearWithNullEventId"] is True
    assert set(
        policy["manualPendingInjection"]["ignoresAutomaticRules"]
    ) == {
        "scene_opportunity",
        "scene_time",
        "enabled",
        "scheduled_time",
        "deadline_time",
        "outline_binding",
        "repeat",
        "event_cooldown",
        "pool_cooldown",
    }
    assert (
        policy["manualPendingInjection"][
            "withoutSceneTimeClearsExistingCooldownAnchor"
        ]
        is True
    )
    assert (
        policy["manualPendingInjection"][
            "withoutSceneTimeClearsExistingEventCooldownAnchor"
        ]
        is True
    )
    assert (
        policy["manualPendingInjection"]["affectsPoolCooldownAnchor"]
        is False
    )
    assert policy["triggeredMeans"] == "selected_and_injected"

    design_schema = json.loads(
        assets["schemas/story-design-v2.schema.json"]
    )
    event_fields = design_schema["$defs"]["PlotEventSpec"]["properties"]
    assert {
        "pendingInjection",
        "temporaryTitle",
        "temporaryDirective",
    }.isdisjoint(event_fields)
    assert "不是定时器" in event_fields["scheduledTime"]["description"]

    skill = assets[
        ".agents/skills/rpg-story-authoring/SKILL.md"
    ]
    reference = assets[
        ".agents/skills/rpg-story-authoring/references/"
        "story-design-contract.md"
    ]
    assert "Do not model automatic Plot selection as a per-turn" in skill
    assert "Keep `plot_event_mark_next` state out of Story Design" in skill
    assert "`cooldownMinutes` pauses the whole pool" in skill
    assert "## Turn and Plot scheduling" in reference
    assert "Manual injection ignores the Scene" in reference
    assert "Exclude an event from the automatic pool lane" in reference


def test_draft_and_package_profiles_return_structured_diagnostics(
    tmp_path,
) -> None:
    document = StoryDesignDocument()
    store = DesignProjectStore.initialize(
        tmp_path / "project",
        document,
        project_name="Profile Test",
    )

    draft = store.validate(profile="draft")
    package = store.validate(profile="package")

    assert draft["valid"] is True
    assert package["valid"] is False
    assert {
        "package.story-title-required",
        "package.workspace-required",
    }.issubset({
        item["ruleId"] for item in package["diagnostics"]
    })
    for item in package["diagnostics"]:
        assert set(item) == {
            "ruleId",
            "severity",
            "path",
            "message",
            "suggestion",
            "runtimeEffect",
        }
    with pytest.raises(
        DesignValidationError,
        match="package profile validation failed",
    ):
        store.build_pack(expected_head="r000001")


def test_authoring_rules_can_be_filtered_by_domain_and_rule_id(
    tmp_path,
) -> None:
    store = DesignProjectStore.initialize(
        tmp_path / "project",
        _document(),
        project_name="Rule Query",
    )

    character_rules = store.get_authoring_rules(domain="character")
    exact = store.get_authoring_rules(
        rule_id="field.character.description"
    )

    assert character_rules["fields"]
    assert {
        item["domain"] for item in character_rules["fields"]
    } == {"character"}
    assert [item["ruleId"] for item in exact["fields"]] == [
        "field.character.description"
    ]
    assert exact["principles"] == []
    assert exact["diagnosticRules"] == []
    with pytest.raises(ValueError, match="unknown authoring rule id"):
        store.get_authoring_rules(rule_id="field.character.not-real")


def test_patch_returns_only_affected_advisory_diagnostics(tmp_path) -> None:
    store = DesignProjectStore.initialize(
        tmp_path / "project",
        _document(),
        project_name="Patch Test",
    )

    result = store.patch(
        expected_head="r000001",
        reason="Add a character draft",
        operations=[{
            "op": "add",
            "path": "/resources/characters/-",
            "value": {
                "stableId": "character-lin",
                "name": "林澈",
                "description": "调查记者，性格谨慎，内心总在怀疑自己。",
                "details": [],
            },
        }],
    )

    assert result["revision"] == "r000002"
    assert result["authoringRulesVersion"] == AUTHORING_RULES_VERSION
    assert [
        item["ruleId"] for item in result["advisoryDiagnostics"]
    ] == ["character.description-portrayal-leak"]


@pytest.mark.parametrize(
    ("mutate", "expected_rule"),
    [
        (
            lambda value: value["resources"]["characters"].append({
                "stableId": "character-mixed",
                "name": "混写角色",
                "description": "调查员。",
                "details": [{
                    "stableId": "detail-mixed",
                    "name": "混写详情",
                    "content": "黑发，语气克制。",
                    "tags": ["kind:appearance", "kind:speech"],
                }],
            }),
            "character.detail-mixed-kinds",
        ),
        (
            lambda value: value["resources"]["statusTables"].append({
                "stableId": "status-scene",
                "name": "当前场景",
                "statusKind": "scene",
                "rows": [
                    {
                        "key": "时间",
                        "value": "1 年 1 月 1 日 9 时",
                        "updateRule": "每 3 回合延迟更新。",
                    },
                    {"key": "位置", "value": "车站"},
                    {"key": "在场人物", "value": "林澈"},
                ],
            }),
            "status.update-rule-scheduling",
        ),
        (
            lambda value: value["resources"]["plotSchedule"].update({
                "pools": [{"stableId": "pool-main", "name": "主线"}],
                "events": [{
                    "stableId": "event-control",
                    "poolRef": "pool-main",
                    "title": "强制选择",
                    "directive": "玩家必须答应 NPC 的要求。",
                    "description": "",
                    "dispatchMode": "soft",
                }],
                "outlines": [],
            }),
            "plot.directive-controls-player",
        ),
        (
            lambda value: value["resources"]["visualCatalog"].append({
                "stableId": "visual-missing",
                "assetType": "scene",
                "title": "未知人物",
                "prompt": "雨夜中的未知人物。",
                "subjectRefs": ["character-not-found"],
                "visualAnchors": [],
            }),
            "visual.subject-ref-unresolved",
        ),
        (
            lambda value: value["resources"]["lorebook"].append({
                "stableId": "lore-empty",
                "name": "空地点",
                "content": "",
            }),
            "lorebook.content-empty",
        ),
        (
            lambda value: value["openQuestions"].append({
                "id": "question-ending",
                "question": "结局是否开放？",
                "status": "open",
            }),
            "workflow.open-question-unresolved",
        ),
    ],
)
def test_forward_authoring_scenarios_emit_expected_rule(
    mutate,
    expected_rule: str,
) -> None:
    value = _document().model_dump(by_alias=True)
    mutate(value)
    document = StoryDesignDocument.model_validate(value)

    diagnostics = evaluate_authoring_diagnostics(
        document,
        profile="draft",
    )

    assert expected_rule in {
        item["ruleId"] for item in diagnostics
    }


def test_authoring_diagnostics_match_viewer_and_portable_pack_validator() -> None:
    value = _document().model_dump(by_alias=True)
    value["story"]["summary"] = "过长摘要" * 61
    value["resources"]["characters"] = [{
        "stableId": "character-review",
        "name": "审阅员",
        "description": "调查员，性格谨慎。",
        "details": [{
            "stableId": "detail-review-mixed",
            "name": "混写详情",
            "content": "黑发，说话方式克制。",
            "tags": ["kind:appearance", "kind:speech"],
        }],
    }]
    value["resources"]["statusTables"] = [{
        "stableId": "status-review-scene",
        "name": "当前场景",
        "statusKind": "scene",
        "rows": [
            {
                "key": "时间",
                "value": "1 年 1 月 1 日 9 时",
                "updateRule": "每 3 回合延迟更新。",
            },
            {"key": "位置", "value": "车站"},
            {"key": "在场人物", "value": "审阅员"},
        ],
    }]
    value["resources"]["plotSchedule"] = {
        "pools": [{"stableId": "pool-review", "name": "审阅池"}],
        "events": [{
            "stableId": "event-review",
            "poolRef": "pool-review",
            "title": "强制玩家",
            "description": "",
            "directive": "玩家必须答应 NPC 的要求。",
            "dispatchMode": "soft",
        }],
        "outlines": [],
    }
    value["resources"]["lorebook"] = [{
        "stableId": "lore-review",
        "name": "空地点",
        "content": "",
    }]
    value["resources"]["narrativeStyles"] = [{
        "stableId": "style-review",
        "name": "空风格",
        "prompt": "",
    }]
    value["resources"]["visualCatalog"] = [{
        "stableId": "visual-review",
        "assetType": "scene",
        "title": "未知人物",
        "prompt": "雨夜中的未知人物。",
        "subjectRefs": ["character-not-found"],
        "visualAnchors": [],
    }]
    document = StoryDesignDocument.model_validate(value)
    catalog = authoring_rules_catalog()
    expected = evaluate_authoring_diagnostics(
        document,
        profile="package",
    )

    viewer_module = runpy.run_path("DesignProject/viewer/serve.py")
    viewer = viewer_module["_authoring_diagnostics"](
        document.model_dump(by_alias=True),
        catalog,
        profile="package",
    )
    pack = build_story_pack(
        document,
        source_revision="r000001",
        source_digest="0" * 64,
        generated_at="2026-07-24T09:00:00Z",
    ).model_dump(by_alias=True, exclude_none=True)
    validator_module = runpy.run_path(
        "DesignProject/.agents/skills/rpg-story-authoring/scripts/"
        "validate_story_pack.py"
    )
    portable = validator_module["authoring_diagnostics"](pack, catalog)

    assert viewer == expected
    assert portable == expected


def test_managed_rule_refresh_preserves_design_and_release_artifacts(
    tmp_path,
) -> None:
    root = tmp_path / "DesignProject"
    shutil.copytree("DesignProject", root)
    protected = [
        root / "design/current.json",
        root / "design/revisions/r000001.json",
        root / "design/checkpoints/.gitkeep",
        root / "artifacts/story-packs/.gitkeep",
        root / "integrations/rpg-world.json",
    ]
    before = {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in protected
    }
    managed = (
        root
        / ".agents/skills/rpg-story-authoring/references/"
        "fields-status-scene.md"
    )
    managed.write_text(
        managed.read_text(encoding="utf-8") + "\nmanual drift\n",
        encoding="utf-8",
    )
    store = DesignProjectStore(root)

    preview = store.preview_authoring_rules_refresh()
    assert preview["changedAssetCount"] == 1
    assert preview["designRevisionChanged"] is False
    applied = store.apply_authoring_rules_refresh(
        preview["operationId"]
    )
    repeated = store.apply_authoring_rules_refresh(
        preview["operationId"]
    )

    assert applied["status"] == "applied"
    assert repeated["status"] == "already_applied"
    assert store.get_current()["revision"] == "r000001"
    assert store.doctor()["healthy"] is True
    assert before == {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in protected
    }


def test_doctor_rejects_external_authoring_catalog_path(tmp_path) -> None:
    root = tmp_path / "DesignProject"
    shutil.copytree("DesignProject", root)
    external = tmp_path / "outside-rules.json"
    external.write_text("{}", encoding="utf-8")
    manifest_path = root / "design-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["paths"]["authoringRules"] = str(external)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    result = DesignProjectStore(root).doctor()

    assert result["healthy"] is False
    assert any(
        "manifest path authoringRules is not portable" in message
        for message in result["errors"]
    )
    assert any(
        "cannot verify authoring-rule catalog" in message
        for message in result["errors"]
    )


def test_rule_refresh_rejects_manifest_change_after_preview(tmp_path) -> None:
    root = tmp_path / "DesignProject"
    shutil.copytree("DesignProject", root)
    store = DesignProjectStore(root)
    preview = store.preview_authoring_rules_refresh()
    manifest_path = root / "design-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contractDigest"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(
        DesignConflictError,
        match="changed after preview",
    ):
        store.apply_authoring_rules_refresh(preview["operationId"])


def test_v1_rule_refresh_is_rejected_without_any_write(tmp_path) -> None:
    root = tmp_path / "legacy"
    shutil.copytree("DesignProject", root)
    manifest_path = root / "design-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schemaVersion"] = "story-design-project/1.0"
    manifest["contractVersion"] = "1.0"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    before = {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    store = DesignProjectStore(root)

    with pytest.raises(DesignStoreError, match="unsupported DesignProject"):
        store.preview_authoring_rules_refresh()
    with pytest.raises(DesignStoreError, match="unsupported DesignProject"):
        store.apply_authoring_rules_refresh("not-a-real-operation")

    after = {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
