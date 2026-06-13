"""RPG World settings — shared by core and API layers.

Settings are read from ``rpg_world/settings.json`` once at startup and are
**read-only** thereafter.  Modifying ``settings.json`` requires a process
restart to take effect.

Path resolution
---------------
Workspace is an explicit parameter in every path method.  The caller always
passes a workspace identifier:

- ``""`` − the default/root workspace (maps to ``rpg_world/data/``)
- ``"data/<name>"`` − a named workspace under ``rpg_world/data/<name>/``

Relative path values (``character_path``, ``lorebook_path`` from
settings.json) are resolved against the workspace root via
:func:`rpg_world.rpg_core.utils.path_utils.resolve_rpg_path`.

Session-scoped data paths are deterministic (not user-configurable):
``{workspace_root}/sessions/{session_id}/{filename}``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rpg_world.rpg_core.utils.path_utils import (
    PACKAGE_ROOT as _PACKAGE_ROOT,
)
from rpg_world.rpg_core.utils.path_utils import (
    resolve_rpg_path,
    resolve_workspace_root,
)

# Location of settings.json relative to this module
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
_RPG_CORE_DIR = Path(__file__).resolve().parent

# Known data-type subdirectories inside data/ — these are excluded from
# workspace discovery in path_utils.list_workspaces().
_KNOWN_DATA_DIRS = frozenset({"character", "lorebook", "memory_sub_agent", "sessions"})

# Session data directory name — deterministic, not configurable.
_SESSION_DIR_NAME = "sessions"


def _load() -> dict[str, object]:
    if _SETTINGS_PATH.is_file():
        with _SETTINGS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


@dataclass
class MemorySettings:
    """记忆系统配置（对应 settings.json 中 ``memory`` 节）。"""

    enabled: bool = False
    """是否启用向量记忆索引与检索。"""

    embedding_model_path: str = ""
    """嵌入模型 GGUF 文件路径（相对于工作区根目录），为空时禁用。"""

    n_ctx: int = 32768
    """嵌入模型的上下文窗口大小（token），默认 32K 与模型对齐。"""

    n_gpu_layers: int = 0
    """GPU 加速层数（0=纯 CPU，-1=全部 GPU）。"""

    top_k: int = 5
    """向量检索返回的最大结果数。"""

    hybrid_enabled: bool = True
    """是否启用向量 + FTS 混合检索。"""

    vector_k: int = 50
    """混合检索中向量召回候选数。"""

    keyword_k: int = 50
    """混合检索中关键词召回候选数。"""

    rerank_enabled: bool = False
    """是否启用本地 llama.cpp 重排。"""

    rerank_model_path: str = ""
    """重排模型 GGUF 路径，为空或不存在时自动回退。"""

    rerank_max_candidates: int = 10
    """送入本地重排模型的最大候选数。"""

    rerank_n_ctx: int = 4096
    """本地重排模型上下文窗口。"""

    rerank_temperature: float = 0.0
    """本地重排模型采样温度。"""

    chunk_size: int = 2000
    """单文件超过此字符数时分块。"""

    chunk_overlap: int = 64
    """分块重叠字符数。"""


class Settings:
    """Read-write settings proxy.  Attributes mirror keys in settings.json."""

    def __init__(self) -> None:
        self._raw = _load()

    # ------------------------------------------------------------------
    # Workspace-scoped path methods
    #
    # Every method that returns a data path receives an explicit
    # *workspace* parameter.  There is NO implicit "active workspace" —
    # callers always specify which workspace they operate on.
    # ------------------------------------------------------------------

    def character_path(self, workspace: str) -> str:
        """Resolve the character data directory for *workspace*."""
        value = self._raw.get("character_path", "character")
        return str(resolve_rpg_path(value, _PACKAGE_ROOT, workspace))

    def lorebook_path(self, workspace: str) -> str:
        """Resolve the lorebook data directory for *workspace*."""
        value = self._raw.get("lorebook_path", "lorebook")
        return str(resolve_rpg_path(value, _PACKAGE_ROOT, workspace))

    @property
    def jinja_dir(self) -> Path:
        """Path to the Jinja template directory (rpg_core/jinja/)."""
        return _RPG_CORE_DIR / "jinja"

    @property
    def verbose_logging(self) -> bool:
        return self._raw.get("agent_config", {}).get("verbose_logging", False)

    @property
    def memory_sub_agent_config(self) -> dict[str, object]:
        """memory_sub_agent 完整配置 dict（保持向后兼容）。"""
        return self._raw.get("agent_config", {}).get("memory_sub_agent", {})

    # ── memory_sub_agent 管线级配置 ────────────────────────────────

    @property
    def memory_summary_config(self) -> dict[str, object]:
        """summary 管线配置：compress_rounds / keep_rounds。"""
        return self.memory_sub_agent_config.get("summary", {})

    @property
    def memory_recall_config(self) -> dict[str, object]:
        """recall 管线配置：max_items。"""
        return self.memory_sub_agent_config.get("recall", {})

    @property
    def memory_story_config(self) -> dict[str, object]:
        """story 管线配置：trigger_rounds。"""
        return self.memory_sub_agent_config.get("story", {})

    @property
    def memory_story_trigger_rounds(self) -> int:
        """N 轮新对话后自动触发剧情记忆提取，0 表示关闭。"""
        return self.memory_story_config.get("trigger_rounds", 0)

    @property
    def memory_compress_batch_size(self) -> int:
        """每批压缩的用户轮次数。"""
        return self.memory_summary_config.get("compress_batch_size", 10)

    @property
    def memory_keep_rounds(self) -> int:
        """压缩后保留的最近对话轮数。"""
        return self.memory_summary_config.get("keep_rounds", 5)

    @property
    def memory_compression_enabled(self) -> bool:
        """是否启用自动压缩。"""
        return self.memory_summary_config.get("compression_enabled", True)

    @property
    def status_sub_agent_config(self) -> dict[str, object]:
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

    # list_workspaces() has moved to rpg_world.rpg_core.utils.path_utils
    # as a pure function.  Workspace discovery is not a settings concern.

    # set_active_workspace() has been removed.  Workspace is no longer
    # a mutable server-wide state — every API call / agent instance
    # explicitly passes the workspace it operates on.

    # ------------------------------------------------------------------
    # Session operations (deterministic paths, not from settings.json)
    #
    # Every method receives an explicit *workspace* parameter.
    # Core principle: every session-scoped data domain has a dedicated
    # getter method.  Do NOT join "sessions" / filenames outside this
    # class — call the method instead.
    # ------------------------------------------------------------------

    def sessions_base_dir(self, workspace: str) -> Path:
        """Return the ``sessions/`` base directory under *workspace*."""
        return resolve_workspace_root(_PACKAGE_ROOT, workspace) / _SESSION_DIR_NAME

    def session_dir(self, workspace: str, session_id: str) -> Path:
        """Return the per-session directory for *session_id*.

        All session-scoped data (status, history, summary, memory) lives
        under this directory.  Use the dedicated getter methods below
        (``get_status_dir``, ``get_history_path``, …) to access specific
        sub-paths; avoid joining *session_dir* by hand.
        """
        return self.sessions_base_dir(workspace) / session_id

    # ── 记忆配置 ────────────────────────────────────────────────

    @property
    def memory_settings(self) -> MemorySettings:
        """记忆系统配置对象（向量检索等）。"""
        raw = self._raw.get("memory", {})
        embed_raw = raw.get("embedding_model_path", "")
        if embed_raw:
            p = Path(embed_raw)
            if p.is_absolute():
                embed_resolved = str(p)
            else:
                # 模型路径相对于包根（rpg_world/）解析，不经过 workspace
                embed_resolved = str((_PACKAGE_ROOT / p).resolve())
        else:
            embed_resolved = embed_raw
        rerank_raw = raw.get("rerank_model_path", "")
        if rerank_raw:
            p = Path(rerank_raw)
            rerank_resolved = str(p if p.is_absolute() else (_PACKAGE_ROOT / p).resolve())
        else:
            rerank_resolved = rerank_raw
        return MemorySettings(
            enabled=raw.get("enabled", False),
            embedding_model_path=embed_resolved,
            n_ctx=raw.get("n_ctx", 32768),
            n_gpu_layers=raw.get("n_gpu_layers", 0),
            top_k=raw.get("top_k", 5),
            hybrid_enabled=raw.get("hybrid_enabled", True),
            vector_k=raw.get("vector_k", 50),
            keyword_k=raw.get("keyword_k", 50),
            rerank_enabled=raw.get("rerank_enabled", False),
            rerank_model_path=rerank_resolved,
            rerank_max_candidates=raw.get("rerank_max_candidates", 10),
            rerank_n_ctx=raw.get("rerank_n_ctx", 4096),
            rerank_temperature=raw.get("rerank_temperature", 0.0),
            chunk_size=raw.get("chunk_size", 2000),
            chunk_overlap=raw.get("chunk_overlap", 64),
        )

    def get_vector_db_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``memory_vectors.db`` path for the given session."""
        return self.session_dir(workspace, session_id) / "memory_vectors.db"

    # ── Session-scoped directory getters ──────────────────────────────

    def get_status_dir(self, workspace: str, session_id: str) -> Path:
        """Return the ``status/`` directory for the given session."""
        return self.session_dir(workspace, session_id) / "status"

    # ── Session-scoped file path getters ──────────────────────────────

    def get_history_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``history.jsonl`` file path for the given session.

        主历史文件，用于构建上下文和压缩。``MemorySubAgent.compact_history()`` 会截断此文件。
        """
        return self.session_dir(workspace, session_id) / "history.jsonl"

    def get_cold_history_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``history_cold.jsonl`` file path for the given session.

        冷备份历史文件，只追加写入，永不截断。与主 history.jsonl 同步写入，
        用于后续的记忆搜寻和数据恢复。
        """
        return self.session_dir(workspace, session_id) / "history_cold.jsonl"

    def get_summary_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``rpg_summaries.json`` file path for the given session."""
        return self.session_dir(workspace, session_id) / "rpg_summaries.json"

    def get_story_memory_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``story_memory.json`` file path for the given session."""
        return self.session_dir(workspace, session_id) / "story_memory.json"

    def get_persistent_memory_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``persistent_memory.json`` file path for the given session."""
        return self.session_dir(workspace, session_id) / "persistent_memory.json"

    def get_session_meta_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``session.json`` metadata file path for the given session."""
        return self.session_dir(workspace, session_id) / "session.json"

    # ── Session file listing ──────────────────────────────────────────

    def list_session_files(self, workspace: str, session_id: str) -> list[Path]:
        """List all files and directories inside a session's data dir."""
        sdir = self.session_dir(workspace, session_id)
        if not sdir.is_dir():
            return []
        return sorted(sdir.iterdir())

# Singleton
settings = Settings()
