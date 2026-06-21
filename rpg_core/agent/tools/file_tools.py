"""File-system tools: list, read, write, grep, restricted by RPG data scope."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rpg_world.rpg_core.agent.tools.base import BaseTool

_MAX_READ_SIZE = 100 * 1024  # 100 KB
_GREP_MAX_FILES = 200
_GREP_BLOCK_SIZE = 50 * 1024  # per-file limit for grep content
_SCOPE_WORKSPACE = "workspace"
_SCOPE_SESSION = "session"
_VALID_SCOPES = {_SCOPE_WORKSPACE, _SCOPE_SESSION}
_SESSION_DIR_NAME = "sessions"


@dataclass(frozen=True)
class FileToolSandbox:
    """Resolve file-tool paths against explicit RPG data scopes."""

    workspace_root: Path
    session_root: Path

    def resolve(self, scope: str, raw: str = "") -> Path:
        """Resolve *raw* under *scope*, rejecting traversal and cross-session access."""
        scope = _normalize_scope(scope)
        raw_path = Path(raw or "")
        if raw_path.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {raw!r}")

        root = self.root_for(scope)
        target = (root / raw_path).resolve()
        rel = _relative_to(target, root)
        if rel is None:
            raise ValueError(f"Path escapes {scope} scope: {raw!r}")
        if scope == _SCOPE_WORKSPACE and rel.parts[:1] == (_SESSION_DIR_NAME,):
            raise ValueError("Workspace scope cannot access sessions; use session scope for the current session")
        return target

    def root_for(self, scope: str) -> Path:
        scope = _normalize_scope(scope)
        root = self.session_root if scope == _SCOPE_SESSION else self.workspace_root
        return root.resolve()

    def display_path(self, scope: str, path: Path) -> Path:
        root = self.root_for(scope)
        rel = _relative_to(path.resolve(), root)
        if rel is None:
            raise ValueError(f"Path escapes {scope} scope: {path}")
        return rel


def _safe_resolve(workspace_root: Path, raw: str) -> Path:
    """Resolve *raw* relative to workspace_root, rejecting traversal escapes."""
    sandbox = FileToolSandbox(workspace_root=workspace_root, session_root=workspace_root / _SESSION_DIR_NAME)
    return sandbox.resolve(_SCOPE_WORKSPACE, raw)


def _normalize_scope(scope: str) -> str:
    scope = (scope or _SCOPE_WORKSPACE).strip()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope {scope!r}; expected 'workspace' or 'session'")
    return scope


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root.resolve())
    except ValueError:
        return None


def _scope_parameter() -> dict[str, object]:
    return {
        "type": "string",
        "enum": [_SCOPE_WORKSPACE, _SCOPE_SESSION],
        "description": (
            "Data scope to access. Use 'workspace' for shared workspace files excluding sessions, "
            "or 'session' for the current session directory."
        ),
        "default": _SCOPE_WORKSPACE,
    }


# -- list_files ---------------------------------------------------------


class ListFilesTool(BaseTool):
    """List directory contents (non-recursive)."""

    name = "list_files"
    description = (
        "List files and subdirectories under a data scope. Workspace scope excludes sessions; "
        "session scope is limited to the current session."
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

    async def execute(self, path: str = "", scope: str = _SCOPE_WORKSPACE) -> str:
        scope = _normalize_scope(scope)
        target = self._sandbox.resolve(scope, path)
        if not target.exists():
            return f"Error: path not found: {path!r}"
        if not target.is_dir():
            return f"Error: not a directory: {path!r}"

        entries = [
            p for p in target.iterdir()
            if not (scope == _SCOPE_WORKSPACE and target == self._sandbox.root_for(scope) and p.name == _SESSION_DIR_NAME)
        ]
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
    description = (
        "Read a file under a data scope. Workspace scope excludes sessions; "
        "session scope is limited to the current session."
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
                    "description": "Relative path to the file under the selected scope.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, scope: str = _SCOPE_WORKSPACE) -> str:
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
        "Create or overwrite a file under a data scope. Creates parent directories if needed. "
        "Workspace scope excludes sessions; session scope is limited to the current session."
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

    async def execute(self, path: str, content: str, scope: str = _SCOPE_WORKSPACE) -> str:
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
        "Search file contents with a regex pattern under a data scope. Use glob to narrow file types "
        "(e.g. '*.json', '*.md'). Results limited to first 200 files. Workspace scope excludes sessions; "
        "session scope is limited to the current session."
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
        scope: str = _SCOPE_WORKSPACE,
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
            if scope == _SCOPE_WORKSPACE and (
                _is_under_workspace_sessions(p, self._sandbox.workspace_root)
                or _is_under_workspace_sessions(resolved, self._sandbox.workspace_root)
            ):
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
    return FileToolSandbox(workspace_root=root, session_root=root / _SESSION_DIR_NAME)


def _is_under_workspace_sessions(path: Path, workspace_root: Path) -> bool:
    rel = _relative_to(path, workspace_root)
    return rel is not None and rel.parts[:1] == (_SESSION_DIR_NAME,)


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / 1024 / 1024:.1f}MB"
