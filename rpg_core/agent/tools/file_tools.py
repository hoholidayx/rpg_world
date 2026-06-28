"""File-system tools restricted to the current RPG session runtime directory."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rpg_core.agent.tools.base import BaseTool

_MAX_READ_SIZE = 100 * 1024  # 100 KB
_GREP_MAX_FILES = 200
_GREP_BLOCK_SIZE = 50 * 1024  # per-file limit for grep content
_SCOPE_SESSION = "session"
_VALID_SCOPES = {_SCOPE_SESSION}


@dataclass(frozen=True)
class FileToolSandbox:
    """Resolve file-tool paths against the current session runtime directory."""

    session_root: Path

    def resolve(self, scope: str, raw: str = "") -> Path:
        """Resolve *raw* under the current session root, rejecting traversal."""
        scope = _normalize_scope(scope)
        raw_path = Path(raw or "")
        if raw_path.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {raw!r}")

        root = self.root_for(scope)
        target = (root / raw_path).resolve()
        rel = _relative_to(target, root)
        if rel is None:
            raise ValueError(f"Path escapes {scope} scope: {raw!r}")
        return target

    def root_for(self, scope: str) -> Path:
        _normalize_scope(scope)
        return self.session_root.resolve()

    def display_path(self, scope: str, path: Path) -> Path:
        root = self.root_for(scope)
        rel = _relative_to(path.resolve(), root)
        if rel is None:
            raise ValueError(f"Path escapes {scope} scope: {path}")
        return rel


def _safe_resolve(session_root: Path, raw: str) -> Path:
    """Resolve *raw* relative to session_root, rejecting traversal escapes."""
    return FileToolSandbox(session_root=Path(session_root)).resolve(_SCOPE_SESSION, raw)


def _normalize_scope(scope: str) -> str:
    scope = (scope or _SCOPE_SESSION).strip()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope {scope!r}; only 'session' scope is supported")
    return scope


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root.resolve())
    except ValueError:
        return None


def _scope_parameter() -> dict[str, object]:
    return {
        "type": "string",
        "enum": [_SCOPE_SESSION],
        "description": "Data scope to access. Only the current session directory is available.",
        "default": _SCOPE_SESSION,
    }


# -- list_files ---------------------------------------------------------


class ListFilesTool(BaseTool):
    """List directory contents (non-recursive)."""

    name = "list_files"
    description = (
        "List files and subdirectories under the current session directory."
    )

    def __init__(self, sandbox: FileToolSandbox | Path) -> None:
        self._sandbox = _coerce_sandbox(sandbox)

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "scope": _scope_parameter(),
                "path": {
                    "type": "string",
                    "description": "Relative path under the selected scope (empty string for root).",
                    "default": "",
                },
            },
        }

    async def execute(self, path: str = "", scope: str = _SCOPE_SESSION) -> str:
        scope = _normalize_scope(scope)
        target = self._sandbox.resolve(scope, path)
        if not target.exists():
            return f"Error: path not found: {path!r}"
        if not target.is_dir():
            return f"Error: not a directory: {path!r}"

        entries = list(target.iterdir())
        entries = sorted(entries, key=lambda p: (not p.is_dir(), p.name))
        lines: list[str] = []
        for p in entries:
            marker = "[dir]" if p.is_dir() else "[file]"
            size = p.stat().st_size if p.is_file() else 0
            lines.append(f"  {marker} {p.name}  ({_human_size(size)})")
        return f"Contents of {scope}:{path or '/'} ({len(entries)} entries):\n" + "\n".join(lines)


# -- read_file ----------------------------------------------------------


class ReadFileTool(BaseTool):
    """Read a file's text content."""

    name = "read_file"
    description = "Read a file under the current session directory."

    def __init__(self, sandbox: FileToolSandbox | Path) -> None:
        self._sandbox = _coerce_sandbox(sandbox)

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "scope": _scope_parameter(),
                "path": {
                    "type": "string",
                    "description": "Relative path to the file under the selected scope.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, scope: str = _SCOPE_SESSION) -> str:
        target = self._sandbox.resolve(scope, path)
        if not target.exists():
            return f"Error: file not found: {path!r}"
        if not target.is_file():
            return f"Error: not a file: {path!r}"

        size = target.stat().st_size
        if size > _MAX_READ_SIZE:
            return f"Error: file too large ({_human_size(size)}). Max read size is {_human_size(_MAX_READ_SIZE)}."

        content = target.read_bytes()
        if b"\x00" in content[:4096]:
            return f"Error: binary file, cannot read as text: {path!r}"

        return content.decode("utf-8")


# -- write_file ---------------------------------------------------------


class WriteFileTool(BaseTool):
    """Create or overwrite a file. Uses atomic write (temp + rename)."""

    name = "write_file"
    description = (
        "Create or overwrite a file under the current session directory. Creates parent directories if needed."
    )

    def __init__(self, sandbox: FileToolSandbox | Path) -> None:
        self._sandbox = _coerce_sandbox(sandbox)

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "scope": _scope_parameter(),
                "path": {
                    "type": "string",
                    "description": "Relative path under the selected scope.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, scope: str = _SCOPE_SESSION) -> str:
        target = self._sandbox.resolve(scope, path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return f"Written {len(content)} bytes to {scope}:{path!r}"


# -- grep ---------------------------------------------------------------


class GrepTool(BaseTool):
    """Search file contents using a regex pattern, limited to text files."""

    name = "grep"
    description = (
        "Search file contents with a regex pattern under the current session directory. "
        "Use glob to narrow file types (e.g. '*.json', '*.md'). Results limited to first 200 files."
    )

    def __init__(self, sandbox: FileToolSandbox | Path) -> None:
        self._sandbox = _coerce_sandbox(sandbox)

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "scope": _scope_parameter(),
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
                    "description": "Relative directory path to search under (empty string for selected scope root).",
                    "default": "",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        glob: str = "*",
        path: str = "",
        scope: str = _SCOPE_SESSION,
    ) -> str:
        import re

        scope = _normalize_scope(scope)
        target_dir = self._sandbox.resolve(scope, path)
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
            resolved = p.resolve()
            if _relative_to(resolved, self._sandbox.root_for(scope)) is None:
                continue
            if b"\x00" in p.read_bytes()[:4096]:
                continue
            if p.stat().st_size > _GREP_BLOCK_SIZE:
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
                    rel = self._sandbox.display_path(scope, p)
                    lines.append(f"  {rel}:{line_no}: {line_text.rstrip()[:200]}")

        if not lines:
            return f"No matches for pattern {pattern!r} in {scope}:{path or '/'}"

        header = f"Found {match_count} matches in {file_count} files for pattern {pattern!r}"
        return header + "\n" + "\n".join(lines)


# -- helper -------------------------------------------------------------


def _coerce_sandbox(value: FileToolSandbox | Path) -> FileToolSandbox:
    if isinstance(value, FileToolSandbox):
        return value
    root = Path(value)
    return FileToolSandbox(session_root=root)


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / 1024 / 1024:.1f}MB"
