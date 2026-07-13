from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rpg_core.agent.sub_agents.status_sub_agent as status_module
from rpg_data.models import STATUS_KIND_NORMAL, STATUS_KIND_SCENE, StatusTableDocument, StatusTableRow
from rpg_core.agent.transaction.status_scratch import ScratchStatusManager, StatusDocumentScratch
from rpg_core.agent.sub_agents import (
    StatusSubAgent,
    StatusSubAgentRecordStatus,
    SubAgentContext,
)
from rpg_core.agent.tools import BaseTool
from rpg_core.context.rpg_context import Message, Role
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.scene import SceneTracker
from rpg_core.status.tools import StatusTableSetValuesTool, StatusTableToolProvider, StatusWritePolicy


def _document(*rows: tuple[str, str]) -> StatusTableDocument:
    return StatusTableDocument.from_rows(
        rows=[StatusTableRow(key, value) for key, value in rows]
    )


class FakeRuntimeStatusManager:
    session_id = "s_main"

    def __init__(self, *, normal_rows: tuple[tuple[str, str], ...] = (("生命", "10"),)) -> None:
        self.documents = {
            1: _document(*normal_rows),
            2: _document(("位置", "森林")),
        }
        self.saved: list[tuple[int, StatusTableDocument, dict[str, object]]] = []

    def _table(self, table_id: int) -> dict[str, object]:
        document = self.documents[table_id]
        return {
            "id": table_id,
            "name": (
                "当前场景"
                if table_id == 2
                else "角色状态"
                if table_id == 1
                else f"状态表 {table_id}"
            ),
            "status_kind": STATUS_KIND_SCENE if table_id == 2 else STATUS_KIND_NORMAL,
            "description": "追踪已有状态",
            "headers": list(document.headers),
            "rows": [list(row) for row in document.data_rows],
            "document": document.to_json_dict(),
            "metadata_json": "{}",
        }

    def list_context_tables(self) -> list[dict[str, object]]:
        return [self._table(1)]

    def get_active_scene_table_ref(self):
        return 2, (STATUS_KIND_SCENE, "当前场景")

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        if table_id not in self.documents:
            raise FileNotFoundError(f"unavailable: {table_id}")
        return self._table(table_id)

    def get_table_document_by_id(self, table_id: int) -> StatusTableDocument:
        if table_id not in self.documents:
            raise FileNotFoundError(f"unavailable: {table_id}")
        return self.documents[table_id]

    def save_table_document(self, table_id: int, document: StatusTableDocument, **kwargs):
        self.saved.append((table_id, document, kwargs))
        self.documents[table_id] = document
        return self._table(table_id)


def _scratch_runtime(manager: FakeRuntimeStatusManager) -> tuple[StatusDocumentScratch, ScratchStatusManager]:
    scratch = StatusDocumentScratch(manager)
    return scratch, ScratchStatusManager(manager, scratch)


@pytest.mark.asyncio
async def test_status_table_tool_updates_existing_values_and_reports_no_op() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)
    tool = StatusTableSetValuesTool(runtime)

    changed = json.loads(await tool.execute(
        table_id=1,
        updates=[{"key": "生命", "value": "8"}],
    ))

    assert changed == {
        "ok": True,
        "tableId": 1,
        "tableName": "角色状态",
        "changed": True,
        "changes": [{"key": "生命", "oldValue": "10", "newValue": "8"}],
    }
    assert len(scratch.staged_changes) == 1
    assert manager.documents[1].data_rows == (("生命", "10"),)

    no_op = json.loads(await tool.execute(
        table_id=1,
        updates=[{"key": "生命", "value": "8"}],
    ))
    assert no_op["changed"] is False
    assert no_op["changes"] == []
    assert len(scratch.staged_changes) == 1

    scratch.commit()
    assert manager.documents[1].data_rows == (("生命", "8"),)
    assert manager.saved[0][2]["expected_status_kind"] == STATUS_KIND_NORMAL
    assert manager.saved[0][2]["base_document"].data_rows == (("生命", "10"),)


