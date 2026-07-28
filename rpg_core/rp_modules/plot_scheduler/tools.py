"""OOC/GM tools for inspecting and staging manual Plot injections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.rp_modules.plot_scheduler.diagnostics import (
    PlotEventBindingDiagnostic,
    PlotPoolCooldownDiagnostic,
    evaluate_event_bindings,
    evaluate_pool_cooldowns,
)
from rpg_core.tooling.base import BaseTool
from rpg_data import models as data_models

if TYPE_CHECKING:
    from rpg_core.agent.turn.transaction import TurnScratch
    from rpg_core.rp_modules.plot_scheduler.models import PlotScheduleSnapshot

PLOT_SANDBOX_READ_TOOL_NAME = "plot_sandbox_read"
PLOT_EVENT_MARK_NEXT_TOOL_NAME = "plot_event_mark_next"
PLOT_SANDBOX_PAGE_DEFAULT = 20
PLOT_SANDBOX_PAGE_MAX = 50

_UNSET = object()


class _PlotSandboxTool(BaseTool):
    def render_invalid_arguments_error(self, message: str) -> str:
        return _json_error("invalid_arguments", message)


class PlotSandboxReadTool(_PlotSandboxTool):
    name = PLOT_SANDBOX_READ_TOOL_NAME
    description = (
        "读取当前 Session 所属 Story 的剧情沙盘定义。可列出或读取事件池、事件、"
        "剧情大纲及节点，也可查看下一次非 OOC turn 的待注入事件快照。"
        "事件池视图会显示池级冷却及跳过原因；事件视图会显示是否已绑定大纲、"
        "是否仍可进入自动池候选。这是只读工具，不会修改任何剧情定义或运行态。"
    )

    def __init__(
        self,
        snapshot: "PlotScheduleSnapshot",
        scratch: "TurnScratch",
    ) -> None:
        self._snapshot = snapshot
        self._scratch = scratch

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "enum": ["schedule", "pool", "event", "outline"],
                },
                "id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "省略时列举该类资源，传入时读取单项详情。",
                },
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": PLOT_SANDBOX_PAGE_MAX,
                    "default": PLOT_SANDBOX_PAGE_DEFAULT,
                },
            },
            "required": ["resource"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        resource: object = None,
        id: object = None,  # noqa: A002
        offset: object = 0,
        limit: object = PLOT_SANDBOX_PAGE_DEFAULT,
        **unexpected: object,
    ) -> str:
        try:
            if unexpected:
                raise ValueError("包含不支持的参数")
            kind = _resource(resource)
            item_id = _optional_positive_int(id, "id")
            page_offset = _non_negative_int(offset, "offset")
            page_limit = _page_limit(limit)
            payload = self._read(kind, item_id, page_offset, page_limit)
            return _json({"ok": True, **payload})
        except FileNotFoundError as exc:
            return _json_error("not_found", str(exc))
        except (TypeError, ValueError) as exc:
            return _json_error("invalid_arguments", str(exc))

    def _read(
        self,
        resource: str,
        item_id: int | None,
        offset: int,
        limit: int,
    ) -> dict[str, object]:
        story = self._snapshot.story
        scene_time = (
            self._scratch.scene_tracker.get_scene_time()
            if self._scratch.scene_tracker is not None
            else None
        )
        scene_time_error = (
            self._scratch.scene_tracker.scene_time_error
            if self._scratch.scene_tracker is not None
            else "当前 Session 没有 Scene 状态表"
        )
        cooldowns = {
            item.pool_id: item
            for item in evaluate_pool_cooldowns(
                story.pools,
                self._snapshot.decisions,
                scene_time=scene_time,
            )
        }
        bindings = {
            item.event_id: item
            for item in evaluate_event_bindings(story)
        }
        if resource == "schedule":
            if item_id is not None:
                raise ValueError("schedule 不接受 id")
            outline_bound_count = sum(
                item.outline_bound for item in bindings.values()
            )
            return {
                "resource": resource,
                "view": "summary",
                "storyId": story.story_id,
                "sceneTime": _time_payload(scene_time),
                "sceneTimeError": "" if scene_time is not None else scene_time_error,
                "counts": {
                    "pools": len(story.pools),
                    "events": len(story.events),
                    "outlines": len(story.outlines),
                    "nodes": sum(len(item.nodes) for item in story.outlines),
                    "outlineBoundEvents": outline_bound_count,
                    "poolLaneEligibleEvents": len(story.events)
                    - outline_bound_count,
                },
                "poolCooldowns": [
                    _pool_cooldown_payload(cooldowns[pool.id])
                    for pool in sorted(
                        story.pools,
                        key=lambda item: (-item.priority, item.id),
                    )
                ],
                "disabledEventIds": sorted(
                    self._snapshot.overrides.disabled_event_ids
                ),
                "disabledOutlineNodeIds": sorted(
                    self._snapshot.overrides.disabled_outline_node_ids
                ),
                "pendingInjection": _pending_payload(self._effective_pending()),
            }
        if resource == "pool":
            values = sorted(story.pools, key=lambda item: (-item.priority, item.id))
            if item_id is None:
                page, info = _page(values, offset, limit)
                return {
                    "resource": resource,
                    "view": "list",
                    "items": [
                        _pool_summary(
                            item,
                            cooldown=cooldowns[item.id],
                            events=story.events,
                            bindings=bindings,
                        )
                        for item in page
                    ],
                    "page": info,
                }
            pool = next((item for item in values if item.id == item_id), None)
            if pool is None:
                raise FileNotFoundError(f"当前 Story 中不存在事件池：{item_id}")
            events = sorted(
                (item for item in story.events if item.pool_id == pool.id),
                key=lambda item: (item.position, item.id),
            )
            page, info = _page(events, offset, limit)
            return {
                "resource": resource,
                "view": "detail",
                "item": {
                    **_pool_summary(
                        pool,
                        cooldown=cooldowns[pool.id],
                        events=story.events,
                        bindings=bindings,
                    ),
                    "description": pool.description,
                    "version": pool.version,
                    "events": [
                        _event_summary(
                            item,
                            binding=bindings[item.id],
                        )
                        for item in page
                    ],
                    "eventPage": info,
                },
            }
        if resource == "event":
            values = sorted(
                story.events,
                key=lambda item: (item.pool_id, item.position, item.id),
            )
            if item_id is None:
                page, info = _page(values, offset, limit)
                return {
                    "resource": resource,
                    "view": "list",
                    "items": [
                        _event_summary(
                            item,
                            binding=bindings[item.id],
                        )
                        for item in page
                    ],
                    "page": info,
                }
            event = next((item for item in values if item.id == item_id), None)
            if event is None:
                raise FileNotFoundError(f"当前 Story 中不存在事件：{item_id}")
            refs = [
                {
                    "outlineId": outline.id,
                    "outlineName": outline.name,
                    "nodeId": node.id,
                    "position": node.position,
                    "enabled": node.enabled,
                    "scheduledTime": _time_payload(node.scheduled_time),
                    "dispatchMode": node.dispatch_mode,
                }
                for outline in sorted(
                    story.outlines,
                    key=lambda item: (-item.priority, item.id),
                )
                for node in sorted(
                    outline.nodes,
                    key=lambda item: (item.position, item.id),
                )
                if node.event_id == event.id
            ]
            page, info = _page(refs, offset, limit)
            pool = next(
                (item for item in story.pools if item.id == event.pool_id),
                None,
            )
            return {
                "resource": resource,
                "view": "detail",
                "item": {
                    **_event_detail(
                        event,
                        binding=bindings[event.id],
                    ),
                    "pool": (
                        _pool_summary(
                            pool,
                            cooldown=cooldowns[pool.id],
                            events=story.events,
                            bindings=bindings,
                        )
                        if pool is not None
                        else None
                    ),
                    "outlineNodeRefs": page,
                    "outlineNodeRefPage": info,
                    "pendingForNextNonOocTurn": (
                        _pending_event_id(self._effective_pending()) == event.id
                    ),
                },
            }
        values = sorted(
            story.outlines,
            key=lambda item: (-item.priority, item.id),
        )
        if item_id is None:
            page, info = _page(values, offset, limit)
            return {
                "resource": resource,
                "view": "list",
                "items": [_outline_summary(item) for item in page],
                "page": info,
            }
        outline = next((item for item in values if item.id == item_id), None)
        if outline is None:
            raise FileNotFoundError(f"当前 Story 中不存在剧情大纲：{item_id}")
        events = {item.id: item for item in story.events}
        nodes = sorted(outline.nodes, key=lambda item: (item.position, item.id))
        page, info = _page(nodes, offset, limit)
        return {
            "resource": resource,
            "view": "detail",
            "item": {
                **_outline_summary(outline),
                "description": outline.description,
                "version": outline.version,
                "nodes": [
                    {
                        "id": node.id,
                        "eventId": node.event_id,
                        "eventTitle": (
                            events[node.event_id].title
                            if node.event_id in events
                            else ""
                        ),
                        "scheduledTime": _time_payload(node.scheduled_time),
                        "dispatchMode": node.dispatch_mode,
                        "position": node.position,
                        "enabled": node.enabled,
                        "sessionDisabled": (
                            node.id
                            in self._snapshot.overrides.disabled_outline_node_ids
                        ),
                    }
                    for node in page
                ],
                "nodePage": info,
            },
        }

    def _effective_pending(self) -> object | None:
        state = self._scratch.plot_pending_injection
        return state.effective if state is not None else None


class PlotEventMarkNextTool(_PlotSandboxTool):
    name = PLOT_EVENT_MARK_NEXT_TOOL_NAME
    description = (
        "标记当前 Story 的一个事件，在下一次非 OOC turn 强制注入。可用临时 title "
        "和 directive 覆盖一次性快照，不会修改原事件；手动注入忽略自动调度的"
        "Scene 机会、SceneTime、启用、时间窗、大纲绑定、重复和冷却规则。"
        "即使没有 SceneTime，也会解除目标事件已有的事件级冷却锚点；它不会"
        "启动、刷新或清除事件池级冷却锚点。event_id 传 null 可清空标记。"
    )

    def __init__(
        self,
        snapshot: "PlotScheduleSnapshot",
        scratch: "TurnScratch",
    ) -> None:
        self._snapshot = snapshot
        self._scratch = scratch

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "event_id": {
                    "anyOf": [
                        {"type": "integer", "minimum": 1},
                        {"type": "null"},
                    ],
                    "description": "正整数标记事件；null 清空当前标记。",
                },
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "description": "可选的一次性事件标题；省略则冻结原标题。",
                },
                "directive": {
                    "type": "string",
                    "minLength": 1,
                    "description": "可选的一次性剧情指令；省略则冻结原 directive。",
                },
            },
            "required": ["event_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        event_id: object = _UNSET,
        title: object = _UNSET,
        directive: object = _UNSET,
        **unexpected: object,
    ) -> str:
        try:
            if unexpected:
                raise ValueError("包含不支持的参数")
            if event_id is _UNSET:
                raise ValueError("event_id 为必填参数")
            state = self._scratch.plot_pending_injection
            if state is None:
                raise RuntimeError("当前 turn 缺少待注入事件状态")
            previous = state.effective
            if event_id is None:
                if title is not _UNSET or directive is not _UNSET:
                    raise ValueError(
                        "event_id 为 null 时不得同时传入 title 或 directive"
                    )
                state.clear()
                return _json({
                    "ok": True,
                    "changed": previous is not None,
                    "pendingForNextNonOocTurn": False,
                    "pendingInjection": None,
                    "replacedOrCleared": _pending_payload(previous),
                })

            normalized_event_id = _positive_int(event_id, "event_id")
            event = next(
                (
                    item
                    for item in self._snapshot.story.events
                    if item.id == normalized_event_id
                ),
                None,
            )
            if event is None:
                raise FileNotFoundError(
                    f"当前 Story 中不存在事件：{normalized_event_id}"
                )
            pool = next(
                (
                    item
                    for item in self._snapshot.story.pools
                    if item.id == event.pool_id
                ),
                None,
            )
            if pool is None:
                raise FileNotFoundError(
                    f"事件所属事件池不存在：{event.pool_id}"
                )
            frozen_title = (
                event.title
                if title is _UNSET
                else _non_empty_text(title, "title")
            )
            frozen_directive = (
                event.directive
                if directive is _UNSET
                else _non_empty_text(directive, "directive")
            )
            binding = next(
                (
                    item
                    for item in evaluate_event_bindings(self._snapshot.story)
                    if item.event_id == event.id
                ),
                None,
            )
            event_snapshot = _event_detail(event, binding=binding)
            event_snapshot.update({
                "sourcePoolId": pool.id,
                "sourcePoolName": pool.name,
                "originalEventTitle": event.title,
                "originalDirective": event.directive,
                "eventTitle": frozen_title,
                "directive": frozen_directive,
            })
            desired = data_models.PendingPlotInjectionWrite(
                story_id=self._snapshot.story_id,
                source_event_id=event.id,
                source_event_version=event.version,
                source_pool_id=pool.id,
                source_pool_name=pool.name,
                event_title=frozen_title,
                directive=frozen_directive,
                event_snapshot=event_snapshot,
                requested_turn_id=self._scratch.turn_id,
            )
            state.mark(desired)
            return _json({
                "ok": True,
                "changed": True,
                "pendingForNextNonOocTurn": True,
                "pendingInjection": _pending_payload(desired),
                "replacedOrCleared": _pending_payload(previous),
            })
        except FileNotFoundError as exc:
            return _json_error("not_found", str(exc))
        except (TypeError, ValueError) as exc:
            return _json_error("invalid_arguments", str(exc))
        except Exception as exc:
            logger.opt(exception=exc).error(
                "[PlotEventMarkNextTool] failed to stage pending Plot injection"
            )
            return _json_error(
                "internal_error",
                "待注入事件标记失败，请稍后重试",
            )


class PlotSandboxToolProvider:
    def get_tools(
        self,
        snapshot: "PlotScheduleSnapshot",
        scratch: "TurnScratch",
    ) -> list[BaseTool]:
        return [
            PlotSandboxReadTool(snapshot, scratch),
            PlotEventMarkNextTool(snapshot, scratch),
        ]


def _resource(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("resource 必须是字符串")
    normalized = value.strip().lower()
    if normalized not in {"schedule", "pool", "event", "outline"}:
        raise ValueError(f"不支持的 resource：{normalized}")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypeError(f"{label} 必须是正整数")
    return value


def _optional_positive_int(value: object, label: str) -> int | None:
    return None if value is None else _positive_int(value, label)


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{label} 必须是非负整数")
    return value


def _page_limit(value: object) -> int:
    parsed = _positive_int(value, "limit")
    if parsed > PLOT_SANDBOX_PAGE_MAX:
        raise ValueError(f"limit 不能超过 {PLOT_SANDBOX_PAGE_MAX}")
    return parsed


def _non_empty_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} 必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} 不能为空")
    return normalized


def _page(values, offset: int, limit: int):  # noqa: ANN001, ANN201
    items = list(values)
    page = items[offset : offset + limit]
    return page, {
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "hasMore": offset + len(page) < len(items),
    }


def _pool_summary(  # noqa: ANN001
    value,
    *,
    cooldown: PlotPoolCooldownDiagnostic,
    events,
    bindings: dict[int, PlotEventBindingDiagnostic],
) -> dict[str, object]:
    pool_events = [event for event in events if event.pool_id == value.id]
    outline_bound_count = sum(
        bindings[event.id].outline_bound
        for event in pool_events
    )
    return {
        "id": value.id,
        "storyId": value.story_id,
        "name": value.name,
        "selectionMode": value.selection_mode,
        "priority": value.priority,
        "cooldownMinutes": value.cooldown_minutes,
        "enabled": value.enabled,
        "eventCount": len(pool_events),
        "outlineBoundEventCount": outline_bound_count,
        "poolLaneEligibleEventCount": len(pool_events) - outline_bound_count,
        "cooldown": _pool_cooldown_payload(cooldown),
    }


def _event_summary(  # noqa: ANN001
    value,
    *,
    binding: PlotEventBindingDiagnostic | None,
) -> dict[str, object]:
    payload = {
        "id": value.id,
        "storyId": value.story_id,
        "poolId": value.pool_id,
        "title": value.title,
        "position": value.position,
        "dispatchMode": value.dispatch_mode,
        "enabled": value.enabled,
    }
    if binding is not None:
        payload.update({
            "outlineBound": binding.outline_bound,
            "outlineNodeReferenceCount": (
                binding.outline_node_reference_count
            ),
            "poolLaneEligibleByBinding": (
                binding.pool_lane_eligible_by_binding
            ),
        })
    return payload


def _event_detail(  # noqa: ANN001
    value,
    *,
    binding: PlotEventBindingDiagnostic | None = None,
) -> dict[str, object]:
    return {
        **_event_summary(value, binding=binding),
        "description": value.description,
        "directive": value.directive,
        "suitabilityHint": value.suitability_hint,
        "scheduledTime": _time_payload(value.scheduled_time),
        "deadlineTime": _time_payload(value.deadline_time),
        "allowRepeat": value.allow_repeat,
        "repeatCooldownMinutes": value.repeat_cooldown_minutes,
        "version": value.version,
    }


def _pool_cooldown_payload(
    value: PlotPoolCooldownDiagnostic,
) -> dict[str, object]:
    anchor = value.anchor
    return {
        "poolId": value.pool_id,
        "cooldownMinutes": value.cooldown_minutes,
        "status": value.status,
        "blocksAutomaticSelection": value.blocks_automatic_selection,
        "elapsedMinutes": value.elapsed_minutes,
        "remainingMinutes": value.remaining_minutes,
        "reasonCode": value.reason_code,
        "reason": value.reason,
        "anchorDecisionId": anchor.id if anchor is not None else None,
        "anchorTurnId": anchor.turn_id if anchor is not None else None,
        "anchorEventId": anchor.event_id if anchor is not None else None,
        "anchorSceneTime": (
            _time_payload(anchor.scene_time)
            if anchor is not None
            else None
        ),
    }


def _outline_summary(value) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": value.id,
        "storyId": value.story_id,
        "name": value.name,
        "priority": value.priority,
        "enabled": value.enabled,
        "nodeCount": len(value.nodes),
    }


def _time_payload(value) -> dict[str, int] | None:  # noqa: ANN001
    return value.to_dict() if value is not None else None


def _pending_event_id(value: object | None) -> int | None:
    if isinstance(value, data_models.SessionPlotPendingInjection):
        return value.source_event_id
    if isinstance(value, data_models.PendingPlotInjectionWrite):
        return value.source_event_id
    return None


def _pending_payload(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, data_models.SessionPlotPendingInjection):
        return {
            "sourceEventId": value.source_event_id,
            "sourceEventVersion": value.source_event_version,
            "sourcePoolId": value.source_pool_id,
            "sourcePoolName": value.source_pool_name,
            "eventTitle": value.event_title,
            "directive": value.directive,
            "requestedTurnId": value.requested_turn_id,
            "version": value.version,
        }
    if isinstance(value, data_models.PendingPlotInjectionWrite):
        return {
            "sourceEventId": value.source_event_id,
            "sourceEventVersion": value.source_event_version,
            "sourcePoolId": value.source_pool_id,
            "sourcePoolName": value.source_pool_name,
            "eventTitle": value.event_title,
            "directive": value.directive,
            "requestedTurnId": value.requested_turn_id,
            "version": None,
        }
    raise TypeError("unsupported pending Plot injection value")


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _json_error(code: str, message: str) -> str:
    return _json({
        "ok": False,
        "errorCode": code,
        "message": str(message),
    })


__all__ = [
    "PLOT_EVENT_MARK_NEXT_TOOL_NAME",
    "PLOT_SANDBOX_READ_TOOL_NAME",
    "PlotEventMarkNextTool",
    "PlotSandboxReadTool",
    "PlotSandboxToolProvider",
]
