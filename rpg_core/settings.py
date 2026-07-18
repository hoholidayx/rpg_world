"""RPG World core business settings.

Settings are read from ``rpg_core/settings.yaml`` once at process startup and
are **read-only** thereafter.  The active profile is selected through
``RPG_WORLD_PROFILE`` before the Python process starts; it defaults to
``local``.

Session runtime file paths are owned by ``rpg_data.catalog``.  Core settings
only expose business/config values; code that needs a session directory must
ask ``CatalogService.get_session_runtime_dir(session_id)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from commons.settings import (
    PROFILE_ENV,
    ProfiledYamlSettings,
    forgiving_float,
    forgiving_int,
)
from commons.types import ConfigDict
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
)
from rpg_core.utils.path_utils import PACKAGE_ROOT as _PACKAGE_ROOT
from rpg_data.models import NarrativeOutcomeWeights

# Location of rpg_core process/business settings.
_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
_RPG_CORE_DIR = Path(__file__).resolve().parent
_PROFILE_ENV = PROFILE_ENV

@dataclass
class MemorySettings:
    """记忆系统配置（对应 settings.yaml 中 ``memory`` 节）。"""

    enabled: bool = False
    """是否启用向量记忆索引与检索。"""

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

    query_planner_enabled: bool = False
    """是否启用本地 llama.cpp 查询规划器。"""

    jieba_dict: str = ""
    """jieba 用户词典路径（相对于项目根目录），留空使用默认词典。"""

    chunk_size: int = 2000
    """单文件超过此字符数时分块。"""

    chunk_overlap: int = 64
    """分块重叠字符数。"""


@dataclass(frozen=True)
class CoreLoggingSettings:
    """Core and memory-side logging settings."""

    log_level: str = "DEBUG"


@dataclass(frozen=True)
class SceneSettings:
    """LLM-facing scene mutation policy."""

    allow_runtime_key_changes: bool = False


@dataclass(frozen=True)
class StatusSubAgentSettings:
    """Status history-window policy shared by turns and derivation bootstrap."""

    history_rounds: int = 5


@dataclass(frozen=True)
class MemoryStorySettings:
    """Story-memory extraction policy."""

    trigger_rounds: int = 0
    max_items: int = 8
    batch_turns: int = 10
    max_batch_chars: int = 32_000


@dataclass(frozen=True)
class MemorySummarySettings:
    """Summary compression policy."""

    compress_batch_size: int = 10
    keep_rounds: int = 5
    compression_enabled: bool = True
    max_batch_chars: int = 32_000


@dataclass(frozen=True)
class DiceModuleSettings:
    """Dice RP module settings."""

    enabled: bool = True
    default_dc: int = 12
    max_dice_count: int = 100
    max_die_sides: int = 1000


@dataclass(frozen=True)
class NarrativeOutcomeModuleSettings:
    """High-level narrative branch adjudication settings."""

    enabled: bool = True
    auto_adjudication_enabled: bool = True
    default_weights: NarrativeOutcomeWeights = field(
        default_factory=NarrativeOutcomeWeights
    )


@dataclass(frozen=True)
class RPModuleSettings:
    """RP Modules business settings."""

    enabled: bool = True
    dice: DiceModuleSettings = field(default_factory=DiceModuleSettings)
    narrative_outcome: NarrativeOutcomeModuleSettings = field(
        default_factory=NarrativeOutcomeModuleSettings
    )


class Settings(ProfiledYamlSettings):
    """Read-only settings proxy. Attributes mirror merged core settings."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "rpg_core/settings.yaml"
        self.env_var = _PROFILE_ENV
        super().__init__()
        self._validate_settings()

    @property
    def agent_settings(self) -> ConfigDict:
        raw = self._raw.get("agent", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def logging(self) -> CoreLoggingSettings:
        raw = self._mapping("logging")
        return CoreLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
        )

    @property
    def scene_settings(self) -> SceneSettings:
        raw = self.agent_settings.get("scene", {})
        if not isinstance(raw, dict):
            raise ValueError("agent.scene must be a mapping")
        allow_runtime_key_changes = raw.get("allow_runtime_key_changes", False)
        if not isinstance(allow_runtime_key_changes, bool):
            raise ValueError(
                "agent.scene.allow_runtime_key_changes must be a boolean"
            )
        return SceneSettings(
            allow_runtime_key_changes=allow_runtime_key_changes,
        )

    @property
    def rp_module_settings(self) -> RPModuleSettings:
        """RP Modules typed settings."""
        raw = self._mapping("rp_modules")
        modules = raw.get("modules", {})
        if not isinstance(modules, dict):
            modules = {}
        dice_raw = modules.get(RP_MODULE_DICE_NAME, {})
        if not isinstance(dice_raw, dict):
            dice_raw = {}
        narrative_raw = modules.get(RP_MODULE_NARRATIVE_OUTCOME_NAME, {})
        if not isinstance(narrative_raw, dict):
            narrative_raw = {}

        default_weights_raw = narrative_raw.get("default_weights")
        if default_weights_raw is None:
            default_weights = NarrativeOutcomeWeights()
        elif isinstance(default_weights_raw, dict):
            default_weights = NarrativeOutcomeWeights.from_mapping(default_weights_raw)
        else:
            raise ValueError(
                "rp_modules.modules.narrative_outcome.default_weights must be a mapping"
            )

        if "allow_auto_checks" in dice_raw:
            raise ValueError(
                "rp_modules.modules.dice.allow_auto_checks is no longer supported; "
                "configure narrative_outcome.auto_adjudication_enabled instead"
            )

        return RPModuleSettings(
            enabled=bool(raw.get("enabled", True)),
            dice=DiceModuleSettings(
                enabled=bool(dice_raw.get("enabled", True)),
                default_dc=int(dice_raw.get("default_dc", 12)),
                max_dice_count=int(dice_raw.get("max_dice_count", 100)),
                max_die_sides=int(dice_raw.get("max_die_sides", 1000)),
            ),
            narrative_outcome=NarrativeOutcomeModuleSettings(
                enabled=bool(narrative_raw.get("enabled", True)),
                auto_adjudication_enabled=bool(
                    narrative_raw.get("auto_adjudication_enabled", True)
                ),
                default_weights=default_weights,
            ),
        )

    def _validate_settings(self) -> None:
        self._validate_context_window_reject_threshold()
        self._validate_status_sub_agent_settings()
        # Materialize memory settings so malformed batch limits fail at startup.
        self.memory_story_settings
        self.memory_summary_settings
        # Materialize the typed scene policy so malformed permissions fail at
        # startup rather than changing tool exposure during a turn.
        self.scene_settings
        # Materialize typed RP module settings at startup so malformed weight
        # distributions fail fast instead of surfacing during a player turn.
        self.rp_module_settings

    def _validate_context_window_reject_threshold(self) -> None:
        value = self.context_window_reject_threshold_ratio
        if not 0 < value <= 1:
            raise ValueError(
                "agent.context_window_reject_threshold_ratio must be within (0, 1]"
            )

    def _validate_status_sub_agent_settings(self) -> None:
        _ = self.status_sub_agent_settings
        _ = self.status_deferred_default_interval_turns

    @property
    def jinja_dir(self) -> Path:
        """Path to the Jinja template directory (rpg_core/jinja/)."""
        return _RPG_CORE_DIR / "jinja"

    @property
    def verbose_logging(self) -> bool:
        return self.agent_settings.get("verbose_logging", False)

    @property
    def context_window_reject_threshold_ratio(self) -> float:
        value = self.agent_settings.get("context_window_reject_threshold_ratio", 0.9)
        if isinstance(value, bool):
            raise ValueError(
                "agent.context_window_reject_threshold_ratio must be a number"
            )
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "agent.context_window_reject_threshold_ratio must be a number"
            ) from exc

    @property
    def memory_sub_agent_config(self) -> ConfigDict:
        """memory_sub_agent 完整配置 dict。

        ``llm_provider`` 与 ``shared/openai/llama`` 控制子 Agent LLM 来源；
        ``summary/story`` 是记忆管线配置，不属于 provider 配置。
        """
        return self.agent_settings.get("memory_sub_agent", {})

    # ── memory_sub_agent 管线级配置 ────────────────────────────────

    @property
    def memory_summary_config(self) -> ConfigDict:
        """summary 管线配置：compress_rounds / keep_rounds。"""
        return self.memory_sub_agent_config.get("summary", {})

    @property
    def memory_story_config(self) -> ConfigDict:
        """story 管线配置：trigger_rounds / max_items。"""
        return self.memory_sub_agent_config.get("story", {})

    @property
    def memory_story_settings(self) -> MemoryStorySettings:
        """Typed story-memory extraction settings."""
        raw = self.memory_story_config
        if not isinstance(raw, dict):
            raise ValueError("agent.memory_sub_agent.story must be a mapping")

        trigger_rounds = raw.get("trigger_rounds", 0)
        max_items = raw.get("max_items", 8)
        batch_turns = raw.get("batch_turns", 10)
        max_batch_chars = raw.get("max_batch_chars", 32_000)
        for key, value, allow_zero in (
            ("trigger_rounds", trigger_rounds, True),
            ("max_items", max_items, False),
            ("batch_turns", batch_turns, False),
            ("max_batch_chars", max_batch_chars, False),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (0 if allow_zero else 1)
            ):
                qualifier = "a non-negative" if allow_zero else "a positive"
                raise ValueError(
                    f"agent.memory_sub_agent.story.{key} must be {qualifier} integer"
                )
        return MemoryStorySettings(
            trigger_rounds=trigger_rounds,
            max_items=max_items,
            batch_turns=batch_turns,
            max_batch_chars=max_batch_chars,
        )

    @property
    def memory_summary_settings(self) -> MemorySummarySettings:
        """Typed summary compression settings."""
        raw = self.memory_summary_config
        if not isinstance(raw, dict):
            raise ValueError("agent.memory_sub_agent.summary must be a mapping")

        compress_batch_size = raw.get("compress_batch_size", 10)
        keep_rounds = raw.get("keep_rounds", 5)
        compression_enabled = raw.get("compression_enabled", True)
        max_batch_chars = raw.get("max_batch_chars", 32_000)
        for key, value, allow_zero in (
            ("compress_batch_size", compress_batch_size, False),
            ("keep_rounds", keep_rounds, True),
            ("max_batch_chars", max_batch_chars, False),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (0 if allow_zero else 1)
            ):
                qualifier = "a non-negative" if allow_zero else "a positive"
                raise ValueError(
                    f"agent.memory_sub_agent.summary.{key} must be {qualifier} integer"
                )
        if not isinstance(compression_enabled, bool):
            raise ValueError(
                "agent.memory_sub_agent.summary.compression_enabled must be a boolean"
            )
        return MemorySummarySettings(
            compress_batch_size=compress_batch_size,
            keep_rounds=keep_rounds,
            compression_enabled=compression_enabled,
            max_batch_chars=max_batch_chars,
        )

    @property
    def memory_story_trigger_rounds(self) -> int:
        """N 轮新对话后自动触发剧情记忆提取，0 表示关闭。"""
        return self.memory_story_settings.trigger_rounds

    @property
    def memory_story_max_items(self) -> int:
        """单次剧情记忆提取允许持久化的最大条数。"""
        return self.memory_story_settings.max_items

    @property
    def memory_story_batch_turns(self) -> int:
        """Maximum number of logical turns in one story-memory LLM batch."""
        return self.memory_story_settings.batch_turns

    @property
    def memory_story_max_batch_chars(self) -> int:
        """Maximum message-body characters in one story-memory LLM batch."""
        return self.memory_story_settings.max_batch_chars

    @property
    def memory_compress_batch_size(self) -> int:
        """每批压缩的用户轮次数。"""
        return self.memory_summary_settings.compress_batch_size

    @property
    def memory_keep_rounds(self) -> int:
        """压缩后保留的最近对话轮数。"""
        return self.memory_summary_settings.keep_rounds

    @property
    def memory_compression_enabled(self) -> bool:
        """是否启用自动压缩。"""
        return self.memory_summary_settings.compression_enabled

    @property
    def memory_summary_max_batch_chars(self) -> int:
        """Maximum message-body characters in one summary LLM batch."""
        return self.memory_summary_settings.max_batch_chars

    @property
    def status_sub_agent_config(self) -> ConfigDict:
        """status_sub_agent 完整配置 dict，包含显式 LLM provider 选择。"""
        return self.agent_settings.get("status_sub_agent", {})

    @property
    def status_sub_agent_settings(self) -> StatusSubAgentSettings:
        raw = self.status_sub_agent_config
        if not isinstance(raw, dict):
            raise ValueError("agent.status_sub_agent must be a mapping")
        history_rounds = raw.get("history_rounds", 5)
        if (
            isinstance(history_rounds, bool)
            or not isinstance(history_rounds, int)
            or history_rounds <= 0
        ):
            raise ValueError(
                "agent.status_sub_agent.history_rounds must be a positive integer"
            )
        return StatusSubAgentSettings(history_rounds=history_rounds)

    @property
    def status_history_rounds(self) -> int:
        return self.status_sub_agent_settings.history_rounds

    @property
    def status_deferred_default_interval_turns(self) -> int:
        deferred = self.status_sub_agent_config.get("deferred", {})
        if not isinstance(deferred, dict):
            raise ValueError("agent.status_sub_agent.deferred must be a mapping")
        value = deferred.get("default_interval_turns", 5)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "agent.status_sub_agent.deferred.default_interval_turns "
                "must be a positive integer"
            )
        return value

    @property
    def max_tool_calls(self) -> int:
        return self.agent_settings.get("max_tool_call_limit", 10)

    @property
    def include_tool_records(self) -> bool:
        return self.agent_settings.get("include_tool_records", True)

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    # Workspace discovery and runtime path resolution are rpg_data catalog
    # concerns. Core settings must not discover workspace directories.

    # set_active_workspace() has been removed.  Workspace is no longer
    # a mutable server-wide state — every API call / agent instance
    # explicitly passes the workspace it operates on.

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
        return MemorySettings(
            enabled=raw.get("enabled", False),
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
            rerank_score_weight=forgiving_float(raw.get("rerank_score_weight", 0.70), 0.70),
            query_planner_enabled=raw.get("query_planner_enabled", False),
            jieba_dict=jieba_dict_resolved,
            chunk_size=raw.get("chunk_size", 2000),
            chunk_overlap=raw.get("chunk_overlap", 64),
        )

# Singleton
settings = Settings()
