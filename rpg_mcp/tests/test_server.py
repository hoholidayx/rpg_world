from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rpg_mcp.cli import build_parser
from rpg_mcp.server import build_server


def test_design_mode_registers_only_design_tools_and_imports_no_runtime() -> None:
    script = """
import asyncio
import json
import sys
from rpg_mcp.server import build_server
bundle = build_server(mode="design", project_root="DesignProject")
names = [tool.name for tool in asyncio.run(bundle.server.list_tools())]
forbidden = sorted(
    name for name in sys.modules
    if name == "rpg_core" or name.startswith("rpg_core.")
    or name == "rpg_data" or name.startswith("rpg_data.")
    or name == "rpg_memory" or name.startswith("rpg_memory.")
)
print(json.dumps({"names": names, "forbidden": forbidden}))
bundle.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=".",
        check=True,
        capture_output=True,
        text=True,
    )
    result = __import__("json").loads(completed.stdout)
    assert len(result["names"]) == 14
    assert all(name.startswith("story_design_") for name in result["names"])
    assert result["forbidden"] == []


def test_all_mode_registers_complete_contract(tmp_path) -> None:
    bundle = build_server(
        mode="all",
        project_root="DesignProject",
        db_path=tmp_path / "runtime.sqlite3",
    )
    try:
        tools = asyncio.run(bundle.server.list_tools())
        names = {item.name for item in tools}
        assert len(names) == 29
        assert {
            "story_design_get_resume_context",
            "story_design_get_authoring_rules",
            "story_design_preview_authoring_rules_refresh",
            "story_design_apply_authoring_rules_refresh",
            "story_design_preview_runtime_sync",
            "story_design_apply_runtime_sync",
            "rpg_preview_story_pack",
            "rpg_apply_story_pack",
        }.issubset(names)
        apply = next(
            item for item in tools if item.name == "rpg_apply_story_pack"
        )
        assert apply.annotations is not None
        assert apply.annotations.destructiveHint is True
        assert apply.annotations.readOnlyHint is False
        contract = json.loads(
            __import__("pathlib").Path(
                "DesignProject/schemas/rpg-mcp-contract-v2.json"
            ).read_text(encoding="utf-8")
        )
        contract_names = {
            tool["name"]
            for mode in contract["modes"].values()
            for tool in mode.get("tools", [])
        }
        assert contract_names == names
        contract_tools = {
            item["name"]: item
            for mode in contract["modes"].values()
            for item in mode.get("tools", [])
        }
        for tool in tools:
            annotations = tool.annotations
            assert annotations is not None
            expected = contract_tools[tool.name]["annotations"]
            assert annotations.readOnlyHint is expected["readOnlyHint"]
            assert annotations.destructiveHint is expected["destructiveHint"]
            assert annotations.openWorldHint is expected["openWorldHint"]
        for name in (
            "rpg_apply_story_pack",
            "rpg_apply_changes",
            "story_design_apply_authoring_rules_refresh",
            "story_design_apply_runtime_sync",
        ):
            tool = next(item for item in tools if item.name == name)
            assert tool.inputSchema["properties"] == {
                "operation_id": {
                    "title": "Operation Id",
                    "type": "string",
                }
            }
            assert tool.inputSchema["required"] == ["operation_id"]
    finally:
        bundle.close()


def test_http_host_is_loopback_only() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--mode",
            "runtime",
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
        ])
    parsed = parser.parse_args([
        "--mode",
        "runtime",
        "--transport",
        "streamable-http",
        "--host",
        "127.0.0.1",
    ])
    assert parsed.host == "127.0.0.1"


async def test_stdio_protocol_lists_design_tools() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "rpg_mcp.cli",
            "--mode",
            "design",
            "--project-root",
            "DesignProject",
        ],
        cwd=".",
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
    assert len(result.tools) == 14
    assert {
        "story_design_get_resume_context",
        "story_design_get_authoring_rules",
        "story_design_patch",
        "story_design_build_pack",
    }.issubset({item.name for item in result.tools})
