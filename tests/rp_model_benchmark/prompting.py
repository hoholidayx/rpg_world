"""Build the frozen story-neutral provider prompt for one benchmark case."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rpg_core.context.fixed_layer.assembler import FixedLayerAssembler
from rpg_core.context.fixed_layer.contributors import (
    CoreRPContractContributor,
    PlayerCharacterFixedLayerContributor,
    TextOutputFormatFixedLayerContributor,
)
from rpg_core.context.models import FixedLayerData, RPGContext
from rpg_core.rp_modules.message_mode.module import MessageModeModule
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.rp_modules.narrative_outcome.module import NarrativeOutcomeModule
from rpg_core.settings import NarrativeOutcomeModuleSettings
from tests.rp_model_benchmark.models import BenchmarkToolName, RPBenchmarkCase
from tests.rp_model_benchmark.tools import BenchmarkToolRuntime


@dataclass(frozen=True)
class _SyntheticPlayer:
    character_id: int
    story_id: int
    name: str


def build_round_messages(
    case: RPBenchmarkCase,
    runtime: BenchmarkToolRuntime,
    transcript: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Re-project dynamic Outcome content while keeping a stable fixed prefix."""

    messages: list[dict[str, object]] = [
        {"role": "system", "content": _fixed_content(case)},
        {"role": "system", "content": _case_context(case, runtime)},
    ]
    dynamic = _dynamic_sections(case, runtime)
    if dynamic:
        messages.append({"role": "system", "content": dynamic})
    messages.append({"role": "user", "content": case.user_input})
    messages.extend(transcript)
    return messages


def _fixed_content(case: RPBenchmarkCase) -> str:
    player = _SyntheticPlayer(1, 1, case.player_character)
    fixed = FixedLayerAssembler(
        world_name="当代日常世界",
        contributors=[
            CoreRPContractContributor("当代日常世界"),
            PlayerCharacterFixedLayerContributor(player),
            TextOutputFormatFixedLayerContributor(),
        ],
    ).assemble()
    return RPGContext(fixed_layer=FixedLayerData(
        world_name=fixed.world_name,
        sections=fixed.sections,
    )).render_layer("fixed_layer") or ""


def _case_context(
    case: RPBenchmarkCase,
    runtime: BenchmarkToolRuntime,
) -> str:
    payload = {
        "messageMode": case.mode,
        "playerCharacter": case.player_character,
        "scene": case.scene,
        "characters": [
            item.model_dump(by_alias=True, exclude_none=True)
            for item in case.characters
        ],
        "authoritativeFacts": case.facts,
        "explicitlyUnknownFacts": case.unknown_facts,
        "normalStatusTables": runtime.status.snapshot(),
    }
    return (
        "[runtime_context]\n"
        "以下是当前 turn 完整且权威的世界快照。"
        "不得把未提供的信息补写成确定事实；明确标为未知的内容必须保持未知，除非工具结果决定。\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n[/runtime_context]"
    )


def _dynamic_sections(
    case: RPBenchmarkCase,
    runtime: BenchmarkToolRuntime,
) -> str:
    contents: list[str] = []
    mode_sections = MessageModeModule().get_runtime_sections(
        ModuleContextRequest(
            session_id="rp_model_benchmark",
            user_input=case.user_input,
            message_mode=case.mode,
            player_character_name=case.player_character,
        )
    )
    contents.extend(_render_section(section.id, section.title, section.content) for section in mode_sections)

    if BenchmarkToolName.OUTCOME in case.tools.available:
        if runtime.state.outcome_staged and runtime.state.outcome is not None:
            payload = json.dumps(
                runtime.state.outcome.tool_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            contents.append(_render_section(
                "rp_module_narrative_outcome_turn_directive",
                "本轮最终剧情结果",
                (
                    "本轮裁定已完成，直接执行以下最终结果：\n"
                    f"{payload}\n"
                    "- 必须按 outcomeCode、reason 与 narrativeGuidance 落实完整目标；"
                    "不得改判、弱化、重新抽取或暴露内部随机细节。"
                ),
            ))
        else:
            module = NarrativeOutcomeModule(
                session_id="rp_model_benchmark",
                settings=NarrativeOutcomeModuleSettings(
                    auto_adjudication_enabled=True,
                ),
            )
            sections = module.get_runtime_sections(ModuleContextRequest(
                session_id="rp_model_benchmark",
                user_input=case.user_input,
                message_mode=case.mode,
            ))
            contents.extend(
                _render_section(section.id, section.title, section.content)
                for section in sections
            )
    return "\n\n".join(item for item in contents if item.strip())


def _render_section(section_id: str, title: str, content: str) -> str:
    return f"[{section_id}]\n# {title}\n{content.strip()}\n[/{section_id}]"


__all__ = ["build_round_messages"]
