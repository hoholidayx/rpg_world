from __future__ import annotations

import pytest

from rpg_core.agent.tools.file_tools import (
    FileToolSandbox,
    GrepTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
)


@pytest.fixture
def sandbox(tmp_path):
    workspace = tmp_path / "workspace"
    current = workspace / "sessions" / "current"
    other = workspace / "sessions" / "other"
    workspace.mkdir()
    current.mkdir(parents=True)
    other.mkdir(parents=True)
    return FileToolSandbox(workspace_root=workspace, session_root=current)


@pytest.mark.asyncio
async def test_workspace_scope_hides_sessions_from_listing(sandbox):
    (sandbox.workspace_root / "character").mkdir()
    (sandbox.workspace_root / "notes.md").write_text("workspace note", encoding="utf-8")

    result = await ListFilesTool(sandbox).execute()

    assert "character" in result
    assert "notes.md" in result
    assert "sessions" not in result


@pytest.mark.asyncio
async def test_workspace_scope_rejects_direct_session_access(sandbox):
    (sandbox.workspace_root / "sessions" / "current" / "history.jsonl").write_text("secret", encoding="utf-8")
    reader = ReadFileTool(sandbox)
    writer = WriteFileTool(sandbox)

    with pytest.raises(ValueError, match="Workspace scope cannot access sessions"):
        await reader.execute("sessions/current/history.jsonl")
    with pytest.raises(ValueError, match="Workspace scope cannot access sessions"):
        await writer.execute("sessions/current/history.jsonl", "edited")


@pytest.mark.asyncio
async def test_session_scope_reads_and_writes_current_session(sandbox):
    writer = WriteFileTool(sandbox)
    reader = ReadFileTool(sandbox)

    await writer.execute("history.jsonl", "edited", scope="session")

    assert (sandbox.session_root / "history.jsonl").read_text(encoding="utf-8") == "edited"
    assert await reader.execute("history.jsonl", scope="session") == "edited"


@pytest.mark.asyncio
async def test_session_scope_rejects_other_session_traversal(sandbox):
    other_history = sandbox.workspace_root / "sessions" / "other" / "history.jsonl"
    other_history.write_text("other secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Path escapes session scope"):
        await ReadFileTool(sandbox).execute("../other/history.jsonl", scope="session")


@pytest.mark.asyncio
async def test_grep_workspace_scope_does_not_search_any_sessions(sandbox):
    (sandbox.workspace_root / "lorebook").mkdir()
    (sandbox.workspace_root / "lorebook" / "world.md").write_text("needle in world", encoding="utf-8")
    (sandbox.workspace_root / "sessions" / "current" / "history.jsonl").write_text("needle in current", encoding="utf-8")
    (sandbox.workspace_root / "sessions" / "other" / "history.jsonl").write_text("needle in other", encoding="utf-8")

    result = await GrepTool(sandbox).execute("needle", glob="*")

    assert "lorebook/world.md" in result
    assert "current" not in result
    assert "other" not in result
    assert "history.jsonl" not in result


@pytest.mark.asyncio
async def test_grep_session_scope_searches_current_session_only(sandbox):
    (sandbox.session_root / "history.jsonl").write_text("needle in current", encoding="utf-8")
    (sandbox.workspace_root / "sessions" / "other" / "history.jsonl").write_text("needle in other", encoding="utf-8")

    result = await GrepTool(sandbox).execute("needle", glob="*", scope="session")

    assert "history.jsonl" in result
    assert "other" not in result


@pytest.mark.asyncio
async def test_symlink_escape_is_rejected_or_skipped(tmp_path, sandbox):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    (sandbox.workspace_root / "outside_link.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="Path escapes workspace scope"):
        await ReadFileTool(sandbox).execute("outside_link.txt")

    result = await GrepTool(sandbox).execute("outside", glob="*.txt")
    assert "outside secret" not in result
