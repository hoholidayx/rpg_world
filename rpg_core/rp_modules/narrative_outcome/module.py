"""Narrative Outcome RP module composition."""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context import FixedLayerSection, RPModuleRuntimeSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID,
    RP_MODULE_NARRATIVE_OUTCOME_SOURCE,
    RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest, ModuleStatus
from rpg_core.rp_modules.narrative_outcome.tools import (
    NarrativeOutcomeSampler,
    NarrativeOutcomeTool,
)
from rpg_core.settings import NarrativeOutcomeModuleSettings
from rpg_data import models as data_models

if TYPE_CHECKING:
    from rpg_core.agent.transaction import TurnScratch


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
_DICE_EXPRESSION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\d+)?d\d+(?:[+-]\d+)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_ENGLISH_RANDOM_CUE_RE = re.compile(
    r"\b(?:roll|dice|skill\s+check|ability\s+check|saving\s+throw)\b",
    re.IGNORECASE,
)
_NEGATED_ENGLISH_RANDOM_CUE_RE = re.compile(
    r"\b(?:do\s+not|don't|dont|no|without)\s+(?:roll|dice|skill\s+check|ability\s+check)\b",
    re.IGNORECASE,
)

SelectionResolver = Callable[
    [str, data_models.NarrativeOutcomeWeights],
    data_models.NarrativeOutcomeSelection | None,
]


