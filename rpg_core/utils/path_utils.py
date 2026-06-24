"""Path resolution for RPG World settings.

Resolution rules (applied in order):

1. Absolute path (starts with ``/``) — returned as-is.
2. Relative path — resolved relative to the **RPG World project root**.

   * If *workspace* is set (e.g. ``"data/非公开行程"``), the
     workspace path is used as the base: ``character`` →
     ``data/非公开行程/character``.
   * If *workspace* is empty, ``data/`` is used as the base: ``character`` →
     ``data/character``.

All functions are pure — they receive all inputs explicitly and never
read module-level or process-global state.
"""

from __future__ import annotations

import re

from pathlib import Path


_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")

__all__ = [
    "resolve_rpg_path",
    "resolve_workspace_root",
    "get_session_dir",
    "list_workspaces",
    "require_workspace",
    "default_workspace_name",
    "ensure_workspace_dir",
    "resolve_api_workspace",
    "PACKAGE_ROOT",
]

_DEFAULT_WORKSPACE_SUFFIX = "_default_workspace"
_DATA_DIR = "data"

# Project root used for resolving settings-relative paths.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]

# Known data-type subdirectories inside data/ — these are excluded from
# workspace discovery.
_KNOWN_DATA_DIRS = frozenset({
    "character",
    "lorebook",
    "memory_sub_agent",
    "sessions",
})


def require_workspace(workspace: str) -> str:
    """Validate and return *workspace*, raising ``ValueError`` if empty.

    Every entry point (API, CLI, Telegram, AgentManager) must call this
    before resolving any data path.  An empty workspace means the caller
    forgot to specify one — the root ``data/`` directory is never used
    as a silent fallback.
    """
    if not workspace or not workspace.strip():
        raise ValueError(
            "workspace is required (e.g. \"data/非公开行程\"). "
            "Empty string / root workspace is not accepted as a fallback. "
            "Configure the workspace in settings.yaml or pass it explicitly."
        )
    return workspace.strip()


def resolve_rpg_path(
    value: str,
    rpg_root: Path,
    rpg_workspace: str = "",
) -> Path:
    """Resolve a path string according to the rules above.

    Args:
        value: Raw path string from settings.
        rpg_root: RPG World project root directory.
        rpg_workspace: Workspace identifier (e.g. ``""`` or ``"data/非公开行程"``).

    Returns:
        Resolved absolute :class:`Path`.
    """
    p = Path(value)
    if p.is_absolute():
        return p

    if rpg_workspace:
        ws = Path(rpg_workspace)
        base = ws if ws.is_absolute() else rpg_root / ws
    else:
        base = rpg_root / _DATA_DIR

    return (base / p).resolve()


def resolve_workspace_root(
    rpg_root: Path,
    rpg_workspace: str = "",
) -> Path:
    """Return the resolved absolute path to the workspace root directory.

    Cross-session data (character, lorebook) lives directly under this root.
    Session-scoped data lives under ``root / "sessions" / {session_id}``.
    """
    if rpg_workspace:
        ws = Path(rpg_workspace)
        return ws if ws.is_absolute() else (rpg_root / ws).resolve()
    return (rpg_root / _DATA_DIR).resolve()


def get_session_dir(
    rpg_root: Path,
    rpg_workspace: str = "",
    session_id: str = "default",
) -> Path:
    """Return the session directory for a given session_id."""
    ws_root = resolve_workspace_root(rpg_root, rpg_workspace)
    return ws_root / "sessions" / session_id


def list_workspaces(rpg_root: Path) -> list[dict[str, str]]:
    """Discover available workspaces under *rpg_root/data/*.

    Returns a list of ``{"name": …, "label": …}`` dicts.  The first
    entry is always the default workspace (``name=""``, ``label="默认"``).
    Named workspaces are subdirectories of ``data/`` that are not
    known data-type directories.  Their ``name`` is ``"data/<dir>"`` so
    that :func:`resolve_rpg_path` resolves paths under the workspace.
    """
    workspaces: list[dict[str, str]] = [
        {"name": "", "label": "默认（根工作区）"},
    ]
    data_dir = rpg_root / _DATA_DIR
    if data_dir.is_dir():
        for entry in sorted(data_dir.iterdir()):
            if entry.is_dir() and entry.name not in _KNOWN_DATA_DIRS:
                workspaces.append({"name": f"{_DATA_DIR}/{entry.name}", "label": entry.name})
    return workspaces


def _sanitize_name(name: str | None) -> str | None:
    """Return *name* if it is safe for use as a directory name component, or ``None``."""
    if name and _VALID_NAME_RE.match(name):
        return name
    return None


def default_workspace_name(channel_name: str | None) -> str:
    """Return the default workspace name for a channel.

    Follows the same ``{channel}_{suffix}`` convention as
    :meth:`ChannelAdapter.get_session_id` uses for sessions.

    Falls back to ``"unknown"`` prefix when *channel_name* is
    ``None``, empty, or contains characters unsafe for directory names.

    >>> default_workspace_name("cli")
    'data/cli_default_workspace'
    >>> default_workspace_name("")           # doctest: +ELLIPSIS
    'data/unknown...'
    >>> default_workspace_name(None)          # doctest: +ELLIPSIS
    'data/unknown...'
    """
    safe = _sanitize_name(channel_name) or "unknown"
    return f"{_DATA_DIR}/{safe}{_DEFAULT_WORKSPACE_SUFFIX}"


def ensure_workspace_dir(rpg_root: Path, workspace: str) -> None:
    """Create the workspace directory if it does not exist.

    Safe to call multiple times — uses ``exist_ok=True``.
    Only creates the workspace root directory (e.g. ``data/cli_default_workspace/``).
    Subdirectories (``character/``, ``sessions/``, etc.) are created lazily
    by their respective managers.
    """
    ws_root = resolve_workspace_root(rpg_root, workspace)
    ws_root.mkdir(parents=True, exist_ok=True)


def resolve_api_workspace(workspace: str) -> str:
    """Resolve workspace for API/WebUI requests.

    When *workspace* is empty (not selected in the frontend),
    defaults to ``"data/dashboard_api_default_workspace"`` so the API
    always has a valid workspace directory.
    """
    if workspace and workspace.strip():
        return workspace.strip()
    return default_workspace_name("api")
