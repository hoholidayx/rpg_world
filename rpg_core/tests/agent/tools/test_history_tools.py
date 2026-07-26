from __future__ import annotations

import json
import threading
from dataclasses import dataclass

import pytest

from rpg_core.agent.tools.history_query import (
    HISTORY_READ_CONTENT_BUDGET,
    HistoryQueryService,
)
from rpg_core.agent.tools.history import (
    HISTORY_READ_TOOL_NAME,
    HISTORY_SEARCH_TOOL_NAME,
    SENSITIVE_HISTORY_TOOL_NAMES,
    HistoryReadTool,
    HistorySearchTool,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry


@dataclass(frozen=True)
class _Hit:
    turn_id: int
    message_id: int
    seq_in_turn: int
    role: str
    mode: str
    content: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class _Message:
    id: int
    turn_id: int
    seq_in_turn: int
    role: str
    mode: str
    content: str


@dataclass(frozen=True)
class _Window:
    anchor_turn_id: int
    turn_ids: tuple[int, ...]
    messages: tuple[_Message, ...]
    has_before: bool
    has_after: bool


class _Data:
    def __init__(
        self,
        *,
        hits: list[_Hit] | None = None,
        window: _Window | None = None,
        error: Exception | None = None,
    ) -> None:
        self.hits = list(hits or [])
        self.window = window
        self.error = error
        self.search_calls: list[tuple[str, tuple[str, ...], int]] = []
        self.read_calls: list[tuple[str, int, int, int]] = []
        self.worker_threads: list[int] = []

    def search_history_turns(
        self,
        session_id: str,
        terms: tuple[str, ...],
        *,
        limit: int,
    ) -> list[_Hit]:
        self.worker_threads.append(threading.get_ident())
        self.search_calls.append((session_id, terms, limit))
        if self.error is not None:
            raise self.error
        return self.hits[:limit]

    def read_history_turn_window(
        self,
        session_id: str,
        *,
        anchor_turn_id: int,
        before_turns: int,
        after_turns: int,
    ) -> _Window | None:
        self.worker_threads.append(threading.get_ident())
        self.read_calls.append(
            (session_id, anchor_turn_id, before_turns, after_turns)
        )
        if self.error is not None:
            raise self.error
        return self.window


class _PlainTool(BaseTool):
    name = "plain_tool"
    description = "Plain compatibility test tool."

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: object) -> str:
        return json.dumps(kwargs)


def _service(
    data: _Data,
    *,
    closed_threads: list[int] | None = None,
) -> HistoryQueryService:
    closed = closed_threads if closed_threads is not None else []
    return HistoryQueryService(
        session_id=lambda: "session_a",
        data=data,
        close_worker_connection=lambda: closed.append(threading.get_ident()),
    )


@pytest.mark.asyncio
async def test_history_search_normalizes_terms_limits_results_and_builds_excerpt() -> None:
    long_content = "前" * 200 + "钟楼" + "后" * 200
    hits = [
        _Hit(
            turn_id=turn_id,
            message_id=turn_id * 10,
            seq_in_turn=2,
            role="assistant",
            mode="ic",
            content=long_content if turn_id == 9 else f"艾琳 turn {turn_id}",
            matched_terms=("艾琳", "钟楼") if turn_id == 9 else ("艾琳",),
        )
        for turn_id in range(9, 3, -1)
    ]
    closed_threads: list[int] = []
    data = _Data(hits=hits)
    main_thread = threading.get_ident()

    result = await _service(data, closed_threads=closed_threads).search(
        terms=[" 艾琳 ", "", "ABC", "abc", "钟楼"],
        limit=5,
    )

    assert result["ok"] is True
    assert result["terms"] == ["艾琳", "ABC", "钟楼"]
    assert result["hasMore"] is True
    assert len(result["items"]) == 5
    assert data.search_calls == [
        ("session_a", ("艾琳", "ABC", "钟楼"), 6)
    ]
    assert data.worker_threads[0] != main_thread
    assert closed_threads == data.worker_threads

    first = result["items"][0]
    assert first["turnId"] == 9
    assert first["matchedTerms"] == ["艾琳", "钟楼"]
    assert len(first["excerpt"]) == 280
    assert "钟楼" in first["excerpt"]
    assert first["excerpt"].startswith("…")
    assert first["excerpt"].endswith("…")
    assert first["excerptTruncated"] is True


@pytest.mark.asyncio
async def test_history_search_empty_result_and_argument_errors_are_structured() -> None:
    data = _Data()
    service = _service(data)

    empty = await service.search(terms=["没有命中"])
    missing = await service.search(terms=None)
    too_many = await service.search(
        terms=[str(index) for index in range(9)]
    )
    too_long = await service.search(terms=["x" * 65])
    bad_limit = await service.search(terms=["x"], limit=True)

    assert empty == {
        "ok": True,
        "terms": ["没有命中"],
        "items": [],
        "hasMore": False,
    }
    for result in (missing, too_many, too_long, bad_limit):
        assert result["ok"] is False
        assert result["errorCode"] == "invalid_arguments"
    assert len(data.search_calls) == 1