@pytest.mark.asyncio
async def test_status_table_tool_rejects_structure_and_access_errors() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)
    tool = StatusTableSetValuesTool(runtime)

    missing_table = json.loads(await tool.execute(
        table_id=999,
        updates=[{"key": "生命", "value": "8"}],
    ))
    missing_key = json.loads(await tool.execute(
        table_id=1,
        updates=[{"key": "不存在", "value": "8"}],
    ))
    scene = json.loads(await tool.execute(
        table_id=2,
        updates=[{"key": "位置", "value": "城堡"}],
    ))
    duplicate = json.loads(await tool.execute(
        table_id=1,
        updates=[{"key": "生命", "value": "8"}, {"key": "生命", "value": "7"}],
    ))
    empty = json.loads(await tool.execute(table_id=1, updates=[]))

    assert missing_table["errorCode"] == "table_unavailable"
    assert missing_table["message"] == "状态表不存在或当前 session 无权访问"
    assert missing_key["errorCode"] == "key_not_found"
    assert scene["errorCode"] == "unsupported_table_kind"
    assert duplicate["errorCode"] == "invalid_arguments"
    assert empty["errorCode"] == "invalid_arguments"
    assert scratch.staged_changes == []


def test_status_tool_provider_skips_empty_normal_tables() -> None:
    empty_manager = FakeRuntimeStatusManager(normal_rows=())
    _scratch, empty_runtime = _scratch_runtime(empty_manager)
    populated_manager = FakeRuntimeStatusManager()
    _scratch, populated_runtime = _scratch_runtime(populated_manager)

    assert StatusTableToolProvider(empty_runtime).get_tools() == []
    assert [tool.name for tool in StatusTableToolProvider(populated_runtime).get_tools()] == [
        "status_table_set_values"
    ]

    slow_manager = FakeRuntimeStatusManager()
    slow_manager.documents[1] = StatusTableDocument.from_rows(rows=[
        StatusTableRow("长期信任", "低", update_frequency="deferred"),
        StatusTableRow("人工备注", "无", update_frequency="manual"),
    ])
    _scratch, slow_runtime = _scratch_runtime(slow_manager)
    assert StatusTableToolProvider(slow_runtime).get_tools() == []


@pytest.mark.asyncio
async def test_status_tool_enforces_frequency_and_scoped_key_policy() -> None:
    manager = FakeRuntimeStatusManager()
    manager.documents[1] = StatusTableDocument.from_rows(rows=[
        StatusTableRow("生命", "10"),
        StatusTableRow(
            "关系事件",
            "无",
            update_frequency="event_driven",
            update_rule="明确结盟时更新",
        ),
        StatusTableRow("长期信任", "低", update_frequency="deferred"),
        StatusTableRow("隐藏设定", "是", update_frequency="manual"),
    ])
    _scratch, runtime = _scratch_runtime(manager)
    default_tool = StatusTableSetValuesTool(runtime)

    blocked_deferred = json.loads(await default_tool.execute(
        table_id=1,
        updates=[{"key": "长期信任", "value": "中"}],
    ))
    blocked_manual = json.loads(await default_tool.execute(
        table_id=1,
        updates=[{"key": "隐藏设定", "value": "否"}],
    ))
    assert blocked_deferred["errorCode"] == "write_not_allowed"
    assert blocked_manual["errorCode"] == "write_not_allowed"

    scoped = StatusTableSetValuesTool(
        runtime,
        write_policy=StatusWritePolicy(
            allowed_keys={1: frozenset({"生命"})},
        ),
    )
    blocked_event = json.loads(await scoped.execute(
        table_id=1,
        updates=[{"key": "关系事件", "value": "已结盟"}],
    ))
    changed = json.loads(await scoped.execute(
        table_id=1,
        updates=[{"key": "生命", "value": "8"}],
    ))
    assert blocked_event["errorCode"] == "write_not_allowed"
    assert changed["changed"] is True


def test_status_scratch_removes_net_no_op_document() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)

    runtime.runtime_set_existing_values(1, [("生命", "8")])
    assert scratch.change_token
    runtime.runtime_set_existing_values(1, [("生命", "10")])

    assert scratch.change_token == ()
    assert scratch.staged_changes == []


