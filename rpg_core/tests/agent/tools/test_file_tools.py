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
    current = tmp_path / "session_root"
    current.mkdir(parents=True)
    return FileToolSandbox(session_root=current)


@pytest.mark.asyncio
async def test_default_scope_lists_current_session(sandbox):
    (sandbox.session_root / "notes.md").write_text("session note", encoding="utf-8")

    result = await ListFilesTool(sandbox).execute()

    assert "notes.md" in result


@pytest.mark.asyncio
async def test_workspace_scope_is_not_available(sandbox):
    reader = ReadFileTool(sandbox)
    writer = WriteFileTool(sandbox)

    with pytest.raises(ValueError, match="only 'session' scope is supported"):
        await reader.execute("history.jsonl", scope="workspace")
    with pytest.raises(ValueError, match="only 'session' scope is supported"):
        await writer.execute("history.jsonl", "edited", scope="workspace")


@pytest.mark.asyncio
async def test_session_scope_reads_and_writes_current_session(sandbox):
    writer = WriteFileTool(sandbox)
    reader = ReadFileTool(sandbox)

    await writer.execute("history.jsonl", "edited", scope="session")

    assert (sandbox.session_root / "history.jsonl").read_text(encoding="utf-8") == "edited"
    assert await reader.execute("history.jsonl", scope="session") == "edited"


@pytest.mark.asyncio
async def test_session_scope_rejects_other_session_traversal(sandbox):
    other_history = sandbox.session_root.parent / "other" / "history.jsonl"
    other_history.parent.mkdir(parents=True)
    other_history.write_text("other secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Path escapes session scope"):
        await ReadFileTool(sandbox).execute("../other/history.jsonl", scope="session")


@pytest.mark.asyncio
async def test_grep_session_scope_searches_current_session_only(sandbox):
    (sandbox.session_root / "history.jsonl").write_text("needle in current", encoding="utf-8")
    other_history = sandbox.session_root.parent / "other" / "history.jsonl"
    other_history.parent.mkdir(parents=True)
    other_history.write_text("needle in other", encoding="utf-8")

    result = await GrepTool(sandbox).execute("needle", glob="*", scope="session")

    assert "history.jsonl" in result
    assert "other" not in result


@pytest.mark.asyncio
async def test_symlink_escape_is_rejected_or_skipped(tmp_path, sandbox):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    (sandbox.session_root / "outside_link.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="Path escapes session scope"):
        await ReadFileTool(sandbox).execute("outside_link.txt")

    result = await GrepTool(sandbox).execute("outside", glob="*.txt")
    assert "outside secret" not in result