class NarrativeOutcomeModule(RPModule):
    """Choose a five-level story branch without exposing random mechanics."""

    name = RP_MODULE_NARRATIVE_OUTCOME_NAME

    def __init__(
        self,
        *,
        session_id: str,
        settings: NarrativeOutcomeModuleSettings | None = None,
        rng: random.Random | None = None,
        selection_resolver: SelectionResolver | None = None,
    ) -> None:
        self.session_id = session_id
        self.settings = settings or NarrativeOutcomeModuleSettings()
        self._sampler = NarrativeOutcomeSampler(rng)
        self._selection_resolver = selection_resolver
        self._active_scratch: TurnScratch | None = None
        self._tool = NarrativeOutcomeTool(self)

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        if self.settings.auto_adjudication_enabled:
            trigger_rule = (
                "- 每轮叙事前，必须结合用户完整语义、当前场景和状态判断是否存在外部实质变数。"
                "只要同一行动或场景决策存在两个或以上合理结果、结果尚未被上下文唯一确定，"
                "并受未知信息、角色能力、对抗或阻力、风险、时机、环境条件或 NPC/世界反应影响，"
                "且不同结果会实质改变剧情走向、获得的信息、风险或代价，就必须先调用 "
                "rp_story_outcome，再描述结果。\n"
                "- 即使用户没有提到骰子，只要 NPC 是否配合或察觉、事件是否及时发生、线索是否获得、"
                "行动能否奏效等仍存在上述实质分支，也必须裁定。"
            )
        else:
            trigger_rule = (
                "- 自动剧情裁定已关闭。仅当用户明确要求掷骰、检定、随机决定或把结果交给运气时，"
                "必须调用 rp_story_outcome；一般隐式不确定性不自动裁定。"
            )

        return [
            FixedLayerSection(
                id=RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID,
                title="剧情分支随机裁定",
                source=RP_MODULE_NARRATIVE_OUTCOME_SOURCE,
                priority=80,
                content=(
                    "- rp_story_outcome 是自然 RP 中唯一的随机剧情裁定工具。"
                    "不要调用或模拟低层骰子、表达式、DC、修正值、概率或随机数。\n"
                    f"{trigger_rule}\n"
                    "- 用户明确要求掷骰、检定、碰碰运气、看能不能或随机决定外部结果时，"
                    "不得只建议、询问或口头模拟，必须在决定结果前调用 rp_story_outcome。\n"
                    "- 每个 turn 最多裁定一个最关键的外部变数；reason 必须完整描述本次裁定的整体目标边界，"
                    "不得只写其中一个子步骤；actor 仅在明确时填写。\n"
                    "- 工具返回结果后，reason 是不可缩小的整体目标，必须把 outcomeCode 和 "
                    "narrativeGuidance 作为本轮事实；不得为匹配结果等级而改写为局部子目标，"
                    "也不得改判、弱化、重复抽取或向玩家透露内部随机细节。\n"
                    "- 确定会发生的动作、无关紧要的细节、纯角色表达，以及玩家角色的内心、选择或台词"
                    "不裁定。裁定世界后果，不替玩家角色做决定。"
                ),
            )
        ]

    def get_runtime_sections(
        self,
        request: ModuleContextRequest,
    ) -> list[RPModuleRuntimeSection]:
        scratch = self._active_scratch if request.include_staged_turn else None
        staged = getattr(scratch, "narrative_outcome", None)
        if staged is not None:
            public_result = json.dumps(
                staged.to_tool_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            return [
                RPModuleRuntimeSection(
                    id=RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
                    title="本轮已生效的剧情预裁定",
                    source=RP_MODULE_NARRATIVE_OUTCOME_SOURCE,
                    priority=80,
                    content=(
                        "以下剧情裁定结果在本轮首次生成前就已生效：\n"
                        f"{public_result}\n"
                        "必须直接遵循 outcomeCode、label 与 narrativeGuidance 推进叙事；不得改判、"
                        "弱化、重新抽取或先写出相反结果，也不需要再次调用 rp_story_outcome。若仍"
                        "重复调用，该工具只会幂等返回同一结果。\n"
                        "reason 是本次裁定不可缩小的整体目标边界，不得用子步骤代替整体目标。\n"
                        "先在内部确定该结果造成的叙事后果和最终状态。凡实际、持久且已经确定的"
                        "裁定派生变化，必须在输出任何 RP 正文前调用 scene_time、scene_attr、"
                        "scene_del_attr 或 status_table_set_values；工具调用轮不得夹带 RP 正文，"
                        "工具返回后再输出与已同步状态一致的正文。状态同步无需玩家确认，"
                        "不得询问是否需要标记、记录或更新状态。"
                    ),
                )
            ]
        if not self._has_explicit_random_intent(request.user_input):
            return []
        return [
            RPModuleRuntimeSection(
                id=RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID,
                title="本轮剧情裁定指令",
                source=RP_MODULE_NARRATIVE_OUTCOME_SOURCE,
                priority=80,
                content=(
                    "用户本轮已明确把外部结果交给随机裁定。必须在生成结果前调用且只调用 "
                    "rp_story_outcome(reason, actor?)。不要询问表达式、DC、难度或其它参数；"
                    "不要先口头决定结果，也不要为同一 turn 重复抽取。"
                ),
            )
        ]

    def get_tools(self):
        return [self._tool]

    def should_offer_status_preflight(self, user_input: str) -> bool:
        """Respect auto-adjudication while still handling explicit random intent."""
        return (
            self.settings.auto_adjudication_enabled
            or self._has_explicit_random_intent(user_input)
        )

    def status(self) -> ModuleStatus:
        return ModuleStatus(
            name=self.name,
            enabled=self.settings.enabled,
            tools=(self._tool.name,),
            fixed_section_ids=(RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID,),
            config_summary={
                "auto_adjudication_enabled": self.settings.auto_adjudication_enabled,
                "default_weights": self.settings.default_weights.to_dict(),
            },
        )

    def bind_turn(self, scratch: TurnScratch) -> None:
        selection = self._resolve_selection()
        scratch.narrative_outcome_selection = selection
        self._active_scratch = scratch
        logger.debug(
            "[NarrativeOutcome] turn bound: session_id={}, turn_id={}, source={}",
            self.session_id,
            scratch.turn_id,
            selection.effective_source,
        )

    def unbind_turn(self, scratch: TurnScratch) -> None:
        if self._active_scratch is scratch:
            self._active_scratch = None

    def adjudicate(self, *, reason: str, actor: str = ""):
        scratch = self._active_scratch
        if scratch is None or scratch.narrative_outcome_selection is None:
            raise RuntimeError("rp_story_outcome is only available during an active turn")
        if scratch.narrative_outcome is not None:
            logger.info(
                "[NarrativeOutcome] reused staged outcome: session_id={}, turn_id={}, code={}",
                self.session_id,
                scratch.turn_id,
                scratch.narrative_outcome.outcome_code,
            )
            return scratch.narrative_outcome

        staged = self._sampler.select(
            reason=reason,
            actor=actor,
            selection=scratch.narrative_outcome_selection,
        )
        scratch.narrative_outcome = staged
        logger.info(
            "[NarrativeOutcome] staged outcome: session_id={}, turn_id={}, code={}, sample={}, source={}, reason={!r}, actor={!r}",
            self.session_id,
            scratch.turn_id,
            staged.outcome_code,
            staged.sample_value,
            staged.effective_source,
            staged.reason,
            staged.actor,
        )
        return staged

    def _resolve_selection(self) -> data_models.NarrativeOutcomeSelection:
        resolver = self._selection_resolver or self._default_selection_resolver
        selection = resolver(self.session_id, self.settings.default_weights)
        if selection is not None:
            return selection
        return data_models.NarrativeOutcomeSelection(
            config_default=self.settings.default_weights,
            story_weights=None,
            session_weights=None,
            effective_weights=self.settings.default_weights,
            effective_source=data_models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
        )

    @staticmethod
    def _default_selection_resolver(
        session_id: str,
        config_default: data_models.NarrativeOutcomeWeights,
    ) -> data_models.NarrativeOutcomeSelection | None:
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().narrative_outcomes.get_session_selection(
            session_id,
            config_default,
        )

    @staticmethod
    def _has_explicit_random_intent(user_input: str) -> bool:
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
