from __future__ import annotations

import json

import pytest

from rpg_data.models import (
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    StatusDeferredProgress,
    StatusTableDocument,
    StatusTableRow,
)
from rpg_core.agent.sub_agents import (
    DeferredStatusResult,
    StatusSubAgent,
    SubAgentContext,
)
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session import SessionManager


async def _async_value(value):  # noqa: ANN001, ANN201
    return value


class _StatusManager:
    def __init__(self) -> None:
        self.document = StatusTableDocument.from_rows(rows=[
            StatusTableRow(
                "长期信任",
                "低",
                update_frequency=STATUS_UPDATE_FREQUENCY_DEFERRED,
                deferred_interval_turns=2,
            ),
            StatusTableRow("当前位置", "森林"),
        ])
        self.progress: list[StatusDeferredProgress] = []
        self.commits: list[tuple[tuple[str, ...], int]] = []

    def list_context_tables(self):  # noqa: ANN201
        return [{
            "id": 7,
            "name": "人物关系",
            "description": "归纳长期关系",
            "document": self.document.to_json_dict(),
        }]

    def list_deferred_progress(self):  # noqa: ANN201
        return list(self.progress)

    def clamp_deferred_progress(self, max_turn_id: int) -> int:
        for index, item in enumerate(self.progress):
            if item.last_processed_turn_id > max_turn_id:
                self.progress[index] = StatusDeferredProgress(
                    item.session_status_table_id,
                    item.field_key,
                    max_turn_id,
                )
        return 0

    def get_table_document_by_id(self, table_id: int) -> StatusTableDocument:
        assert table_id == 7
        return self.document

    def commit_deferred_update(
        self,
        table_id: int,
        document: StatusTableDocument,
        *,
        processed_keys,
        last_processed_turn_id: int,
        base_document: StatusTableDocument,
    ) -> None:
        assert table_id == 7
        assert base_document == self.document
        keys = tuple(processed_keys)
        self.document = document
        self.progress = [
            StatusDeferredProgress(7, key, last_processed_turn_id)
            for key in keys
        ]
        self.commits.append((keys, last_processed_turn_id))


@pytest.mark.asyncio
async def test_deferred_reconciler_uses_committed_interval_and_advances_progress() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "帮助了她", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "她表示感谢", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "再次守约", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "她开始信任你", turn_id=2, seq_in_turn=2),
    ], persist=False)
    status = _StatusManager()

    class Provider:
        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools[0]["function"]["name"] == "set_deferred_values"
            return {
                "tool_calls": [{
                    "function": {
                        "name": "set_deferred_values",
                        "arguments": json.dumps({
                            "updates": [{"key": "长期信任", "value": "中"}],
                        }, ensure_ascii=False),
                    },
                }],
            }

    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent._get_provider = lambda: _async_value(Provider())  # type: ignore[method-assign]

    result = await sub_agent.reconcile_deferred(
        session_manager=session,
        status_manager=status,
    )

    assert result == DeferredStatusResult(batches=1, fields=1, changed=1)
    assert status.document.row_for_key("长期信任").value == "中"
    assert status.commits == [(('长期信任',), 2)]


@pytest.mark.asyncio
async def test_deferred_reconciler_skips_fields_before_interval() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "一次互动", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "尚未形成趋势", turn_id=1, seq_in_turn=2),
    ], persist=False)
    status = _StatusManager()
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")

    result = await sub_agent.reconcile_deferred(
        session_manager=session,
        status_manager=status,
    )

    assert result == DeferredStatusResult()
    assert status.commits == []


@pytest.mark.asyncio
async def test_deferred_reconciler_isolates_failed_table_batches() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "形成长期变化", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "变化已经确认", turn_id=1, seq_in_turn=2),
    ], persist=False)

    class StatusManager:
        def __init__(self) -> None:
            self.documents = {
                table_id: StatusTableDocument.from_rows(rows=[
                    StatusTableRow(
                        key,
                        "低",
                        update_frequency=STATUS_UPDATE_FREQUENCY_DEFERRED,
                        deferred_interval_turns=1,
                    )
                ])
                for table_id, key in ((7, "长期信任"), (8, "长期警戒"))
            }
            self.committed_tables: list[int] = []

        def list_context_tables(self):  # noqa: ANN201
            return [
                {
                    "id": table_id,
                    "name": f"表 {table_id}",
                    "description": "测试隔离",
                    "document": document.to_json_dict(),
                }
                for table_id, document in self.documents.items()
            ]

        def list_deferred_progress(self):  # noqa: ANN201
            return []

        @staticmethod
        def clamp_deferred_progress(_max_turn_id: int) -> int:
            return 0

        def get_table_document_by_id(self, table_id: int) -> StatusTableDocument:
            return self.documents[table_id]

        def commit_deferred_update(
            self,
            table_id: int,
            document: StatusTableDocument,
            **_kwargs,
        ) -> None:
            self.documents[table_id] = document
            self.committed_tables.append(table_id)

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, _messages, *, tools):  # noqa: ANN001
            assert tools[0]["function"]["name"] == "set_deferred_values"
            self.calls += 1
            if self.calls == 1:
                return {
                    "tool_calls": [{
                        "function": {
                            "name": "invalid_deferred_tool",
                            "arguments": "{}",
                        },
                    }],
                }
            return {"tool_calls": []}

    status = StatusManager()
    provider = Provider()
    sub_agent = StatusSubAgent(provider_biz_key="agent.status_sub_agent")
    sub_agent.bind_context(SubAgentContext())
    sub_agent._get_provider = lambda: _async_value(provider)  # type: ignore[method-assign]

    result = await sub_agent.reconcile_deferred(
        session_manager=session,
        status_manager=status,
    )

    assert result == DeferredStatusResult(batches=1, fields=1, changed=0)
    assert status.committed_tables == [8]