def test_status_scratch_keeps_first_read_snapshot_during_turn() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)

    assert runtime.list_context_tables()[0]["rows"] == [["生命", "10"]]
    manager.documents[1] = _document(("生命", "9"))

    assert runtime.list_context_tables()[0]["rows"] == [["生命", "10"]]
    result = runtime.runtime_set_existing_values(1, [("生命", "8")])
    assert result.changes[0].old_value == "10"
    assert scratch.staged_changes[0].base_document.data_rows == (("生命", "10"),)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value", "expected_updated", "expected_status"),
    [
        ("生命", "10", False, StatusSubAgentRecordStatus.NO_OP),
        ("生命", "8", True, StatusSubAgentRecordStatus.CHANGED),
        ("不存在", "8", False, StatusSubAgentRecordStatus.ERROR),
    ],
)
async def test_status_sub_agent_updated_tracks_actual_scratch_change(
    key: str,
    value: str,
    expected_updated: bool,
    expected_status: StatusSubAgentRecordStatus,
) -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)
    tool = StatusTableSetValuesTool(runtime)

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools[0]["function"]["name"] == "status_table_set_values"
            return {
                "tool_calls": [{
                    "function": {
                        "name": "status_table_set_values",
                        "arguments": json.dumps({
                            "table_id": 1,
                            "updates": [{"key": key, "value": value}],
                        }),
                    },
                }],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([tool])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.update(
        history=[Message(Role.USER, "old")],
        state_context="status",
        user_input="act",
    )

    assert result.updated is expected_updated
    assert result.records[0].changed is expected_updated
    assert result.records[0].status is expected_status
    assert result.records[0].success is (
        expected_status is not StatusSubAgentRecordStatus.ERROR
    )


class _OutcomeTool(BaseTool):
    name = NARRATIVE_OUTCOME_TOOL_NAME
    description = "test outcome"

    def __init__(self) -> None:
        self.calls = 0

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        }

    async def execute(self, **kwargs: object) -> str:
        self.calls += 1
        return json.dumps(
            {
                "outcomeCode": "success_with_cost",
                "label": "成功但有代价",
                "narrativeGuidance": "达成目标并引入代价。",
                "reason": str(kwargs["reason"]),
            },
            ensure_ascii=False,
        )


class _SceneAttrTool(BaseTool):
    name = "scene_attr"
    description = "test scene writer"

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        }

    async def execute(self, **kwargs: object) -> str:
        return json.dumps({"ok": True, "changed": bool(kwargs)})


