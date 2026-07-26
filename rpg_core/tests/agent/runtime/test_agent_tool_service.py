from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg_core.agent.runtime.resources import AgentContextResources
from rpg_core.agent.runtime.tools import AgentToolService
from rpg_core.agent.tools.file_tools import FileToolSandbox, ReadFileTool, WriteFileTool
from rpg_core.tooling.base import BaseTool
from rpg_core.agent.turn import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnMode,
    TurnRequest,
)


class _Tool(BaseTool):
    description = "test"

    def __init__(self, name: str) -> None:
        self.name = name

    def parameters(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: object) -> str:
        del kwargs
        return self.name


class _Scene:
    def __init__(self) -> None:
        self.tool = _Tool("scene_time")

    def get_tools(self) -> list[BaseTool]:
        return [self.tool]


class _RPRuntime:
    def __init__(self) -> None:
        self.outcome = _Tool("rp_story_outcome")
        self.visible = _Tool("rp_visible")

    def get_tools(self) -> list[BaseTool]:
        return [self.outcome, self.visible]

    def get_main_agent_tools(self) -> list[BaseTool]:
        return [self.visible]

    def get_status_preflight_tools(self, _user_input: str) -> list[BaseTool]:
        return [self.outcome]


class _HistoryQuery:
    pass


class _SummaryQuery:
    pass


def _execution(mode: TurnMode) -> TurnExecutionSnapshot:
    request = TurnRequest.create("test", mode=mode)
    return TurnExecutionSnapshot(
        request=request,
        narrative_style_id=None,
        narrative_style_name="",
        narrative_style_prompt="",
        policy=TurnExecutionPolicy.for_mode(mode),
    )


def test_tool_service_removes_hidden_rp_tool_from_registry_and_schema() -> None:
    scene = _Scene()
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=scene,
        memory_manager=None,
    )
    service = AgentToolService(
        resources=lambda: resources,
        history_query=_HistoryQuery(),
        summary_query=_SummaryQuery(),
        extra_tools=[_Tool("custom_read")],
    )
    service.refresh_base_registry()
    runtime = _RPRuntime()

    registry = service.registry_for_turn(
        scene,
        None,
        rp_module_runtime=runtime,
        turn_execution=_execution(TurnMode.IC),
    )
    assert registry is not None
    assert "rp_story_outcome" not in registry
    assert "rp_visible" in registry
    assert "scene_time" in registry
    schemas = service.main_schemas(registry, rp_module_runtime=runtime)
    names = {schema["function"]["name"] for schema in schemas}
    assert "rp_story_outcome" not in names
    assert "rp_visible" in names


def test_ooc_tool_policy_hides_state_rp_and_write_tools(tmp_path) -> None:
    scene = _Scene()
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=scene,
        memory_manager=None,
    )
    service = AgentToolService(
        resources=lambda: resources,
        history_query=_HistoryQuery(),
        summary_query=_SummaryQuery(),
        extra_tools=[
            _Tool("custom_read"),
            WriteFileTool(FileToolSandbox(tmp_path)),
        ],
    )
    service.refresh_base_registry()

    registry = service.registry_for_turn(
        scene,
        None,
        rp_module_runtime=_RPRuntime(),
        turn_execution=_execution(TurnMode.OOC),
    )
    assert registry is not None
    names = {tool.name for tool in registry}
    assert "write_file" not in names
    assert "scene_time" not in names
    assert "rp_story_outcome" not in names
    assert "rp_visible" not in names
    assert "custom_read" in names
    assert {
        "history_search",
        "history_read",
        "summary_search",
        "summary_read",
    } <= names


def test_tool_service_replaces_default_file_tools_with_lookup_tools() -> None:
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=None,
    )
    service = AgentToolService(
        resources=lambda: resources,
        history_query=_HistoryQuery(),
        summary_query=_SummaryQuery(),
    )

    service.refresh_base_registry()
    registry = service.base_registry
    assert registry is not None
    names = {tool.name for tool in registry}
    assert {
        "history_search",
        "history_read",
        "summary_search",
        "summary_read",
    } <= names
    assert {"list_files", "read_file", "write_file", "grep"}.isdisjoint(names)


@pytest.mark.parametrize("mode", list(TurnMode))
def test_lookup_tools_are_exposed_in_every_turn_mode(mode: TurnMode) -> None:
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=None,
    )
    service = AgentToolService(
        resources=lambda: resources,
        history_query=_HistoryQuery(),
        summary_query=_SummaryQuery(),
    )
    service.refresh_base_registry()

    registry = service.registry_for_turn(
        None,
        None,
        turn_execution=_execution(mode),
    )
    assert registry is not None
    assert {
        "history_search",
        "history_read",
        "summary_search",
        "summary_read",
    } <= {
        tool.name for tool in registry
    }


def test_explicit_file_tools_remain_available_under_existing_mode_policy(
    tmp_path,
) -> None:
    resources = AgentContextResources(
        builder=SimpleNamespace(),
        character_manager=None,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=None,
        memory_manager=None,
    )
    sandbox = FileToolSandbox(tmp_path)
    service = AgentToolService(
        resources=lambda: resources,
        history_query=_HistoryQuery(),
        summary_query=_SummaryQuery(),
        extra_tools=[ReadFileTool(sandbox), WriteFileTool(sandbox)],
    )
    service.refresh_base_registry()

    ic_registry = service.registry_for_turn(
        None,
        None,
        turn_execution=_execution(TurnMode.IC),
    )
    assert ic_registry is not None
    assert {"read_file", "write_file"} <= {tool.name for tool in ic_registry}

    ooc_registry = service.registry_for_turn(
        None,
        None,
        turn_execution=_execution(TurnMode.OOC),
    )
    assert ooc_registry is not None
    ooc_names = {tool.name for tool in ooc_registry}
    assert "read_file" in ooc_names
    assert "write_file" not in ooc_names


def test_state_tool_set_reports_exact_runtime_capabilities() -> None:
    state_tools = AgentToolService.state_tools(_Scene(), None)

    assert state_tools.names == ("scene_time",)
    assert state_tools.supports("scene_time") is True
    assert state_tools.supports("scene_del_attr") is False
    assert AgentToolService.state_tools(None, None).names == ()