@pytest.mark.asyncio
async def test_history_read_uses_actual_window_and_prioritizes_anchor_content() -> None:
    anchor_content = "A" * 19_000
    nearby_content = "B" * 2_000
    later_content = "C" * 2_000
    window = _Window(
        anchor_turn_id=20,
        turn_ids=(4, 20, 35),
        messages=(
            _Message(1, 4, 1, "user", "neutral", nearby_content),
            _Message(2, 20, 1, "user", "ic", anchor_content),
            _Message(3, 35, 1, "assistant", "gm", later_content),
        ),
        has_before=True,
        has_after=False,
    )
    data = _Data(window=window)

    result = await _service(data).read(
        turn_id=20,
        before_turns=1,
        after_turns=1,
    )

    assert result["ok"] is True
    assert result["anchorTurnId"] == 20
    assert result["turnIds"] == [4, 20, 35]
    assert [message["turnId"] for message in result["messages"]] == [4, 20, 35]
    assert sum(len(message["content"]) for message in result["messages"]) == (
        HISTORY_READ_CONTENT_BUDGET
    )
    assert result["messages"][1]["content"] == anchor_content
    assert len(result["messages"][0]["content"]) == 1_000
    assert result["messages"][0]["content"].startswith("B")
    assert result["messages"][0]["content"].endswith("B")
    assert "…" in result["messages"][0]["content"]
    assert result["messages"][0]["contentTruncated"] is True
    assert result["messages"][2]["content"] == ""
    assert result["messages"][2]["contentTruncated"] is True
    assert result["hasBefore"] is True
    assert result["hasAfter"] is False
    assert result["truncated"] is True
    assert data.read_calls == [("session_a", 20, 1, 1)]


@pytest.mark.asyncio
async def test_history_read_shares_anchor_budget_between_its_messages() -> None:
    window = _Window(
        anchor_turn_id=8,
        turn_ids=(8,),
        messages=(
            _Message(1, 8, 1, "user", "neutral", "左" * 15_000),
            _Message(2, 8, 2, "assistant", "neutral", "右" * 15_000),
        ),
        has_before=False,
        has_after=False,
    )

    result = await _service(_Data(window=window)).read(
        turn_id=8,
        before_turns=0,
        after_turns=0,
    )

    contents = [message["content"] for message in result["messages"]]
    assert [len(content) for content in contents] == [10_000, 10_000]
    assert all("…" in content for content in contents)
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_history_read_missing_turn_validation_and_internal_error() -> None:
    missing = await _service(_Data()).read(turn_id=99)
    invalid = await _service(_Data()).read(turn_id=0, before_turns=3)

    closed_threads: list[int] = []
    failing_data = _Data(error=RuntimeError("sensitive database detail"))
    failed = await _service(
        failing_data,
        closed_threads=closed_threads,
    ).read(turn_id=1)

    assert missing["errorCode"] == "turn_not_found"
    assert invalid["errorCode"] == "invalid_arguments"
    assert failed == {
        "ok": False,
        "errorCode": "internal_error",
        "message": "历史读取失败，请稍后重试",
    }
    assert closed_threads == failing_data.worker_threads


@pytest.mark.asyncio
async def test_history_tools_publish_closed_schemas_and_json_contracts() -> None:
    service = _service(_Data())
    search = HistorySearchTool(service)
    read = HistoryReadTool(service)

    assert search.name == HISTORY_SEARCH_TOOL_NAME
    assert read.name == HISTORY_READ_TOOL_NAME
    assert SENSITIVE_HISTORY_TOOL_NAMES == frozenset({
        "history_search",
        "history_read",
    })
    assert search.parameters()["additionalProperties"] is False
    assert read.parameters()["additionalProperties"] is False
    assert "history_read" in search.description
    assert "history_search" in read.description

    invalid_search = json.loads(
        await search.execute(terms=["x"], unknown=True)
    )
    invalid_read = json.loads(
        await read.execute(turn_id=1, unknown=True)
    )
    assert invalid_search["errorCode"] == "invalid_arguments"
    assert invalid_read["errorCode"] == "invalid_arguments"

    unicode_result = json.loads(await search.execute(terms=["艾琳"]))
    assert unicode_result["terms"] == ["艾琳"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_factory", "malformed_arguments"),
    [
        (HistorySearchTool, '{"terms":["不能回显"]'),
        (HistoryReadTool, '{"turn_id":'),
    ],
)
async def test_history_registry_malformed_json_uses_structured_error(
    tool_factory,
    malformed_arguments: str,
) -> None:
    registry = ToolRegistry()
    registry.register(tool_factory(_service(_Data())))

    result = json.loads(
        await registry.execute(tool_factory.name, malformed_arguments)
    )

    assert result == {
        "ok": False,
        "errorCode": "invalid_arguments",
        "message": "arguments 必须是有效的 JSON 对象",
    }
    assert "不能回显" not in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_factory", [HistorySearchTool, HistoryReadTool])
async def test_history_registry_non_object_json_uses_structured_error(
    tool_factory,
) -> None:
    registry = ToolRegistry()
    registry.register(tool_factory(_service(_Data())))

    result = json.loads(await registry.execute(tool_factory.name, "[]"))

    assert result == {
        "ok": False,
        "errorCode": "invalid_arguments",
        "message": "arguments 必须解码为 JSON 对象",
    }


@pytest.mark.asyncio
async def test_registry_preserves_plain_tool_argument_error_behavior() -> None:
    registry = ToolRegistry()
    registry.register(_PlainTool())

    malformed = await registry.execute("plain_tool", "{")
    non_object = await registry.execute("plain_tool", "[]")

    assert malformed.startswith(
        "Error: invalid arguments JSON for 'plain_tool':"
    )
    assert non_object.startswith("Error executing 'plain_tool':")