@pytest.mark.asyncio
async def test_fixed_preflight_isolates_scene_and_routed_table_contexts(
    monkeypatch,
) -> None:
    manager = FakeRuntimeStatusManager()
    manager.documents[1] = StatusTableDocument.from_rows(rows=[
        StatusTableRow("生命", "RT_SENTINEL"),
        StatusTableRow("长期信任", "SLOW_SENTINEL", update_frequency="deferred"),
    ])
    scratch, runtime = _scratch_runtime(manager)

    class Provider:
        def __init__(self) -> None:
            self.stages: list[str] = []

        async def chat(self, messages, *, tools):  # noqa: ANN001
            names = {
                schema["function"]["name"]
                for schema in tools
            }
            user_content = str(messages[-1]["content"])
            if names == {NARRATIVE_OUTCOME_TOOL_NAME}:
                self.stages.append("outcome")
                assert "COMBINED_TABLE_SENTINEL" in user_content
                return {"tool_calls": []}
            if names == {"select_status_targets"}:
                self.stages.append("route")
                assert "COMBINED_TABLE_SENTINEL" in user_content
                return {
                    "tool_calls": [{
                        "function": {
                            "name": "select_status_targets",
                            "arguments": json.dumps({
                                "scene": True,
                                "tables": [{
                                    "table_id": 1,
                                    "realtime_keys": ["生命"],
                                    "event_keys": [],
                                    "reason": "本轮生命值相关",
                                }],
                            }, ensure_ascii=False),
                        },
                    }],
                }
            if names == {"scene_attr"}:
                self.stages.append("scene")
                assert "SCENE_SENTINEL" in user_content
                assert "COMBINED_TABLE_SENTINEL" not in user_content
                assert "SLOW_SENTINEL" not in user_content
                return {"tool_calls": []}
            if names == {"status_table_set_values"}:
                self.stages.append("table")
                assert "RT_SENTINEL" in user_content
                assert "SLOW_SENTINEL" not in user_content
                assert "SCENE_SENTINEL" not in user_content
                return {"tool_calls": []}
            raise AssertionError(f"unexpected schemas: {names}")

    provider = Provider()
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([
        _OutcomeTool(),
        _SceneAttrTool(),
        StatusTableSetValuesTool(runtime),
    ])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent._get_provider = lambda: provider  # type: ignore[method-assign]
    info = MagicMock()
    monkeypatch.setattr(
        status_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(status_module.logger, "info", info)

    context_tables = runtime.list_context_tables()
    result = await sub_agent.run_preflight(
        history=[],
        state_context="SCENE_SENTINEL\nCOMBINED_TABLE_SENTINEL",
        scene_context="SCENE_SENTINEL",
        context_tables=context_tables,
        user_input="检查状态",
    )

    assert result.failed is False
    assert provider.stages == ["outcome", "route", "scene", "table"]
    llm_started_sources = [
        call.args[1]
        for call in info.call_args_list
        if "LLM call started" in call.args[0]
    ]
    llm_completed_sources = [
        call.args[1]
        for call in info.call_args_list
        if "LLM call completed" in call.args[0]
    ]
    expected_sources = [
        "status_outcome_preflight",
        "status_router",
        "status_update:scene",
        "status_update:table:1",
    ]
    assert llm_started_sources == expected_sources
    assert llm_completed_sources == expected_sources
    target_sources = [
        call.args[1]
        for call in info.call_args_list
        if "update target started" in call.args[0]
    ]
    assert target_sources == ["status_update:scene", "status_update:table:1"]
    log_formats = [call.args[0] for call in info.call_args_list]
    assert any("preflight started" in message for message in log_formats)
    assert any("stage completed: stage=outcome" in message for message in log_formats)
    assert any("stage completed: stage=router" in message for message in log_formats)
    assert any("stage completed: stage=state_updates" in message for message in log_formats)
    assert any("preflight completed" in message for message in log_formats)


@pytest.mark.asyncio
async def test_fixed_preflight_keeps_other_targets_when_provider_fails() -> None:
    manager = FakeRuntimeStatusManager()
    manager.documents[3] = _document(("法力", "5"))
    manager.documents[4] = _document(("线索", "0"))
    manager.list_context_tables = lambda: [  # type: ignore[method-assign]
        manager._table(table_id) for table_id in (1, 3, 4)
    ]
    scratch, runtime = _scratch_runtime(manager)

    class Provider:
        def __init__(self) -> None:
            self.stages: list[str] = []

        async def chat(self, messages, *, tools):  # noqa: ANN001
            names = {schema["function"]["name"] for schema in tools}
            if names == {"select_status_targets"}:
                self.stages.append("route")
                return {
                    "tool_calls": [{
                        "function": {
                            "name": "select_status_targets",
                            "arguments": json.dumps({
                                "scene": False,
                                "tables": [
                                    {
                                        "table_id": table_id,
                                        "realtime_keys": [key],
                                        "event_keys": [],
                                        "reason": "确定变化",
                                    }
                                    for table_id, key in (
                                        (1, "生命"),
                                        (3, "法力"),
                                        (4, "线索"),
                                    )
                                ],
                            }, ensure_ascii=False),
                        },
                    }],
                }

            selected = str(messages[-1]["content"])
            if "生命" in selected:
                self.stages.append("table:1")
                table_id, key, value = 1, "生命", "8"
            elif "法力" in selected:
                self.stages.append("table:3:error")
                raise RuntimeError("provider unavailable")
            else:
                self.stages.append("table:4")
                table_id, key, value = 4, "线索", "1"
            return {
                "tool_calls": [{
                    "function": {
                        "name": "status_table_set_values",
                        "arguments": json.dumps({
                            "table_id": table_id,
                            "updates": [{"key": key, "value": value}],
                        }, ensure_ascii=False),
                    },
                }],
            }

    provider = Provider()
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([StatusTableSetValuesTool(runtime)])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent.set_mutation_boundary(
        scratch.create_checkpoint,
        scratch.restore_checkpoint,
    )
    sub_agent._get_provider = lambda: provider  # type: ignore[method-assign]

    result = await sub_agent.run_preflight(
        history=[],
        state_context="status",
        scene_context="",
        context_tables=runtime.list_context_tables(),
        user_input="执行确定更新",
    )

    assert result.failed is True
    assert result.updated is True
    assert provider.stages == ["route", "table:1", "table:3:error", "table:4"]
    assert [change.table_id for change in scratch.staged_changes] == [1, 4]
    assert runtime.get_table_by_id(1)["rows"] == [["生命", "8"]]
    assert runtime.get_table_by_id(3)["rows"] == [["法力", "5"]]
    assert runtime.get_table_by_id(4)["rows"] == [["线索", "1"]]


@pytest.mark.asyncio
async def test_fixed_preflight_rolls_back_only_failed_table_target() -> None:
    manager = FakeRuntimeStatusManager()
    manager.documents[3] = _document(("法力", "5"))
    manager.documents[4] = _document(("线索", "0"))
    manager.list_context_tables = lambda: [  # type: ignore[method-assign]
        manager._table(table_id) for table_id in (1, 3, 4)
    ]
    scratch, runtime = _scratch_runtime(manager)

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            names = {schema["function"]["name"] for schema in tools}
            if names == {"select_status_targets"}:
                return {
                    "tool_calls": [{
                        "function": {
                            "name": "select_status_targets",
                            "arguments": json.dumps({
                                "scene": False,
                                "tables": [
                                    {
                                        "table_id": table_id,
                                        "realtime_keys": [key],
                                        "event_keys": [],
                                        "reason": "确定变化",
                                    }
                                    for table_id, key in (
                                        (1, "生命"),
                                        (3, "法力"),
                                        (4, "线索"),
                                    )
                                ],
                            }, ensure_ascii=False),
                        },
                    }],
                }

            selected = str(messages[-1]["content"])
            if "生命" in selected:
                calls = [(1, "生命", "8")]
            elif "法力" in selected:
                calls = [(3, "法力", "4"), (3, "不存在", "x")]
            else:
                calls = [(4, "线索", "1")]
            return {
                "tool_calls": [
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": table_id,
                                "updates": [{"key": key, "value": value}],
                            }, ensure_ascii=False),
                        },
                    }
                    for table_id, key, value in calls
                ],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([StatusTableSetValuesTool(runtime)])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent.set_mutation_boundary(
        scratch.create_checkpoint,
        scratch.restore_checkpoint,
    )
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.run_preflight(
        history=[],
        state_context="status",
        scene_context="",
        context_tables=runtime.list_context_tables(),
        user_input="执行确定更新",
    )

    assert result.failed is True
    assert result.updated is True
    assert [record.status for record in result.records] == [
        StatusSubAgentRecordStatus.CHANGED,
        StatusSubAgentRecordStatus.ROLLED_BACK_DUE_TO_FAILURE,
        StatusSubAgentRecordStatus.ERROR,
        StatusSubAgentRecordStatus.CHANGED,
    ]
    assert [change.table_id for change in scratch.staged_changes] == [1, 4]
    assert runtime.get_table_by_id(3)["rows"] == [["法力", "5"]]


