"""RPG World settings — shared by core and API layers.

Settings are read from ``rpg_world/settings.json``.  Path resolution:

- Absolute path (starts with ``/``) — returned as-is.
- Relative path — resolved relative to ``rpg_world/``.  If
  ``active_workspace`` is set (e.g. ``"data/非公开行程"``), it is used
  as the base directory; otherwise ``data/`` is used as the default base.

See :func:`rpg_world.rpg_core.utils.path_utils.resolve_rpg_path` for details.

Session-scoped data paths are deterministic (not user-configurable):
``{workspace_root}/sessions/{session_id}/{filename}``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.utils.path_utils import resolve_rpg_path, resolve_workspace_root

# Location of settings.json relative to this module
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
# Package roots used to resolve relative paths
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_RPG_CORE_DIR = Path(__file__).resolve().parent

# Known data-type subdirectories inside data/ — these are excluded from
# workspace discovery in list_workspaces().
_KNOWN_DATA_DIRS = frozenset({"character", "lorebook", "memory_sub_agent", "sessions"})

# Session data directory name and filenames — deterministic, not configurable.
_SESSION_DIR_NAME = "sessions"


def _load() -> dict[str, Any]:
    if _SETTINGS_PATH.is_file():
        with _SETTINGS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


class Settings:
    """Read-write settings proxy.  Attributes mirror keys in settings.json."""

    def __init__(self) -> None:
        self._raw = _load()

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _resolve(self, key: str, default: str) -> str:
        """Resolve a settings value, delegating to :func:`resolve_rpg_path`."""
        value = self._raw.get(key, default)
        return str(resolve_rpg_path(
            value=value,
            rpg_root=_PACKAGE_ROOT,
            rpg_workspace=self.active_workspace,
        ))

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def active_workspace(self) -> str:
        return self._raw.get("active_workspace", "")

    @property
    def workspace_root(self) -> Path:
        """Resolved absolute path to the active workspace root.

        Cross-session data (character, lorebook) lives directly under this.
        Session-scoped data lives under ``workspace_root / "sessions" / {session_id}``.
        """
        return resolve_workspace_root(_PACKAGE_ROOT, self.active_workspace)

    @property
    def character_path(self) -> str:
        return self._resolve("character_path", "character")

    @property
    def lorebook_path(self) -> str:
        return self._resolve("lorebook_path", "lorebook")

    @property
    def pm_details_path(self) -> str:
        """路径：PM 可展开条目的详情文件（JSON，预留）。"""
        return self._resolve("pm_details_path", "pm_details.json")

    @property
    def jinja_dir(self) -> Path:
        """Path to the Jinja template directory (rpg_core/jinja/)."""
        return _RPG_CORE_DIR / "jinja"

    @property
    def verbose_logging(self) -> bool:
        return self._raw.get("agent_config", {}).get("verbose_logging", False)

    @property
    def log_llm_calls(self) -> bool:
        """每轮记录每个 LLM 的 usage（token、计时、模型）。"""
        return self._raw.get("agent_config", {}).get("log_llm_calls", self.verbose_logging)

    @property
    def log_reasoning(self) -> bool:
        """在日志输出中包含推理/思考内容（可能很长）。"""
        return self._raw.get("agent_config", {}).get("log_reasoning", False)

    @property
    def log_tool_timing(self) -> bool:
        """记录每次工具执行的时间。"""
        return self._raw.get("agent_config", {}).get("log_tool_timing", self.verbose_logging)

    @property
    def memory_sub_agent_config(self) -> dict[str, Any]:
        """memory_sub_agent 完整配置 dict（保持向后兼容）。"""
        return self._raw.get("agent_config", {}).get("memory_sub_agent", {})

    # ── memory_sub_agent 管线级配置 ────────────────────────────────

    @property
    def memory_summary_config(self) -> dict[str, Any]:
        """summary 管线配置：compress_rounds / keep_rounds / trigger_rounds。"""
        return self.memory_sub_agent_config.get("summary", {})

    @property
    def memory_recall_config(self) -> dict[str, Any]:
        """recall 管线配置：max_items。"""
        return self.memory_sub_agent_config.get("recall", {})

    @property
    def memory_story_config(self) -> dict[str, Any]:
        """story 管线配置：trigger_rounds。"""
        return self.memory_sub_agent_config.get("story", {})

    @property
    def memory_story_trigger_rounds(self) -> int:
        """N 轮新对话后自动触发剧情记忆提取，0 表示关闭。"""
        return self.memory_story_config.get("trigger_rounds", 0)

    @property
    def memory_compress_rounds(self) -> int:
        """从最老的对话轮次开始压缩的默认轮数。"""
        return self.memory_summary_config.get("compress_rounds", 10)

    @property
    def memory_keep_rounds(self) -> int:
        """压缩后保留的最近对话轮数。"""
        return self.memory_summary_config.get("keep_rounds", 5)

    @property
    def status_sub_agent_config(self) -> dict[str, Any]:
        return self._raw.get("agent_config", {}).get("status_sub_agent", {})

    @property
    def max_tool_calls(self) -> int:
        return self._raw.get("agent_config", {}).get("max_tool_call_limit", 10)

    @property
    def include_tool_records(self) -> bool:
        return self._raw.get("agent_config", {}).get("include_tool_records", True)

    @property
    def agent_model(self) -> str:
        """用于 API 层创建 RPGGameAgent 的默认模型名。"""
        return self._raw.get("agent_config", {}).get("model", "deepseek-v4-flash")

    @property
    def agent_base_url(self) -> str | None:
        """用于 API 层创建 RPGGameAgent 的 base URL。None 表示使用 SDK 默认值。"""
        return self._raw.get("agent_config", {}).get("base_url")

    @property
    def agent_max_tokens(self) -> int | None:
        return self._raw.get("agent_config", {}).get("max_tokens")

    @property
    def agent_temperature(self) -> float | None:
        return self._raw.get("agent_config", {}).get("temperature")

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, str]]:
        """Discover available workspaces.

        Returns a list of ``{"name": …, "label": …}`` dicts.  The first
        entry is always the default workspace (``name=""``, ``label="默认"``).
        Named workspaces are subdirectories of ``data/`` that are not
        known data-type directories.  Their ``name`` is ``"data/<dir>"`` so
        that ``resolve_rpg_path`` resolves paths under the workspace.
        """
        workspaces: list[dict[str, str]] = [
            {"name": "", "label": "默认（根工作区）"},
        ]
        data_dir = _PACKAGE_ROOT / "data"
        if data_dir.is_dir():
            for entry in sorted(data_dir.iterdir()):
                if entry.is_dir() and entry.name not in _KNOWN_DATA_DIRS:
                    workspaces.append({"name": f"data/{entry.name}", "label": entry.name})
        return workspaces

    def set_active_workspace(self, name: str) -> None:
        """Switch the active workspace and persist to disk."""
        self._raw["active_workspace"] = name
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SETTINGS_PATH.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self._raw, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # ------------------------------------------------------------------
    # Session operations (deterministic paths, not from settings.json)
    #
    # Core principle: every session-scoped data domain has a dedicated
    # getter method.  Do NOT join "sessions" / filenames outside this
    # class — call the method instead.
    # ------------------------------------------------------------------

    def sessions_base_dir(self) -> Path:
        """Return the ``sessions/`` base directory under the active workspace."""
        return self.workspace_root / _SESSION_DIR_NAME

    def session_dir(self, session_id: str) -> Path:
        """Return the per-session directory for *session_id*.

        All session-scoped data (status, history, summary, memory) lives
        under this directory.  Use the dedicated getter methods below
        (``get_status_dir``, ``get_history_path``, …) to access specific
        sub-paths; avoid joining *session_dir* by hand.
        """
        return self.sessions_base_dir() / session_id

    # ── Session-scoped directory getters ──────────────────────────────

    def get_status_dir(self, session_id: str) -> Path:
        """Return the ``status/`` directory for the given session."""
        return self.session_dir(session_id) / "status"

    # ── Session-scoped file path getters ──────────────────────────────

    def get_history_path(self, session_id: str) -> Path:
        """Return the ``history.jsonl`` file path for the given session.

        主历史文件，用于构建上下文和压缩。``compact_history()`` 会截断此文件。
        """
        return self.session_dir(session_id) / "history.jsonl"

    def get_cold_history_path(self, session_id: str) -> Path:
        """Return the ``history_cold.jsonl`` file path for the given session.

        冷备份历史文件，只追加写入，永不截断。与主 history.jsonl 同步写入，
        用于后续的记忆搜寻和数据恢复。
        """
        return self.session_dir(session_id) / "history_cold.jsonl"

    def get_summary_path(self, session_id: str) -> Path:
        """Return the ``rpg_summaries.json`` file path for the given session."""
        return self.session_dir(session_id) / "rpg_summaries.json"

    def get_story_memory_path(self, session_id: str) -> Path:
        """Return the ``story_memory.json`` file path for the given session."""
        return self.session_dir(session_id) / "story_memory.json"

    def get_persistent_memory_path(self, session_id: str) -> Path:
        """Return the ``persistent_memory.json`` file path for the given session."""
        return self.session_dir(session_id) / "persistent_memory.json"

    def get_session_meta_path(self, session_id: str) -> Path:
        """Return the ``session.json`` metadata file path for the given session."""
        return self.session_dir(session_id) / "session.json"

    # ── Session file listing ──────────────────────────────────────────

    def list_session_files(self, session_id: str) -> list[Path]:
        """List all files and directories inside a session's data dir."""
        sdir = self.session_dir(session_id)
        if not sdir.is_dir():
            return []
        return sorted(sdir.iterdir())

    # ── Session lifecycle ─────────────────────────────────────────────

    def list_sessions(self) -> list[str]:
        """Discover available session IDs under the active workspace."""
        sdir = self.sessions_base_dir()
        if not sdir.is_dir():
            return []
        return sorted(
            d.name for d in sdir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def create_session(self, session_id: str) -> None:
        """Create a new session directory. Raises ``FileExistsError`` if exists."""
        sdir = self.session_dir(session_id)
        sdir.mkdir(parents=True, exist_ok=False)

    def delete_session(self, session_id: str) -> None:
        """Delete a session directory and all its contents."""
        sdir = self.session_dir(session_id)
        if sdir.exists():
            shutil.rmtree(sdir)


# Singleton
settings = Settings()
