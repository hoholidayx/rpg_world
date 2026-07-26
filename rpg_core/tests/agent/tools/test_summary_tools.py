from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from rpg_core.agent.tools.history import HistoryToolSet
from rpg_core.agent.tools.lookup import (
    SENSITIVE_LOOKUP_TOOL_NAMES,
    LookupToolSet,
)
from rpg_core.agent.tools.summary import (
    SUMMARY_READ_TOOL_NAME,
    SUMMARY_SEARCH_TOOL_NAME,
    SENSITIVE_SUMMARY_TOOL_NAMES,
    SummaryReadTool,
    SummarySearchTool,
    SummaryToolSet,
)
from rpg_core.agent.tools.summary_query import (
    SUMMARY_READ_CONTENT_BUDGET,
    SummaryQueryService,
)
from rpg_core.summary.reference import ResolvedSummaryDocument
from rpg_core.tooling.registry import ToolRegistry
from rpg_data.model.session_reference import SessionReferenceLocator


def _document(
    summary_id: str,
    *,
    kind: str = "batch",
    title: str = "",
    text: str = "",
    time: str = "",
    location: str = "",
    characters: tuple[str, ...] = (),
    batch_id: int | None = None,
) -> ResolvedSummaryDocument:
    resolved_batch_id = (
        int(summary_id)
        if kind == "batch" and batch_id is None
        else batch_id
    )
    return ResolvedSummaryDocument(
        summary_id=summary_id,
        kind=kind,
        title=title,
        excerpt=text[:240],
        text=text,
        turn_start=1,
        turn_end=8,
        time=time,
        location=location,
        characters=characters,
        updated_at="2026-07-26T10:00:00+00:00",
        summary_type="overall" if kind == "overall" else "",
        batch_id=resolved_batch_id,
        last_batch_id=4 if kind == "overall" else None,
        source_turn_start=2 if kind == "batch" else None,
        source_turn_end=7 if kind == "batch" else None,
        source_message_ids=(21, 22) if kind == "batch" else (),
        turn_range_source="sql",
    )


class _SessionData:
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing
        self.thread_ids: list[int] = []

    def get_session(self, session_id: str):  # noqa: ANN201
        self.thread_ids.append(threading.get_ident())
        if self.missing:
            return None
        return SimpleNamespace(
            id=session_id,
            workspace_id="workspace_a",
            story_id=7,
        )


