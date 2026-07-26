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
    HistoryToolSet,
)
from rpg_core.agent.tools.history_query import (
    HistoryQueryDataPort,
    HistoryQueryService,
)
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
    SummaryQueryService,
    SummaryQuerySessionDataPort,
    SummaryReferenceProviderPort,
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
    "HistoryToolSet",
    "HistoryQueryDataPort",
    "HistoryQueryService",
    "LookupToolSet",
    "SENSITIVE_LOOKUP_TOOL_NAMES",
    "SUMMARY_READ_TOOL_NAME",
    "SUMMARY_SEARCH_TOOL_NAME",
    "SENSITIVE_SUMMARY_TOOL_NAMES",
    "SummaryReadTool",
    "SummarySearchTool",
    "SummaryToolSet",
    "SummaryQueryService",
    "SummaryQuerySessionDataPort",
    "SummaryReferenceProviderPort",
]