@pytest.mark.asyncio
async def test_fixed_preflight_restores_failed_scene_and_continues_tables() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)
    scene_tracker = SceneTracker(allow_runtime_key_changes=True)
    scene_tracker.bind_status_manager(runtime)
    assert scene_tracker.load_from_status_table() is True

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            names = {schema["function"]["name"] for schema in tools}
            if names == {"select_status_targets"}:
                return {
                    "tool_calls": [{
                        "function": {
                            "name": "select_status_targets",
                            "arguments": json.dumps({
                                "scene": True,
                                "tables": [{
                                    "table_id": 1,
                                    "realtime_keys": ["生命"],
                                    "event_keys": [],
                                    "reason": "确定变化",
                                }],
                            }, ensure_ascii=False),
                        },
                    }],
                }
            if "scene_time" in names:
                return {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "scene_time",
                                "arguments": json.dumps({"hour": 9}),
                            },
                        },
                        {
                            "function": {
                                "name": "status_table_set_values",
                                "arguments": json.dumps({
                                    "table_id": 1,
                                    "updates": [{"key": "生命", "value": "7"}],
                                }, ensure_ascii=False),
                            },
                        },
                    ],
                }
            return {
                "tool_calls": [{
                    "function": {
                        "name": "status_table_set_values",
                        "arguments": json.dumps({
                            "table_id": 1,
                            "updates": [{"key": "生命", "value": "8"}],
                        }, ensure_ascii=False),
                    },
                }],
            }

    def create_checkpoint() -> object:
        return scratch.create_checkpoint(), scene_tracker.get_time_state()

    def restore_checkpoint(checkpoint: object) -> None:
        status_checkpoint, scene_time = checkpoint  # type: ignore[misc]
        scratch.restore_checkpoint(status_checkpoint)
        scene_tracker.set_time_state(scene_time)

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([
        *scene_tracker.get_tools(),
        StatusTableSetValuesTool(runtime),
    ])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent.set_mutation_boundary(create_checkpoint, restore_checkpoint)
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.run_preflight(
        history=[],
        state_context="status",
        scene_context=scene_tracker.get_context(),
        context_tables=runtime.list_context_tables(),
        user_input="时间推进并受伤",
    )

    assert result.failed is True
    assert result.updated is True
    assert scene_tracker.get_time_state()["hour"] == 6
    assert [change.table_id for change in scratch.staged_changes] == [1]
    assert runtime.get_table_by_id(1)["rows"] == [["生命", "8"]]
    assert runtime.get_table_by_id(2)["rows"] == [["位置", "森林"]]
    assert [record.status for record in result.records] == [
        StatusSubAgentRecordStatus.ROLLED_BACK_DUE_TO_FAILURE,
        StatusSubAgentRecordStatus.ERROR,
        StatusSubAgentRecordStatus.CHANGED,
    ]


