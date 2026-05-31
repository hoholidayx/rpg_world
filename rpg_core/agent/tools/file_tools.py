"""File-system tools — list, read, write, grep — restricted to workspace root."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.agent.tools.base import BaseTool

_MAX_READ_SIZE = 100 * 1024  # 100 KB
_GREP_MAX_FILES = 200
_GREB_BLOCK_SIZE = 50 * 1024  # per-file limit for grep content


def _safe_resolve(workspace_root: Path, raw: str) -> Path:
    """Resolve *raw* relative to workspace_root, rejecting traversal escapes."""
    target = (workspace_root / raw).resolve()
    if not str(target).startswith(str(workspace_root.resolve())):
        raise ValueError(f"Path escapes workspace: {raw!r}")
    return target


# ── list_files ─────────────────────────────────────────────────────────


class ListFilesTool(BaseTool):
    """List directory contents (non-recursive)."""

    name = "list_files"
    description = "List files and subdirectories in a directory under the active workspace."

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path under the workspace (empty string for root).",
                    "default": "",
                },
            },
        }

    async def execute(self, path: str = "") -> str:
        target = _safe_resolve(self._root, path)
        if not target.exists():
            return f"Error: path not found: {path!r}"
        if not target.is_dir():
            return f"Error: not a directory: {path!r}"

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        lines: list[str] = []
        for p in entries:
            marker = "📁" if p.is_dir() else "📄"
            size = p.stat().st_size if p.is_file() else 0
            lines.append(f"  {marker} {p.name}  ({_human_size(size)})")
        return f"Contents of {path or '/'} ({len(entries)} entries):\n" + "\n".join(lines)


# ── read_file ──────────────────────────────────────────────────────────


class ReadFileTool(BaseTool):
    """Read a file's text content."""

    name = "read_file"
    description = "Read the content of a file under the active workspace."

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file under the workspace.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str) -> str:
        target = _safe_resolve(self._root, path)
        if not target.exists():
            return f"Error: file not found: {path!r}"
        if not target.is_file():
            return f"Error: not a file: {path!r}"

        size = target.stat().st_size
        if size > _MAX_READ_SIZE:
            return f"Error: file too large ({_human_size(size)}). Max read size is {_human_size(_MAX_READ_SIZE)}."

        content = target.read_bytes()
        # Reject binary content
        if b"\x00" in content[:4096]:
            return f"Error: binary file, cannot read as text: {path!r}"

        text = content.decode("utf-8")
        return text


# ── write_file ─────────────────────────────────────────────────────────


class WriteFileTool(BaseTool):
    """Create or overwrite a file. Uses atomic write (temp + rename)."""

    name = "write_file"
    description = "Create a new file or overwrite an existing file under the active workspace.  Creates parent directories if needed."

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path under the workspace.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> str:
        target = _safe_resolve(self._root, path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: temp file → rename
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return f"Written {len(content)} bytes to {path!r}"


# ── grep ───────────────────────────────────────────────────────────────


class GrepTool(BaseTool):
    """Search file contents using a regex pattern, limited to text files."""

    name = "grep"
    description = "Search file contents with a regex pattern under a workspace directory.  Use glob to narrow file types (e.g. '*.json', '*.md').  Results limited to first 200 files."

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.json', '*.md', '*').",
                    "default": "*",
                },
                "path": {
                    "type": "string",
                    "description": "Relative directory path to search under (empty string for workspace root).",
                    "default": "",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, glob: str = "*", path: str = "") -> str:
        import re

        target_dir = _safe_resolve(self._root, path)
        if not target_dir.exists() or not target_dir.is_dir():
            return f"Error: directory not found: {path!r}"

        file_count = 0
        match_count = 0
        lines: list[str] = []

        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return f"Error: invalid regex pattern: {exc}"

        for p in sorted(target_dir.rglob(glob)):
            if not p.is_file():
                continue
            if b"\x00" in p.read_bytes()[:4096]:
                continue
            if p.stat().st_size > _GREB_BLOCK_SIZE:
                continue

            file_count += 1
            if file_count > _GREP_MAX_FILES:
                lines.append(f"  ... (reached limit of {_GREP_MAX_FILES} files)")
                break

            try:
                text = p.read_text("utf-8")
            except Exception:
                continue

            for line_no, line_text in enumerate(text.splitlines(), 1):
                if compiled.search(line_text):
                    match_count += 1
                    rel = p.relative_to(self._root)
                    lines.append(f"  {rel}:{line_no}: {line_text.rstrip()[:200]}")

        if not lines:
            return f"No matches for pattern {pattern!r} in {path or '/'}"

        header = f"Found {match_count} matches in {file_count} files for pattern {pattern!r}"
        return header + "\n" + "\n".join(lines)


# ── helper ─────────────────────────────────────────────────────────────


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / 1024 / 1024:.1f}MB"
