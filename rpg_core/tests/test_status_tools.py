from __future__ import annotations

import json

import pytest

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
from rpg_core.status.tools import StatusTableSetValuesTool, StatusTableToolProvider


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
            "name": "角色状态" if table_id == 1 else "当前场景",
            "status_kind": STATUS_KIND_NORMAL if table_id == 1 else STATUS_KIND_SCENE,
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


@pytest.mark.asyncio
async def test_status_sub_agent_failed_state_batch_restores_all_prewrites() -> None:
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