def test_status_sub_agent_turn_tool_scope_restores_owned_bindings() -> None:
    manager = FakeRuntimeStatusManager()
    _scratch, runtime = _scratch_runtime(manager)
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    original_tool = _OutcomeTool()
    sub_agent.register_tools([original_tool])
    original_probe = lambda: "original"  # noqa: E731
    original_checkpoint = lambda: "checkpoint"  # noqa: E731
    original_restore = lambda _checkpoint: None  # noqa: E731
    sub_agent.set_mutation_probe(original_probe)
    sub_agent.set_mutation_boundary(original_checkpoint, original_restore)

    turn_probe = lambda: "turn"  # noqa: E731
    turn_checkpoint = lambda: "turn-checkpoint"  # noqa: E731
    turn_restore = lambda _checkpoint: None  # noqa: E731
    with pytest.raises(RuntimeError, match="leave turn scope"):
        with sub_agent.use_turn_tools(
            [StatusTableSetValuesTool(runtime)],
            mutation_probe=turn_probe,
            create_checkpoint=turn_checkpoint,
            restore_checkpoint=turn_restore,
        ):
            assert [
                schema["function"]["name"] for schema in sub_agent._schemas
            ] == ["status_table_set_values"]
            assert sub_agent._mutation_probe is turn_probe
            assert sub_agent._mutation_checkpoint is turn_checkpoint
            assert sub_agent._mutation_restore is turn_restore
            raise RuntimeError("leave turn scope")

    assert [schema["function"]["name"] for schema in sub_agent._schemas] == [
        NARRATIVE_OUTCOME_TOOL_NAME
    ]
    assert sub_agent._mutation_probe is original_probe
    assert sub_agent._mutation_checkpoint is original_checkpoint
    assert sub_agent._mutation_restore is original_restore


