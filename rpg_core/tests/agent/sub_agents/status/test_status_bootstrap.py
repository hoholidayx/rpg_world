from __future__ import annotations

import json

import pytest

from rpg_data import models
from rpg_core.agent.sub_agents import (
    StatusBootstrapCoordinator,
    StatusSubAgent,
    SubAgentContext,
    select_status_bootstrap_history,
)
from rpg_core.context.models import Message, Role
from rpg_core.scene import SceneTracker
from tests.support.scripted_llm import response


def _document() -> models.StatusTableDocument:
    return models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow("生命", "10"),
        models.StatusTableRow(
            "长期信任",
            "低",
            update_rule="长期信任事实明确变化时更新",
        ),
        models.StatusTableRow(
            "人工备注",
            "保留",
        ),
    ])


class _StatusManager:
    session_id = "derived"

    def __init__(self) -> None:
        self.document = _document()
        self.commits: list[dict[str, object]] = []

    def _table(self) -> dict[str, object]:
        return {
            "id": 1,
            "name": "角色状态",
            "status_kind": models.STATUS_KIND_NORMAL,
            "description": "派生状态",
            "document": self.document.to_json_dict(),
            "headers": list(self.document.headers),
            "rows": [list(row) for row in self.document.data_rows],
        }

    def list_context_tables(self) -> list[dict[str, object]]:
        return [self._table()]

    def get_active_scene_table_ref(self):  # noqa: ANN201
        return None

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        if table_id != 1:
            raise FileNotFoundError(table_id)
        return self._table()

    def get_table_document_by_id(self, table_id: int) -> models.StatusTableDocument:
        if table_id != 1:
            raise FileNotFoundError(table_id)
        return self.document

    def commit_bootstrap_state(
        self,
        changes,
    ) -> None:  # noqa: ANN001
        changes = list(changes)
        self.commits.append({"changes": changes})
        for change in changes:
            self.document = change.document


def _history() -> list[Message]:
    return [
        Message(Role.USER, "旧行动", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "旧结果", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "题外", mode="ooc", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "题外回复", mode="ooc", turn_id=2, seq_in_turn=2),
        Message(Role.USER, "受伤", mode="gm", turn_id=3, seq_in_turn=1),
        Message(Role.ASSISTANT, "生命降为八", mode="gm", turn_id=3, seq_in_turn=2),
        Message(Role.USER, "未完成", turn_id=4, seq_in_turn=1),
    ]


def test_select_status_bootstrap_history_uses_complete_world_turns_only() -> None:
    selected = select_status_bootstrap_history(
        _history(),
        boundary_turn_id=4,
        history_rounds=2,
    )

    assert [(message.turn_id, message.content) for message in selected] == [
        (1, "旧行动"),
        (1, "旧结果"),
        (3, "受伤"),
        (3, "生命降为八"),
    ]


def test_select_status_bootstrap_history_requires_explicit_contiguous_closed_turns() -> None:
    selected = select_status_bootstrap_history(
        [
            Message(Role.ASSISTANT, "开场白", turn_id=1, seq_in_turn=1),
            Message(Role.USER, "序号缺口", turn_id=2, seq_in_turn=1),
            Message(Role.ASSISTANT, "不应采用", turn_id=2, seq_in_turn=3),
            Message(Role.USER, "不从一开始", turn_id=3, seq_in_turn=2),
            Message(Role.ASSISTANT, "同样不应采用", turn_id=3, seq_in_turn=3),
            Message(Role.USER, "尚未收束", turn_id=4, seq_in_turn=1),
            Message(Role.ASSISTANT, "中间回复", turn_id=4, seq_in_turn=2),
            Message(Role.USER, "最后仍是用户", turn_id=4, seq_in_turn=3),
            Message(Role.USER, "完整行动", mode="gm", turn_id=5, seq_in_turn=1),
            Message(Role.ASSISTANT, "完整结果", mode="gm", turn_id=5, seq_in_turn=2),
            Message(Role.TOOL, "工具尾声", mode="gm", turn_id=5, seq_in_turn=3),
        ],
        boundary_turn_id=5,
        history_rounds=10,
    )

    assert [(message.turn_id, message.content) for message in selected] == [
        (5, "完整行动"),
        (5, "完整结果"),
    ]


