"""RPG World core business settings.

Settings are read from ``rpg_core/settings.yaml`` once at process startup and
are **read-only** thereafter.  The active profile is selected through
``RPG_WORLD_PROFILE`` before the Python process starts; it defaults to
``local``.

Path resolution
---------------
Workspace is an explicit parameter in session path methods.  The caller always
passes a workspace identifier:

- ``""`` − the default/root workspace (maps to ``data/``)
- ``"data/<name>"`` − a named workspace under ``data/<name>/``

Session-scoped data paths are deterministic (not user-configurable):
``{workspace_root}/sessions/{session_id}/{filename}``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from commons.settings import (
    PROFILE_ENV,
    ProfiledYamlSettings,
    forgiving_float,
)
from rpg_core.common_types import ConfigDict, ConfigValue
from llm_service.config import get_runtime_config, resolve_agent_defaults, resolve_llm_config
from llm_service.keys import (
    AGENT_MAIN_BIZ_KEY,
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
)
from rpg_core.utils.path_utils import (
    PACKAGE_ROOT as _PACKAGE_ROOT,
    resolve_workspace_root,
)

# Location of rpg_core process/business settings.
_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
_RPG_CORE_DIR = Path(__file__).resolve().parent
_PROFILE_ENV = PROFILE_ENV

# Session data directory name — deterministic, not configurable.
_SESSION_DIR_NAME = "sessions"

@dataclass
class MemorySettings:
    """记忆系统配置（对应 settings.yaml 中 ``memory`` 节）。"""

    @dataclass(frozen=True)
    class Provider:
        """单个 memory LLM 后端选择。

        具体 OpenAI / llama 参数由 ``llm.yaml`` 和 ``LLMManager`` 负责解析，
        memory 设置只保留业务开关与 provider kind。
        """

        provider: Literal["shared", "openai", "llama"] = "llama"

    enabled: bool = False
    """是否启用向量记忆索引与检索。"""

    embedding_provider: Provider = field(default_factory=Provider)
    """Embedding provider 配置。"""

    query_planner_provider: Provider = field(default_factory=Provider)
    """Query planner provider 配置。"""

    rerank_provider: Provider = field(default_factory=Provider)
    """Reranker provider 配置。"""

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

    keyword_tokenizer: str = "jieba"
    """关键词检索 tokenizer：jieba / bigram / both。"""

    keyword_k: int = 50
    """混合检索中 keyword 召回候选数。"""

    hybrid_vector_weight: float = 0.47
    """混合评分中向量相似度归一化分数的权重。"""

    hybrid_keyword_weight: float = 0.18
    """混合评分中 keyword 匹配归一化分数的权重。"""

    hybrid_raw_md_weight: float = 0.05
    """混合评分中 raw markdown 原文词项覆盖分数的权重。"""

    hybrid_exact_weight: float = 0.10
    """混合评分中精确/模糊匹配分数的权重。"""

    hybrid_expanded_weight: float = 0.10
    """混合评分中 query planner 扩展查询匹配分数的权重。"""

    hybrid_recency_weight: float = 0.05
    """混合评分中时间衰减归一化分数的权重。"""

    hybrid_granularity_weight: float = 0.05
    """混合评分中记忆粒度优先级分数的权重。"""

    raw_md_mode: str = "fallback_only"
    """Raw markdown 召回模式：fallback_only / always / disabled。"""

    raw_md_min_results: int = 0
    """Raw markdown fallback 触发阈值，0 表示当前召回池目标。"""

    rerank_candidate_k: int = 8
    """进入 reranker 的混合检索候选数，最终仍返回 top_k。"""

    rerank_score_weight: float = 0.70
    """Reranker 融合评分中 LLM 重排分的权重（剩余为混合分数权重）。"""

    rerank_enabled: bool = False
    """是否启用本地 llama.cpp 重排。"""

    rerank_model_path: str = ""
    """重排模型 GGUF 路径，为空或不存在时自动回退。"""

    rerank_n_ctx: int = 4096
    """本地重排模型上下文窗口。"""

    rerank_n_gpu_layers: int = 0
    """本地重排模型 GPU 加速层数。"""

    rerank_temperature: float = 0.0
    """本地重排模型采样温度。"""

    rerank_verbose: bool = False
    """重排模型 llama.cpp verbose 日志开关。"""

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

    jieba_dict: str = ""
    """jieba 用户词典路径（相对于项目根目录），留空使用默认词典。"""

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
class CoreLoggingSettings:
    """Core and memory-side logging settings."""

    log_level: str = "DEBUG"


class Settings(ProfiledYamlSettings):
    """Read-only settings proxy. Attributes mirror merged core settings."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "rpg_core/settings.yaml"
        self.env_var = _PROFILE_ENV
        super().__init__()
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
        return self.resolve_openai_api_key(explicit=explicit)

    def resolve_openai_api_key(
        self,
        *,
        explicit: str | None = None,
        explicit_env: str | None = None,
        fallback_to_agent: bool = True,
    ) -> str | None:
        """Resolve an OpenAI API key from explicit values and config fallbacks."""
        if not fallback_to_agent:
            return self._first_non_empty(
                explicit,
                os.environ.get(explicit_env) if explicit_env else None,
            )
        llm_agent = self._llm_agent_openai_settings()
        agent = self.agent_settings
        llm_env = self._first_non_empty(llm_agent.get("api_key_env"))
        agent_env = self._first_non_empty(agent.get("api_key_env"))
        return self._first_non_empty(
            explicit,
            os.environ.get(explicit_env) if explicit_env else None,
            llm_agent.get("api_key"),
            agent.get("api_key"),
            os.environ.get(llm_env) if llm_env else None,
            os.environ.get(agent_env) if agent_env else None,
        )

    @property
    def agent_settings(self) -> ConfigDict:
        raw = self._raw.get("agent", {})
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _llm_agent_openai_settings() -> ConfigDict:
        try:
            cfg = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
        except ValueError:
            return {}
        return cfg.openai if isinstance(cfg.openai, dict) else {}

    @property
    def logging(self) -> CoreLoggingSettings:
        raw = self._mapping("logging")
        return CoreLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
        )

    def _validate_settings(self) -> None:
        self._validate_agent_llm_settings()

    def _validate_agent_llm_settings(self) -> None:
        legacy_model = self._first_non_empty(self.agent_settings.get("model"))
        try:
            agent = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
        except ValueError:
            if not legacy_model:
                raise
            return

        if agent.model:
            return
        if legacy_model:
            return
        raise ValueError(f"llm biz config invalid: {AGENT_MAIN_BIZ_KEY}.model is required")

    @property
    def jinja_dir(self) -> Path:
        """Path to the Jinja template directory (rpg_core/jinja/)."""
        return _RPG_CORE_DIR / "jinja"

    @property
    def verbose_logging(self) -> bool:
        return self.agent_settings.get("verbose_logging", False)

    @property
    def memory_sub_agent_config(self) -> ConfigDict:
        """memory_sub_agent 完整配置 dict。

        ``llm_provider`` 与 ``shared/openai/llama`` 控制子 Agent LLM 来源；
        ``summary/recall/story`` 是记忆管线配置，不属于 provider 配置。
        """
        return self.agent_settings.get("memory_sub_agent", {})

    # ── memory_sub_agent 管线级配置 ────────────────────────────────

    @property
    def memory_summary_config(self) -> ConfigDict:
        """summary 管线配置：compress_rounds / keep_rounds。"""
        return self.memory_sub_agent_config.get("summary", {})

    @property
    def memory_recall_config(self) -> ConfigDict:
        """recall 管线配置：max_items。"""
        return self.memory_sub_agent_config.get("recall", {})

    @property
    def memory_story_config(self) -> ConfigDict:
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
    def status_sub_agent_config(self) -> ConfigDict:
        """status_sub_agent 完整配置 dict，包含显式 LLM provider 选择。"""
        return self.agent_settings.get("status_sub_agent", {})

    @property
    def max_tool_calls(self) -> int:
        return self.agent_settings.get("max_tool_call_limit", 10)

    @property
    def include_tool_records(self) -> bool:
        return self.agent_settings.get("include_tool_records", True)

    @property
    def agent_model(self) -> str:
        """用于 API 层创建 RPGGameAgent 的默认模型名。
        """
        try:
            cfg = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
        except ValueError:
            return self._first_non_empty(self.agent_settings.get("model")) or ""

        value = self._first_non_empty(cfg.model)
        if value:
            return value
        return self._first_non_empty(self.agent_settings.get("model")) or ""

    @property
    def agent_base_url(self) -> str | None:
        """用于 API 层创建 RPGGameAgent 的 base URL。None 表示使用 SDK 默认值。"""
        try:
            cfg = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
            return cfg.base_url
        except ValueError:
            pass
        value = self.agent_settings.get("base_url")
        return str(value) if value is not None else None

    @property
    def agent_max_tokens(self) -> int | None:
        try:
            cfg = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
            if cfg.max_tokens is not None:
                return cfg.max_tokens
        except ValueError:
            pass
        value = self.agent_settings.get("max_tokens")
        return int(value) if value is not None else None

    @property
    def agent_temperature(self) -> float | None:
        try:
            cfg = resolve_agent_defaults(AGENT_MAIN_BIZ_KEY)
            if cfg.temperature is not None:
                return cfg.temperature
        except ValueError:
            pass
        value = self.agent_settings.get("temperature")
        return float(value) if value is not None else None

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    # list_workspaces() has moved to rpg_core.utils.path_utils
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

        Legacy file-backed session data lives under this directory.  Use the
        dedicated getter methods below to access specific sub-paths; avoid
        joining *session_dir* by hand.
        """
        return self.sessions_base_dir(workspace) / session_id

    # ── 记忆配置 ────────────────────────────────────────────────

    @property
    def memory_settings(self) -> MemorySettings:
        """记忆系统配置对象（向量检索等）。"""
        raw = self._raw.get("memory", {})
        if not isinstance(raw, dict):
            raw = {}

        jieba_dict_raw = str(raw.get("jieba_dict", "") or "").strip()
        if jieba_dict_raw:
            p = Path(jieba_dict_raw)
            jieba_dict_resolved = str(p if p.is_absolute() else (_PACKAGE_ROOT / p).resolve())
        else:
            jieba_dict_resolved = ""
        llm_runtime = get_runtime_config()
        return MemorySettings(
            enabled=raw.get("enabled", False),
            embedding_provider=self._memory_llm_provider(MEMORY_EMBED_BIZ_KEY),
            query_planner_provider=self._memory_llm_provider(MEMORY_QUERY_PLANNER_BIZ_KEY),
            rerank_provider=self._memory_llm_provider(MEMORY_RERANK_BIZ_KEY),
            embedding_model_path=self._memory_llama_model_path(MEMORY_EMBED_BIZ_KEY),
            n_ctx=32768,
            n_gpu_layers=0,
            embedding_n_threads=4,
            embedding_verbose=False,
            top_k=raw.get("top_k", 5),
            hybrid_enabled=raw.get("hybrid_enabled", True),
            vector_k=raw.get("vector_k", 50),
            keyword_tokenizer=raw.get("keyword_tokenizer", "jieba"),
            keyword_k=raw.get("keyword_k", 50),
            hybrid_vector_weight=raw.get("hybrid_vector_weight", 0.47),
            hybrid_keyword_weight=raw.get("hybrid_keyword_weight", 0.18),
            hybrid_raw_md_weight=raw.get("hybrid_raw_md_weight", 0.05),
            hybrid_exact_weight=raw.get("hybrid_exact_weight", 0.10),
            hybrid_expanded_weight=raw.get("hybrid_expanded_weight", 0.10),
            hybrid_recency_weight=raw.get("hybrid_recency_weight", 0.05),
            hybrid_granularity_weight=raw.get("hybrid_granularity_weight", 0.05),
            raw_md_mode=raw.get("raw_md_mode", "fallback_only"),
            raw_md_min_results=raw.get("raw_md_min_results", 0),
            rerank_candidate_k=raw.get("rerank_candidate_k", 8),
            rerank_enabled=raw.get("rerank_enabled", False),
            rerank_model_path=self._memory_llama_model_path(MEMORY_RERANK_BIZ_KEY),
            rerank_n_ctx=4096,
            rerank_n_gpu_layers=0,
            rerank_temperature=0.0,
            rerank_score_weight=forgiving_float(raw.get("rerank_score_weight", 0.70), 0.70),
            rerank_verbose=False,
            query_planner_enabled=raw.get("query_planner_enabled", False),
            query_planner_model_path=self._memory_llama_model_path(MEMORY_QUERY_PLANNER_BIZ_KEY),
            query_planner_n_ctx=2048,
            query_planner_n_gpu_layers=0,
            query_planner_temperature=0.0,
            query_planner_max_tokens=512,
            jieba_dict=jieba_dict_resolved,
            llama_process_enabled=llm_runtime.llama_process_enabled,
            llama_request_timeout_ms=llm_runtime.llama_request_timeout_ms,
            llama_startup_timeout_ms=llm_runtime.llama_startup_timeout_ms,
            llama_max_parallel_models=llm_runtime.llama_max_parallel_models,
            chunk_size=raw.get("chunk_size", 2000),
            chunk_overlap=raw.get("chunk_overlap", 64),
        )

    @staticmethod
    def _resolve_package_path(value: ConfigValue) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        path = Path(text)
        if path.is_absolute():
            return str(path)
        return str((_PACKAGE_ROOT / path).resolve())

    @staticmethod
    def _memory_llm_provider(biz_key: str) -> MemorySettings.Provider:
        try:
            cfg = resolve_llm_config(biz_key)
        except ValueError:
            return MemorySettings.Provider()
        provider = cfg.provider if cfg.provider in {"shared", "openai", "llama"} else "llama"
        return MemorySettings.Provider(provider=provider)  # type: ignore[arg-type]

    @staticmethod
    def _memory_llama_model_path(biz_key: str) -> str:
        try:
            cfg = resolve_llm_config(biz_key)
        except ValueError:
            return ""
        return Settings._resolve_package_path(cfg.llama.get("model_path"))

    def get_vector_db_path(self, workspace: str, session_id: str) -> Path:
        """Return the ``memory_vectors.db`` path for the given session."""
        return self.session_dir(workspace, session_id) / "memory_vectors.db"

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