class _Summaries:
    def __init__(
        self,
        documents: tuple[ResolvedSummaryDocument, ...] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self.documents = documents
        self.error = error
        self.list_locators: list[SessionReferenceLocator] = []
        self.get_calls: list[tuple[SessionReferenceLocator, str]] = []
        self.thread_ids: list[int] = []

    def list_summaries(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[ResolvedSummaryDocument, ...]:
        self.thread_ids.append(threading.get_ident())
        self.list_locators.append(locator)
        if self.error is not None:
            raise self.error
        return self.documents

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> ResolvedSummaryDocument | None:
        self.thread_ids.append(threading.get_ident())
        self.get_calls.append((locator, summary_id))
        if self.error is not None:
            raise self.error
        return next(
            (
                document
                for document in self.documents
                if document.summary_id == summary_id
            ),
            None,
        )


def _service(
    documents: tuple[ResolvedSummaryDocument, ...] = (),
    *,
    session_data: _SessionData | None = None,
    summaries: _Summaries | None = None,
    closed_threads: list[int] | None = None,
) -> tuple[SummaryQueryService, _SessionData, _Summaries]:
    data = session_data or _SessionData()
    provider = summaries or _Summaries(documents)
    closed = closed_threads if closed_threads is not None else []
    return (
        SummaryQueryService(
            session_id=lambda: "session_a",
            session_data=data,
            summaries=provider,
            close_worker_connection=lambda: closed.append(
                threading.get_ident()
            ),
        ),
        data,
        provider,
    )


@pytest.mark.asyncio
async def test_summary_search_ranks_matches_and_returns_parsed_source_metadata() -> None:
    long_body = "前" * 200 + "艾琳在钟楼找到了钥匙" + "后" * 200
    documents = (
        _document(
            "overall",
            kind="overall",
            title="故事归纳",
            text="艾琳仍在调查。",
        ),
        _document("1", title="艾琳", text="旧批次"),
        _document("2", title="艾琳", text="新批次"),
        _document("3", title="第三幕", text=long_body),
        _document("4", title="艾琳与钟楼", text="钥匙已被提及"),
    )
    closed_threads: list[int] = []
    service, data, summaries = _service(
        documents,
        closed_threads=closed_threads,
    )
    main_thread = threading.get_ident()

    result = await service.search(
        terms=[" 艾琳 ", "钟楼", "钥匙", "艾琳"],
        limit=4,
    )

    assert result["ok"] is True
    assert result["terms"] == ["艾琳", "钟楼", "钥匙"]
    assert result["hasMore"] is True
    assert [
        item["summaryId"] for item in result["items"]
    ] == ["4", "3", "2", "1"]
    first = result["items"][0]
    assert first["matchedTerms"] == ["艾琳", "钟楼", "钥匙"]
    assert first["matchedFields"] == ["title", "text"]
    assert set(first["frontMatter"]) == {
        "batch_id",
        "title",
        "source_turn_start",
        "source_turn_end",
        "source_message_ids",
        "time",
        "location",
        "characters",
    }
    assert first["resolvedTurnRange"] == {
        "start": 1,
        "end": 8,
        "source": "sql",
    }
    body_match = result["items"][1]
    assert len(body_match["excerpt"]) == 280
    assert "艾琳在钟楼找到了钥匙" in body_match["excerpt"]
    assert summaries.list_locators == [
        SessionReferenceLocator("session_a", "workspace_a", 7)
    ]
    assert data.thread_ids[0] != main_thread
    assert summaries.thread_ids == data.thread_ids
    assert closed_threads == data.thread_ids


@pytest.mark.asyncio
async def test_summary_search_empty_and_argument_errors_are_structured() -> None:
    service, _data, summaries = _service()

    empty = await service.search(terms=["不存在"])
    missing = await service.search(terms=None)
    too_many = await service.search(
        terms=[str(index) for index in range(9)]
    )
    too_long = await service.search(terms=["x" * 65])
    bad_limit = await service.search(terms=["x"], limit=True)

    assert empty == {
        "ok": True,
        "terms": ["不存在"],
        "items": [],
        "hasMore": False,
    }
    for result in (missing, too_many, too_long, bad_limit):
        assert result["ok"] is False
        assert result["errorCode"] == "invalid_arguments"
    assert len(summaries.list_locators) == 1


@pytest.mark.asyncio
async def test_summary_read_normalizes_id_and_truncates_body() -> None:
    content = "左" * 12_000 + "右" * 12_000
    document = _document("3", title="第三幕", text=content)
    service, _data, summaries = _service((document,))

    result = await service.read(summary_id="003")

    assert result["ok"] is True
    assert result["summaryId"] == "3"
    assert len(result["content"]) == SUMMARY_READ_CONTENT_BUDGET
    assert "…" in result["content"]
    assert result["contentTruncated"] is True
    assert result["frontMatter"]["source_message_ids"] == [21, 22]
    assert summaries.get_calls[0][1] == "3"


@pytest.mark.asyncio
async def test_summary_read_missing_validation_and_internal_error() -> None:
    missing, _data, _summaries = _service()
    invalid_int = await missing.read(summary_id=3)
    invalid_text = await missing.read(summary_id="-1")
    not_found = await missing.read(summary_id="9")

    closed_threads: list[int] = []
    failing_provider = _Summaries(error=RuntimeError("sensitive file detail"))
    failed, data, _provider = _service(
        session_data=_SessionData(),
        summaries=failing_provider,
        closed_threads=closed_threads,
    )
    failure = await failed.read(summary_id="overall")

    for result in (invalid_int, invalid_text):
        assert result["errorCode"] == "invalid_arguments"
    assert not_found["errorCode"] == "summary_not_found"
    assert failure == {
        "ok": False,
        "errorCode": "internal_error",
        "message": "摘要读取失败，请稍后重试",
    }
    assert closed_threads == data.thread_ids


@pytest.mark.asyncio
async def test_summary_tools_publish_closed_schemas_and_lookup_union() -> None:
    service, _data, _summaries = _service()
    search = SummarySearchTool(service)
    read = SummaryReadTool(service)

    assert search.name == SUMMARY_SEARCH_TOOL_NAME
    assert read.name == SUMMARY_READ_TOOL_NAME
    assert SENSITIVE_SUMMARY_TOOL_NAMES == frozenset({
        "summary_search",
        "summary_read",
    })
    assert search.parameters()["additionalProperties"] is False
    assert read.parameters()["additionalProperties"] is False
    assert "resolvedTurnRange" in search.description
    assert "history_search/history_read" in read.description

    history_service = SimpleNamespace()
    lookup = LookupToolSet(
        HistoryToolSet(history_service),  # type: ignore[arg-type]
        SummaryToolSet(service),
    )
    assert lookup.names == SENSITIVE_LOOKUP_TOOL_NAMES == frozenset({
        "history_search",
        "history_read",
        "summary_search",
        "summary_read",
    })
    assert {
        schema["function"]["name"]
        for schema in lookup.schemas()
    } == lookup.names

    invalid_search = json.loads(
        await search.execute(terms=["x"], unknown=True)
    )
    invalid_read = json.loads(
        await read.execute(summary_id="overall", unknown=True)
    )
    assert invalid_search["errorCode"] == "invalid_arguments"
    assert invalid_read["errorCode"] == "invalid_arguments"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_factory", "malformed_arguments"),
    [
        (SummarySearchTool, '{"terms":["不能回显"]'),
        (SummaryReadTool, '{"summary_id":'),
    ],
)
async def test_summary_registry_malformed_json_uses_structured_error(
    tool_factory,
    malformed_arguments: str,
) -> None:
    service, _data, _summaries = _service()
    registry = ToolRegistry()
    registry.register(tool_factory(service))

    result = json.loads(
        await registry.execute(tool_factory.name, malformed_arguments)
    )

    assert result == {
        "ok": False,
        "errorCode": "invalid_arguments",
        "message": "arguments 必须是有效的 JSON 对象",
    }
    assert "不能回显" not in result["message"]