@pytest.mark.asyncio
async def test_bootstrap_updates_all_fields_and_commits_once() -> None:
    manager = _StatusManager()

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            assert {tool["function"]["name"] for tool in tools} == {
                "status_table_edit_fields",
                "status_table_set_values",
            }
            prompt = str(messages[-1]["content"])
            assert "生命降为八" in prompt
            assert "题外回复" not in prompt
            assert "人工备注" in prompt
            assert "长期信任事实明确变化时更新" in prompt
            return response(tool_calls=[{
                    "function": {
                        "name": "status_table_set_values",
                        "arguments": json.dumps({
                            "table_id": 1,
                            "updates": [
                                {"key": "生命", "value": "8"},
                                {"key": "长期信任", "value": "中"},
                                {"key": "人工备注", "value": "已核实"},
                            ],
                        }),
                    }
                }])

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=4,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is False
    assert result.updated is True
    assert result.processed_turns == 2
    assert manager.document.row_for_key("生命").value == "8"  # type: ignore[union-attr]
    assert manager.document.row_for_key("长期信任").value == "中"  # type: ignore[union-attr]
    assert manager.document.row_for_key("人工备注").value == "已核实"  # type: ignore[union-attr]
    assert len(manager.commits) == 1


@pytest.mark.asyncio
async def test_bootstrap_prompt_keeps_long_message_tail() -> None:
    manager = _StatusManager()
    tail_marker = "TAIL-STATUS-FACT-MUST-REACH-BOOTSTRAP"
    long_result = "x" * 900 + tail_marker

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            assert {tool["function"]["name"] for tool in tools} == {
                "status_table_edit_fields",
                "status_table_set_values",
            }
            assert tail_marker in str(messages[-1]["content"])
            return response()

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=[
            Message(Role.USER, "行动", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, long_result, turn_id=1, seq_in_turn=2),
        ],
        boundary_turn_id=1,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is False
    assert result.processed_turns == 1
    assert len(manager.commits) == 1


@pytest.mark.asyncio
async def test_bootstrap_rebuilds_dynamic_field_in_empty_normal_table() -> None:
    manager = _StatusManager()
    manager.document = models.StatusTableDocument.from_rows(rows=[])

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            assert {tool["function"]["name"] for tool in tools} == {
                "status_table_edit_fields"
            }
            prompt = str(messages[-1]["content"])
            assert "生命降为八" in prompt
            assert '"rows": []' in prompt
            return response(tool_calls=[{
                "function": {
                    "name": "status_table_edit_fields",
                    "arguments": json.dumps({
                        "table_id": 1,
                        "creates": [{
                            "key": "当前伤势",
                            "value": "受伤，生命降为八",
                        }],
                        "renames": [],
                        "deletes": [],
                    }),
                },
            }])

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=4,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is False
    assert result.updated is True
    rebuilt = manager.document.row_for_key("当前伤势")
    assert rebuilt is not None
    assert rebuilt.value == "受伤，生命降为八"
    assert rebuilt.runtime_key_locked is False
    assert rebuilt.update_rule == ""
    assert rebuilt.metadata == {}
    assert len(manager.commits) == 1


@pytest.mark.asyncio
async def test_disabled_bootstrap_without_complete_history_skips_cleanly() -> None:
    manager = _StatusManager()

    class Provider:
        async def chat(self, *_args, **_kwargs):  # noqa: ANN001
            raise AssertionError("bootstrap must not call the LLM without a complete turn")

    sub_agent = StatusSubAgent(
        provider_biz_key="agent.status_sub_agent",
        enabled=False,
    )
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=[Message(Role.ASSISTANT, "开场", turn_id=1, seq_in_turn=1)],
        boundary_turn_id=1,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is False
    assert result.processed_turns == 0
    assert manager.commits[0]["changes"] == []


@pytest.mark.asyncio
async def test_disabled_bootstrap_with_complete_history_and_normal_target_fails() -> None:
    manager = _StatusManager()

    class Provider:
        async def chat(self, *_args, **_kwargs):  # noqa: ANN001
            raise AssertionError("disabled bootstrap must not call the LLM")

    sub_agent = StatusSubAgent(
        provider_biz_key="agent.status_sub_agent",
        enabled=False,
    )
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=4,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is True
    assert result.processed_turns == 2
    assert manager.commits == []


@pytest.mark.asyncio
async def test_disabled_bootstrap_with_empty_structural_target_fails() -> None:
    manager = _StatusManager()
    manager.document = models.StatusTableDocument.from_rows(rows=[])
    sub_agent = StatusSubAgent(
        provider_biz_key="agent.status_sub_agent",
        enabled=False,
    )
    sub_agent.bind_context(SubAgentContext())

    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=4,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is True
    assert result.processed_turns == 2
    assert len(manager.commits) == 0