@pytest.mark.asyncio
async def test_status_sub_agent_outcome_batch_skips_all_state_prewrites() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)
    outcome_tool = _OutcomeTool()

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert {schema["function"]["name"] for schema in tools} == {
                NARRATIVE_OUTCOME_TOOL_NAME,
                "status_table_set_values",
            }
            return {
                "tool_calls": [
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": 1,
                                "updates": [{"key": "生命", "value": "1"}],
                            }),
                        },
                    },
                    {
                        "function": {
                            "name": NARRATIVE_OUTCOME_TOOL_NAME,
                            "arguments": json.dumps({"reason": "能否脱离伏击"}),
                        },
                    },
                    {
                        "function": {
                            "name": "scene_attr",
                            "arguments": json.dumps({"key": "位置", "value": "安全屋"}),
                        },
                    },
                ],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([
        outcome_tool,
        StatusTableSetValuesTool(runtime),
    ])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.update(
        history=[Message(Role.ASSISTANT, "伏击仍未解决")],
        state_context="status",
        user_input="我冲出去并抵达安全屋",
    )

    assert result.outcome_requested is True
    assert result.outcome_staged is True
    assert result.updated is False
    assert result.failed is False
    assert result.state_prewrites_skipped == 2
    assert [record.status for record in result.records] == [
        StatusSubAgentRecordStatus.SKIPPED_DUE_TO_OUTCOME,
        StatusSubAgentRecordStatus.OUTCOME_STAGED,
        StatusSubAgentRecordStatus.SKIPPED_DUE_TO_OUTCOME,
    ]
    assert outcome_tool.calls == 1
    assert scratch.staged_changes == []
    assert manager.documents[1].row_for_key("生命").value == "10"


def test_status_sub_agent_prompt_and_schema_only_include_outcome_when_mounted() -> None:
    manager = FakeRuntimeStatusManager()
    _scratch, runtime = _scratch_runtime(manager)
    state_tool = StatusTableSetValuesTool(runtime)
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    with sub_agent.use_turn_tools(
        [state_tool],
        mutation_probe=None,
        create_checkpoint=None,
        restore_checkpoint=None,
        outcome_preflight_enabled=False,
    ):
        assert NARRATIVE_OUTCOME_TOOL_NAME not in sub_agent.system_prompt
        assert [schema["function"]["name"] for schema in sub_agent._schemas] == [
            "status_table_set_values"
        ]

    with sub_agent.use_turn_tools(
        [_OutcomeTool(), state_tool],
        mutation_probe=None,
        create_checkpoint=None,
        restore_checkpoint=None,
        outcome_preflight_enabled=True,
    ):
        assert NARRATIVE_OUTCOME_TOOL_NAME in sub_agent.system_prompt
        assert NARRATIVE_OUTCOME_TOOL_NAME in [
            schema["function"]["name"] for schema in sub_agent._schemas
        ]


def test_status_sub_agent_prompt_uses_actual_value_only_scene_tools() -> None:
    manager = FakeRuntimeStatusManager()
    _scratch, runtime = _scratch_runtime(manager)
    scene_tracker = SceneTracker()
    scene_tracker.bind_status_manager(runtime)
    assert scene_tracker.load_from_status_table() is True
    tools = [
        *scene_tracker.get_tools(),
        StatusTableSetValuesTool(runtime),
    ]
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")

    with sub_agent.use_turn_tools(
        tools,
        mutation_probe=None,
        create_checkpoint=None,
        restore_checkpoint=None,
        outcome_preflight_enabled=False,
    ):
        prompt = sub_agent.system_prompt
        assert "scene_attr" in prompt
        assert "status_table_set_values" in prompt
        assert "scene_time" not in prompt
        assert "scene_del_attr" not in prompt
        assert "主动清理" not in prompt
        assert "只能修改已有 key 的 value" in prompt
        assert "value 更新为空字符串或当前适用值" in prompt
        attr_schema = next(
            schema
            for schema in sub_agent._schemas
            if schema["function"]["name"] == "scene_attr"
        )
        assert attr_schema["function"]["parameters"]["properties"]["key"]["enum"] == [
            "位置"
        ]


