"""Main-Agent tool adapters, query services, and compatibility exports."""

from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry
from rpg_core.agent.tools.file_tools import (
    FileToolSandbox,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    GrepTool,
)
from rpg_core.agent.tools.history import (
    HISTORY_READ_TOOL_NAME,
    HISTORY_SEARCH_TOOL_NAME,
    SENSITIVE_HISTORY_TOOL_NAMES,
    HistoryReadTool,
    HistorySearchTool,
)
from rpg_core.agent.tools.history_query import (
    HistoryQueryDataPort,
    HistoryQueryService,
)

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "FileToolSandbox",
    "ListFilesTool",
    "ReadFileTool",
    "WriteFileTool",
    "GrepTool",
    "HISTORY_READ_TOOL_NAME",
    "HISTORY_SEARCH_TOOL_NAME",
    "SENSITIVE_HISTORY_TOOL_NAMES",
    "HistoryReadTool",
    "HistorySearchTool",
    "HistoryQueryDataPort",
    "HistoryQueryService",
]
