"""Small path-adjacent helpers for RPG World core.

Runtime workspace and session filesystem paths are owned by ``rpg_data``.
Core code must use catalog services for those paths instead of resolving
workspace directories locally.
"""

from __future__ import annotations

import re

from pathlib import Path


_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")

__all__ = [
    "require_workspace",
    "default_workspace_name",
    "resolve_api_workspace",
    "PACKAGE_ROOT",
]

_DEFAULT_WORKSPACE_SUFFIX = "_default_workspace"
_DATA_DIR = "data"

# Project root used for resolving settings-relative paths.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]

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


def resolve_api_workspace(workspace: str) -> str:
    """Resolve workspace for API/WebUI requests.

    When *workspace* is empty (not selected in the frontend),
    defaults to the API workspace so the API always has a valid
    workspace directory.
    """
    if workspace and workspace.strip():
        return workspace.strip()
    return default_workspace_name("api")