def test_status_sub_agent_prompt_retains_structural_guidance_when_enabled() -> None:
    manager = FakeRuntimeStatusManager()
    _scratch, runtime = _scratch_runtime(manager)
    scene_tracker = SceneTracker(allow_runtime_key_changes=True)
    scene_tracker.bind_status_manager(runtime)
    assert scene_tracker.load_from_status_table() is True
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")

    with sub_agent.use_turn_tools(
        scene_tracker.get_tools(),
        mutation_probe=None,
        create_checkpoint=None,
        restore_checkpoint=None,
        outcome_preflight_enabled=False,
    ):
        prompt = sub_agent.system_prompt
        assert "scene_time / scene_attr / scene_del_attr" in prompt
        assert "主动清理" in prompt
        assert "使用 scene_del_attr 将其移除" in prompt


@pytest.mark.asyncio
async def test_status_route_cannot_select_scene_without_scene_tools() -> None:
    manager = FakeRuntimeStatusManager()
    _scratch, runtime = _scratch_runtime(manager)

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert [schema["function"]["name"] for schema in tools] == [
                "select_status_targets"
            ]
            scene_schema = tools[0]["function"]["parameters"]["properties"]["scene"]
            assert scene_schema["const"] is False
            return {
                "tool_calls": [{
                    "function": {
                        "name": "select_status_targets",
                        "arguments": json.dumps({"scene": True, "tables": []}),
                    },
                }],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([StatusTableSetValuesTool(runtime)])
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.run_preflight(
        history=[],
        state_context="status",
        scene_context="scene is read-only",
        context_tables=runtime.list_context_tables(),
        user_input="检查场景",
    )

    assert result.failed is False
    assert result.route is not None
    assert result.route.scene is False
    assert result.records == []


@pytest.mark.asyncio
async def test_status_sub_agent_failed_state_target_restores_its_prewrites() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools[0]["function"]["name"] == "status_table_set_values"
            return {
                "tool_calls": [
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": 1,
                                "updates": [{"key": "生命", "value": "8"}],
                            }),
                        },
                    },
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": 1,
                                "updates": [{"key": "不存在", "value": "x"}],
                            }),
                        },
                    },
                ],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([StatusTableSetValuesTool(runtime)])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent.set_mutation_boundary(
        scratch.create_checkpoint,
        scratch.restore_checkpoint,
    )
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    result = await sub_agent.update(
        history=[],
        state_context="status",
        user_input="更新两个值",
    )

    assert result.failed is True
    assert result.updated is False
    assert (
        result.records[0].status
        is StatusSubAgentRecordStatus.ROLLED_BACK_DUE_TO_FAILURE
    )
    assert result.records[1].status is StatusSubAgentRecordStatus.ERROR
    assert scratch.staged_changes == []
    assert manager.documents[1].row_for_key("生命").value == "10"


@pytest.mark.asyncio
async def test_status_sub_agent_checkpoint_restore_failure_remains_fatal() -> None:
    manager = FakeRuntimeStatusManager()
    scratch, runtime = _scratch_runtime(manager)

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools[0]["function"]["name"] == "status_table_set_values"
            return {
                "tool_calls": [
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": 1,
                                "updates": [{"key": "生命", "value": "8"}],
                            }),
                        },
                    },
                    {
                        "function": {
                            "name": "status_table_set_values",
                            "arguments": json.dumps({
                                "table_id": 1,
                                "updates": [{"key": "不存在", "value": "x"}],
                            }),
                        },
                    },
                ],
            }

    def fail_restore(_checkpoint: object) -> None:
        raise RuntimeError("restore unavailable")

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent.register_tools([StatusTableSetValuesTool(runtime)])
    sub_agent.set_mutation_probe(lambda: scratch.change_token)
    sub_agent.set_mutation_boundary(scratch.create_checkpoint, fail_restore)
    sub_agent._get_provider = lambda: Provider()  # type: ignore[method-assign]

    with pytest.raises(
        RuntimeError,
        match="failed to restore status update target checkpoint",
    ):
        await sub_agent.update(
            history=[],
            state_context="status",
            user_input="更新两个值",
        )
