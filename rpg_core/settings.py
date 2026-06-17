"""RPG World settings — shared by core, channel, and API layers.

Settings are read from ``rpg_world/settings.yaml`` once at process startup and
are **read-only** thereafter.  The active profile is selected through
``RPG_WORLD_PROFILE`` before the Python process starts; it defaults to
``local``.

Path resolution
---------------
Workspace is an explicit parameter in every path method.  The caller always
passes a workspace identifier:

- ``""`` − the default/root workspace (maps to ``rpg_world/data/``)
- ``"data/<name>"`` − a named workspace under ``rpg_world/data/<name>/``

Relative path values (``data.character_path``, ``data.lorebook_path`` from
settings.yaml) are resolved against the workspace root via
:func:`rpg_world.rpg_core.utils.path_utils.resolve_rpg_path`.

Session-scoped data paths are deterministic (not user-configurable):
``{workspace_root}/sessions/{session_id}/{filename}``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rpg_world.rpg_core.utils.path_utils import (
    PACKAGE_ROOT as _PACKAGE_ROOT,
)
from rpg_world.rpg_core.utils.path_utils import (
    resolve_rpg_path,
    resolve_workspace_root,
)

# Location of settings.yaml relative to this module
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.yaml"
_RPG_CORE_DIR = Path(__file__).resolve().parent
_PROFILE_ENV = "RPG_WORLD_PROFILE"
_TELEGRAM_BOT_NAME_RE = __import__("re").compile(r"^[A-Za-z0-9_]+$")

# Known data-type subdirectories inside data/ — these are excluded from
# workspace discovery in path_utils.list_workspaces().
_KNOWN_DATA_DIRS = frozenset({"character", "lorebook", "memory_sub_agent", "sessions"})

# Session data directory name — deterministic, not configurable.
_SESSION_DIR_NAME = "sessions"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge settings dicts.

    Lists are replaced, except ``modules.telegram.bots`` which is merged by
    bot ``name`` so profiles can override individual bots.
    """

    def merge_value(left: Any, right: Any, path: tuple[str, ...]) -> Any:
        if (
            path == ("modules", "telegram", "bots")
            and isinstance(left, list)
            and isinstance(right, list)
        ):
            return _merge_bots(left, right)
        if isinstance(left, dict) and isinstance(right, dict):
            return merge_dict(left, right, path)
        return right

    def merge_dict(left: dict[str, Any], right: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            key_path = (*path, str(key))
            if key in merged:
                merged[key] = merge_value(merged[key], value, key_path)
            else:
                merged[key] = value
        return merged

    def _merge_bots(left: list[Any], right: list[Any]) -> list[Any]:
        merged = [dict(item) if isinstance(item, dict) else item for item in left]
        index_by_name = {
            item.get("name"): idx
            for idx, item in enumerate(merged)
            if isinstance(item, dict) and item.get("name")
        }
        for bot in right:
            if not isinstance(bot, dict) or not bot.get("name"):
                merged.append(bot)
                continue
            name = bot["name"]
            if name in index_by_name and isinstance(merged[index_by_name[name]], dict):
                idx = index_by_name[name]
                merged[idx] = merge_value(merged[idx], bot, ("modules", "telegram", "bots", str(name)))
            else:
                index_by_name[name] = len(merged)
                merged.append(dict(bot))
        return merged

    return merge_dict(base, override, ())


def _load() -> dict[str, object]:
    if _SETTINGS_PATH.is_file():
        return _load_yaml_mapping(_SETTINGS_PATH, "settings.yaml")
    return {}


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a mapping")
    return loaded


def _resolve_profile_override(profile_name: str, profile: Any) -> dict[str, Any]:
    """Return the override dict for a profile.

    Supported forms:

    ``local: {}``
        Inline override, unchanged from the original YAML format.

    ``local: settings.local.yaml``
        Load a profile override file relative to ``settings.yaml``.

    ``local: {file: settings.local.yaml, required: true, ...}``
        Merge inline keys first, then the file override. Missing files are
        allowed unless ``required`` is truthy, which is convenient for
        gitignored local profile files.
    """
    if profile is None:
        return {}
    if isinstance(profile, str):
        return _load_profile_file(profile_name, profile, required=False)
    if not isinstance(profile, dict):
        raise ValueError(f"settings profile must be a mapping or file path: {profile_name}")

    file_value = profile.get("file")
    required = Settings._as_bool(profile.get("required", False), False)
    inline = {
        key: value
        for key, value in profile.items()
        if key not in {"file", "required"}
    }
    if file_value is None:
        return inline
    if not isinstance(file_value, str) or not file_value.strip():
        raise ValueError(f"settings profile file must be a non-empty string: {profile_name}")
    file_override = _load_profile_file(profile_name, file_value, required=required)
    return _deep_merge(inline, file_override)


def _load_profile_file(profile_name: str, file_value: str, *, required: bool) -> dict[str, Any]:
    path = Path(file_value).expanduser()
    if not path.is_absolute():
        path = _SETTINGS_PATH.parent / path
    if not path.is_file():
        if required:
            raise ValueError(f"settings profile file not found: profile={profile_name} file={path}")
        return {}
    return _load_yaml_mapping(path, f"settings profile file: {profile_name}")


@dataclass
class MemorySettings:
    """记忆系统配置（对应 settings.yaml 中 ``memory`` 节）。"""

    enabled: bool = False
    """是否启用向量记忆索引与检索。"""

    embedding_model_path: str = ""
    """嵌入模型 GGUF 文件路径（相对于工作区根目录），为空时禁用。"""

    n_ctx: int = 32768
    """嵌入模型的上下文窗口大小（token），默认 32K 与模型对齐。"""

    n_gpu_layers: int = 0
    """GPU 加速层数（0=纯 CPU，-1=全部 GPU）。"""

    embedding_n_threads: int = 4
    """嵌入模型 CPU 线程数。"""

    embedding_verbose: bool = False
    """是否输出嵌入模型 llama.cpp verbose 日志。"""

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

    rerank_n_gpu_layers: int = 0
    """本地重排模型 GPU 加速层数。"""

    rerank_temperature: float = 0.0
    """本地重排模型采样温度。"""

    query_planner_enabled: bool = False
    """是否启用本地 llama.cpp 查询规划器。"""

    query_planner_model_path: str = ""
    """查询规划模型 GGUF 路径，为空或不存在时回退到规则规划器。"""

    query_planner_n_ctx: int = 2048
    """查询规划模型上下文窗口。"""

    query_planner_n_gpu_layers: int = 0
    """查询规划模型 GPU 加速层数。"""

    query_planner_temperature: float = 0.0
    """查询规划模型采样温度。"""

    query_planner_max_tokens: int = 512
    """查询规划模型最大输出 token 数。"""

    llama_process_enabled: bool = True
    """是否将 llama.cpp 推理隔离到托管子进程。"""

    llama_request_timeout_ms: int = 60000
    """主进程等待 llama 子进程单次请求响应的超时时间。"""

    llama_startup_timeout_ms: int = 120000
    """llama 子进程启动超时时间。"""

    llama_max_parallel_models: int = 2
    """llama 子进程中允许并行调度的最大模型实例数。"""

    chunk_size: int = 2000
    """单文件超过此字符数时分块。"""

    chunk_overlap: int = 64
    """分块重叠字符数。"""


@dataclass(frozen=True)
class TelegramBotSettings:
    """Resolved Telegram bot configuration."""

    name: str
    enabled: bool = False
    token: str = ""
    workspace: str = ""
    allow_from: list[str] | None = None
    streaming: bool = True
    proxy: str = ""
    stream_edit_interval_ms: int = 800
    stream_edit_min_chars: int = 24
    request_timeout_ms: int = 5000


class Settings:
    """Read-only settings proxy. Attributes mirror merged ``settings.yaml``."""

    def __init__(self) -> None:
        loaded = _load()
        profile_name = os.environ.get(_PROFILE_ENV, "local").strip() or "local"
        profiles = loaded.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("settings.yaml profiles must be a mapping")
        if profile_name not in profiles:
            raise ValueError(f"settings profile not found: {profile_name}")
        base = loaded.get("base", {})
        profile = _resolve_profile_override(profile_name, profiles.get(profile_name))
        if not isinstance(base, dict):
            raise ValueError("settings.yaml base must be a mapping")
        self.profile = profile_name
        self._raw = _deep_merge(base, profile)
        self._validate_settings()

    @staticmethod
    def _first_non_empty(*values: str | None) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def get_openai_api_key(self, explicit: str | None = None) -> str | None:
        """Return API key with priority: explicit -> YAML api_key -> env(api_key_env)."""
        agent = self.agent_settings
        api_key_env = self._first_non_empty(agent.get("api_key_env"))
        return self._first_non_empty(
            explicit,
            agent.get("api_key"),
            os.environ.get(api_key_env) if api_key_env else None,
        )

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    @property
    def agent_settings(self) -> dict[str, Any]:
        raw = self._raw.get("agent", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def module_settings(self) -> dict[str, Any]:
        raw = self._raw.get("modules", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def telegram_bots(self) -> list[TelegramBotSettings]:
        telegram = self.module_settings.get("telegram", {})
        if not isinstance(telegram, dict):
            return []
        bots = telegram.get("bots", [])
        if not isinstance(bots, list):
            return []
        return [self._build_telegram_bot(bot) for bot in bots if isinstance(bot, dict)]

    def _build_telegram_bot(self, bot: dict[str, Any]) -> TelegramBotSettings:
        token_env = self._first_non_empty(bot.get("token_env"))
        token = self._first_non_empty(
            bot.get("bot_token"),
            os.environ.get(token_env) if token_env else None,
        ) or ""
        allow_from = bot.get("allow_from", ["*"])
        if not isinstance(allow_from, list):
            allow_from = ["*"]
        return TelegramBotSettings(
            name=str(bot.get("name", "")),
            enabled=self._as_bool(bot.get("enabled", False), False),
            token=token,
            workspace=str(bot.get("workspace", "") or ""),
            allow_from=[str(item) for item in allow_from],
            streaming=self._as_bool(bot.get("streaming", True), True),
            proxy=str(bot.get("proxy", "") or ""),
            stream_edit_interval_ms=self._as_int(bot.get("stream_edit_interval_ms", 800), 800),
            stream_edit_min_chars=self._as_int(bot.get("stream_edit_min_chars", 24), 24),
            request_timeout_ms=self._as_int(bot.get("request_timeout_ms", 5000), 5000),
        )

    @staticmethod
    def _as_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default

    @staticmethod
    def _as_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _validate_settings(self) -> None:
        modules = self.module_settings
        telegram = modules.get("telegram", {})
        if not isinstance(telegram, dict):
            return
        bots = telegram.get("bots", [])
        if not isinstance(bots, list):
            raise ValueError("telegram bot config invalid: bots must be a list")

        seen_names: set[str] = set()
        token_to_workspace: dict[str, tuple[str, str]] = {}
        workspace_to_token: dict[str, tuple[str, str]] = {}
        telegram_enabled = self._as_bool(telegram.get("enabled", False), False)
        for raw_bot in bots:
            if not isinstance(raw_bot, dict):
                raise ValueError("telegram bot config invalid: bot entry must be a mapping")
            name = str(raw_bot.get("name", "") or "")
            if not name or not _TELEGRAM_BOT_NAME_RE.fullmatch(name):
                raise ValueError(f"telegram bot config invalid: bot={name or '<missing>'} invalid name")
            if name in seen_names:
                raise ValueError(f"telegram bot config invalid: bot={name} duplicate name")
            seen_names.add(name)
            bot = self._build_telegram_bot(raw_bot)
            if not bot.enabled:
                continue
            if not telegram_enabled:
                continue
            if not bot.token:
                raise ValueError(f"telegram bot config invalid: bot={name} missing token")
            if not bot.workspace.strip():
                raise ValueError(f"telegram bot config invalid: bot={name} missing workspace")
            if bot.token in token_to_workspace:
                other_name, other_workspace = token_to_workspace[bot.token]
                if other_workspace != bot.workspace:
                    raise ValueError(
                        "telegram bot config invalid: token reused across workspaces "
                        f"bot={name} conflicts_with={other_name} "
                        f"workspace={bot.workspace} other_workspace={other_workspace}"
                    )
            token_to_workspace[bot.token] = (name, bot.workspace)
            if bot.workspace in workspace_to_token:
                other_name, other_token = workspace_to_token[bot.workspace]
                if other_token != bot.token:
                    raise ValueError(
                        "telegram bot config invalid: workspace reused by multiple tokens "
                        f"bot={name} conflicts_with={other_name} workspace={bot.workspace}"
                    )
            workspace_to_token[bot.workspace] = (name, bot.token)

    # ------------------------------------------------------------------
    # Workspace-scoped path methods
    #
    # Every method that returns a data path receives an explicit
    # *workspace* parameter.  There is NO implicit "active workspace" —
    # callers always specify which workspace they operate on.
    # ------------------------------------------------------------------

    def character_path(self, workspace: str) -> str:
        """Resolve the character data directory for *workspace*."""
        data = self._raw.get("data", {})
        value = data.get("character_path", "character") if isinstance(data, dict) else "character"
        return str(resolve_rpg_path(value, _PACKAGE_ROOT, workspace))

    def lorebook_path(self, workspace: str) -> str:
        """Resolve the lorebook data directory for *workspace*."""
        data = self._raw.get("data", {})
        value = data.get("lorebook_path", "lorebook") if isinstance(data, dict) else "lorebook"
        return str(resolve_rpg_path(value, _PACKAGE_ROOT, workspace))

    @property
    def jinja_dir(self) -> Path:
        """Path to the Jinja template directory (rpg_core/jinja/)."""
        return _RPG_CORE_DIR / "jinja"

    @property
    def verbose_logging(self) -> bool:
        return self.agent_settings.get("verbose_logging", False)

    @property
    def memory_sub_agent_config(self) -> dict[str, object]:
        """memory_sub_agent 完整配置 dict（保持向后兼容）。"""
        return self.agent_settings.get("memory_sub_agent", {})

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
        return self.agent_settings.get("status_sub_agent", {})

    @property
    def max_tool_calls(self) -> int:
        return self.agent_settings.get("max_tool_call_limit", 10)

    @property
    def include_tool_records(self) -> bool:
        return self.agent_settings.get("include_tool_records", True)

    @property
    def agent_model(self) -> str:
        """用于 API 层创建 RPGGameAgent 的默认模型名。"""
        return self.agent_settings.get("model", "deepseek-v4-flash")

    @property
    def agent_base_url(self) -> str | None:
        """用于 API 层创建 RPGGameAgent 的 base URL。None 表示使用 SDK 默认值。"""
        return self.agent_settings.get("base_url")

    @property
    def agent_max_tokens(self) -> int | None:
        return self.agent_settings.get("max_tokens")

    @property
    def agent_temperature(self) -> float | None:
        return self.agent_settings.get("temperature")

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    # list_workspaces() has moved to rpg_world.rpg_core.utils.path_utils
    # as a pure function.  Workspace discovery is not a settings concern.

    # set_active_workspace() has been removed.  Workspace is no longer
    # a mutable server-wide state — every API call / agent instance
    # explicitly passes the workspace it operates on.

    # ------------------------------------------------------------------
    # Session operations (deterministic paths, not from settings.yaml)
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
        if not isinstance(raw, dict):
            raw = {}
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
        planner_raw = raw.get("query_planner_model_path", "")
        if planner_raw:
            p = Path(planner_raw)
            planner_resolved = str(p if p.is_absolute() else (_PACKAGE_ROOT / p).resolve())
        else:
            planner_resolved = planner_raw
        return MemorySettings(
            enabled=raw.get("enabled", False),
            embedding_model_path=embed_resolved,
            n_ctx=raw.get("n_ctx", 32768),
            n_gpu_layers=raw.get("n_gpu_layers", 0),
            embedding_n_threads=self._as_int(raw.get("embedding_n_threads", 4), 4),
            embedding_verbose=self._as_bool(raw.get("embedding_verbose", False), False),
            top_k=raw.get("top_k", 5),
            hybrid_enabled=raw.get("hybrid_enabled", True),
            vector_k=raw.get("vector_k", 50),
            keyword_k=raw.get("keyword_k", 50),
            rerank_enabled=raw.get("rerank_enabled", False),
            rerank_model_path=rerank_resolved,
            rerank_max_candidates=raw.get("rerank_max_candidates", 10),
            rerank_n_ctx=raw.get("rerank_n_ctx", 4096),
            rerank_n_gpu_layers=self._as_int(raw.get("rerank_n_gpu_layers", 0), 0),
            rerank_temperature=raw.get("rerank_temperature", 0.0),
            query_planner_enabled=raw.get("query_planner_enabled", False),
            query_planner_model_path=planner_resolved,
            query_planner_n_ctx=raw.get("query_planner_n_ctx", 2048),
            query_planner_n_gpu_layers=raw.get("query_planner_n_gpu_layers", 0),
            query_planner_temperature=raw.get("query_planner_temperature", 0.0),
            query_planner_max_tokens=raw.get("query_planner_max_tokens", 512),
            llama_process_enabled=self._as_bool(raw.get("llama_process_enabled", True), True),
            llama_request_timeout_ms=self._as_int(raw.get("llama_request_timeout_ms", 60000), 60000),
            llama_startup_timeout_ms=self._as_int(raw.get("llama_startup_timeout_ms", 120000), 120000),
            llama_max_parallel_models=self._as_int(raw.get("llama_max_parallel_models", 2), 2),
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