class _SceneStatusManager:
    session_id = "derived_scene"

    def __init__(self) -> None:
        self.documents = {
            1: _document(),
            2: models.StatusTableDocument.from_rows(rows=[
                models.StatusTableRow("位置", "森林"),
            ]),
        }
        self.committed_table_ids: list[int] = []

    def _table(self, table_id: int) -> dict[str, object]:
        document = self.documents[table_id]
        return {
            "id": table_id,
            "name": "当前场景" if table_id == 2 else "角色状态",
            "status_kind": (
                models.STATUS_KIND_SCENE if table_id == 2 else models.STATUS_KIND_NORMAL
            ),
            "description": "状态",
            "document": document.to_json_dict(),
            "headers": list(document.headers),
            "rows": [list(row) for row in document.data_rows],
        }

    def list_context_tables(self) -> list[dict[str, object]]:
        return [self._table(1)]

    def get_active_scene_table_ref(self):  # noqa: ANN201
        return 2, (models.STATUS_KIND_SCENE, "当前场景")

    def get_scene_attrs(self) -> dict[str, str]:
        return dict(self.documents[2].data_rows)

    def get_scene_update_rules(self) -> dict[str, str]:
        return {
            row.key: row.update_rule
            for row in self.documents[2].rows
            if row.update_rule
        }

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        return self._table(table_id)

    def get_table_document_by_id(self, table_id: int) -> models.StatusTableDocument:
        return self.documents[table_id]

    def commit_bootstrap_state(
        self,
        changes,
    ) -> None:  # noqa: ANN001
        for change in changes:
            self.committed_table_ids.append(change.table_id)
            self.documents[change.table_id] = change.document


@pytest.mark.asyncio
async def test_disabled_bootstrap_with_complete_history_and_scene_target_fails() -> None:
    manager = _SceneStatusManager()
    manager.list_context_tables = lambda: []  # type: ignore[method-assign]
    sub_agent = StatusSubAgent(
        provider_biz_key="agent.status_sub_agent",
        enabled=False,
    )
    sub_agent.bind_context(SubAgentContext())
    scene = SceneTracker(allow_runtime_key_changes=False)
    scene.bind_status_manager(manager)  # type: ignore[arg-type]
    assert scene.load_from_status_table() is True

    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=3,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=scene,
    )

    assert result.failed is True
    assert result.processed_turns == 2
    assert manager.committed_table_ids == []


@pytest.mark.asyncio
async def test_bootstrap_scene_uses_scratch_and_publishes_with_other_documents() -> None:
    manager = _SceneStatusManager()

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            names = {tool["function"]["name"] for tool in tools}
            if names == {"scene_attr"}:
                return response(tool_calls=[{
                        "function": {
                            "name": "scene_attr",
                            "arguments": json.dumps({"key": "位置", "value": "城堡"}),
                        }
                    }])
            assert names == {
                "status_table_edit_fields",
                "status_table_set_values",
            }
            return response()

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    scene = SceneTracker(allow_runtime_key_changes=False)
    scene.bind_status_manager(manager)  # type: ignore[arg-type]
    assert scene.load_from_status_table() is True

    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=3,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=scene,
    )

    assert result.failed is False
    assert manager.committed_table_ids == [2]
    assert manager.documents[2].row_for_key("位置").value == "城堡"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_bootstrap_target_failure_restores_all_scratch_and_skips_publish() -> None:
    manager = _SceneStatusManager()
    manager.documents[3] = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow("任务", "未开始"),
    ])
    manager.get_active_scene_table_ref = lambda: None  # type: ignore[method-assign]
    manager.list_context_tables = lambda: [  # type: ignore[method-assign]
        manager._table(1),
        manager._table(3),
    ]
    original = dict(manager.documents)

    class Provider:
        async def chat(self, messages, *, tools):  # noqa: ANN001
            assert {tool["function"]["name"] for tool in tools} == {
                "status_table_edit_fields",
                "status_table_set_values",
            }
            prompt = str(messages[-1]["content"])
            table_id = 1 if '"table_id": 1' in prompt else 3
            key = "生命" if table_id == 1 else "不存在"
            return response(tool_calls=[{
                    "function": {
                        "name": "status_table_set_values",
                        "arguments": json.dumps({
                            "table_id": table_id,
                            "updates": [{"key": key, "value": "changed"}],
                        }),
                    }
                }])

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())

    async def get_provider():
        return Provider()

    sub_agent._get_provider = get_provider  # type: ignore[method-assign]
    result = await StatusBootstrapCoordinator(sub_agent).run(
        history=_history(),
        boundary_turn_id=3,
        status_manager=manager,  # type: ignore[arg-type]
        scene_tracker=None,
    )

    assert result.failed is True
    assert result.updated is False
    assert manager.committed_table_ids == []
    assert manager.documents == original
