"""Deterministic turn eligibility for Narrative Outcome adjudication."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from rpg_core.session.modes import TurnMode, normalize_turn_mode


_EXPLICIT_RANDOM_CUES = (
    "掷骰",
    "投骰",
    "扔骰",
    "骰一下",
    "骰个",
    "骰子",
    "检定",
    "碰碰运气",
    "碰运气",
    "试试运气",
    "试试手气",
    "交给运气",
    "看运气",
    "看手气",
    "随机裁定",
    "随机决定",
)
_NEGATED_RANDOM_CUES = (
    "不要掷骰",
    "不用掷骰",
    "别掷骰",
    "无需掷骰",
    "不需要掷骰",
    "不要骰子",
    "不用骰子",
    "不要检定",
    "不用检定",
    "取消检定",
)
_EXPLICIT_UNKNOWN_EXTERNAL_CUES = (
    "结果未知",
    "结果未定",
    "外部结果未定",
    "外部反应未知",
    "外部反应未定",
    "保留结果未知",
    "保留结果未定",
    "不预设结果",
    "不指定结果",
    "不替对方决定",
    "不替她决定",
    "不替他决定",
    "由对方决定",
    "由她决定",
    "由他决定",
    "由其决定",
    "由npc决定",
    "由世界反应决定",
    "由真实组织流程决定",
)
_DETERMINISTIC_FACT_CUES = (
    "已确认事实",
    "确认的事实",
    "既定事实",
    "固定推进",
    "确定推进",
    "直接推进",
    "按以下事实",
    "事实更正",
    "更正刚才",
    "更正为",
    "纠正为",
    "修正为",
    "已经确定",
    "已确定",
    "明确指定",
)
_DICE_EXPRESSION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\d+)?d\d+(?:[+-]\d+)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_ENGLISH_RANDOM_CUE_RE = re.compile(
    r"\b(?:roll|dice|skill\s+check|ability\s+check|saving\s+throw)\b",
    re.IGNORECASE,
)
_NEGATED_ENGLISH_RANDOM_CUE_RE = re.compile(
    r"\b(?:do\s+not|don't|dont|no|without)\s+"
    r"(?:roll|dice|skill\s+check|ability\s+check)\b",
    re.IGNORECASE,
)
_UNKNOWN_EXTERNAL_RE = re.compile(
    r"(?:让|由)(?:[^，。！？\n]{0,24})(?:自行|自己|当下)?决定(?:是否|会不会|结果)"
    r"|(?:是否|会不会)(?:[^，。！？\n]{0,24})(?:由|取决于)"
    r"(?:[^，。！？\n]{0,24})(?:反应|流程|判断|选择|决定)",
    re.IGNORECASE,
)
_ENGLISH_UNKNOWN_EXTERNAL_RE = re.compile(
    r"\b(?:leave|keep)\s+(?:the\s+)?(?:outcome|reaction)\s+"
    r"(?:unknown|open|undecided)\b"
    r"|\b(?:let|allow)\s+[^.!?\n]{0,40}\s+decide\s+(?:whether|if)\b",
    re.IGNORECASE,
)


class NarrativeOutcomeEligibilityReason(StrEnum):
    """Why the deterministic gate did or did not expose adjudication."""

    EXPLICIT_RANDOM = "explicit_random"
    EXPLICIT_UNKNOWN_EXTERNAL = "explicit_unknown_external"
    DETERMINISTIC_FACT = "deterministic_fact"
    AUTO_ADJUDICATION = "auto_adjudication"
    GM_DEFAULT = "gm_default"
    OOC_MODE = "ooc_mode"
    AUTO_DISABLED = "auto_disabled"


@dataclass(frozen=True)
class NarrativeOutcomeEligibility:
    """Permission to ask an LLM to decide whether this turn needs Outcome.

    ``eligible`` does not mean an Outcome is required.  In automatic modes it
    only permits the StatusSubAgent or main Agent to inspect genuine external
    uncertainty.  Deterministic GM authority and fact corrections are filtered
    before any Outcome-capable provider request is made.
    """

    eligible: bool
    reason: NarrativeOutcomeEligibilityReason
    explicit_random: bool = False
    explicit_unknown_external: bool = False


def resolve_narrative_outcome_eligibility(
    user_input: str,
    *,
    message_mode: TurnMode | str = TurnMode.NEUTRAL,
    auto_adjudication_enabled: bool,
) -> NarrativeOutcomeEligibility:
    """Resolve one shared, deterministic eligibility decision for a turn."""

    mode = normalize_turn_mode(message_mode)
    if mode is TurnMode.OOC:
        return NarrativeOutcomeEligibility(
            eligible=False,
            reason=NarrativeOutcomeEligibilityReason.OOC_MODE,
        )

    explicit_random = has_explicit_random_intent(user_input)
    explicit_unknown = has_explicit_unknown_external_intent(user_input)
    # Explicit uncertainty is stronger than nearby fact/correction wording.
    if explicit_random:
        return NarrativeOutcomeEligibility(
            eligible=True,
            reason=NarrativeOutcomeEligibilityReason.EXPLICIT_RANDOM,
            explicit_random=True,
            explicit_unknown_external=explicit_unknown,
        )
    if explicit_unknown:
        return NarrativeOutcomeEligibility(
            eligible=True,
            reason=NarrativeOutcomeEligibilityReason.EXPLICIT_UNKNOWN_EXTERNAL,
            explicit_unknown_external=True,
        )
    if has_deterministic_fact_intent(user_input):
        return NarrativeOutcomeEligibility(
            eligible=False,
            reason=NarrativeOutcomeEligibilityReason.DETERMINISTIC_FACT,
        )
    if mode is TurnMode.GM:
        return NarrativeOutcomeEligibility(
            eligible=False,
            reason=NarrativeOutcomeEligibilityReason.GM_DEFAULT,
        )
    if auto_adjudication_enabled:
        return NarrativeOutcomeEligibility(
            eligible=True,
            reason=NarrativeOutcomeEligibilityReason.AUTO_ADJUDICATION,
        )
    return NarrativeOutcomeEligibility(
        eligible=False,
        reason=NarrativeOutcomeEligibilityReason.AUTO_DISABLED,
    )


def has_explicit_random_intent(user_input: str) -> bool:
    text = str(user_input or "").strip()
    if not text:
        return False
    compact = re.sub(r"\s+", "", text).casefold()
    if any(cue in compact for cue in _NEGATED_RANDOM_CUES):
        return False
    if _NEGATED_ENGLISH_RANDOM_CUE_RE.search(text):
        return False
    if any(cue in compact for cue in _EXPLICIT_RANDOM_CUES):
        return True
    return bool(
        _DICE_EXPRESSION_RE.search(text)
        or _ENGLISH_RANDOM_CUE_RE.search(text)
    )


def has_explicit_unknown_external_intent(user_input: str) -> bool:
    text = str(user_input or "").strip()
    if not text:
        return False
    compact = re.sub(r"\s+", "", text).casefold()
    return bool(
        any(cue in compact for cue in _EXPLICIT_UNKNOWN_EXTERNAL_CUES)
        or _UNKNOWN_EXTERNAL_RE.search(text)
        or _ENGLISH_UNKNOWN_EXTERNAL_RE.search(text)
    )


def has_deterministic_fact_intent(user_input: str) -> bool:
    text = str(user_input or "").strip()
    if not text:
        return False
    compact = re.sub(r"\s+", "", text).casefold()
    return any(cue in compact for cue in _DETERMINISTIC_FACT_CUES)


__all__ = [
    "NarrativeOutcomeEligibility",
    "NarrativeOutcomeEligibilityReason",
    "has_deterministic_fact_intent",
    "has_explicit_random_intent",
    "has_explicit_unknown_external_intent",
    "resolve_narrative_outcome_eligibility",
]
