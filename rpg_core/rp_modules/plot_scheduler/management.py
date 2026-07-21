"""Business rules and application service for Plot Scheduler definitions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import ContextManager, Protocol, TypeVar

from commons.scene_time import SceneTime
from rpg_core.rp_modules.plot_scheduler.commands import (
    CreatePlotEventCommand,
    CreatePlotNodeCommand,
    CreatePlotOutlineCommand,
    CreatePlotPoolCommand,
    PLOT_PATCH_UNSET,
    PlotPatchUnset,
    UpdatePlotEventCommand,
    UpdatePlotNodeCommand,
    UpdatePlotOutlineCommand,
    UpdatePlotPoolCommand,
)
from rpg_data import models as data_models
from rpg_data.errors import DataIntegrityError

_ValueT = TypeVar("_ValueT")


class PlotDefinitionInUseError(ValueError):
    """A definition cannot be removed while another definition uses it."""


class PlotScheduleConflictError(RuntimeError):
    """Persisted Plot data changed or rejected an otherwise valid command."""


class PlotScheduleManagementDataPort(Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def get_story_schedule(
        self,
        workspace_id: str,
        story_id: int,
    ) -> data_models.StoryPlotSchedule | None: ...

    def get_pool(
        self,
        story_id: int,
        pool_id: int,
    ) -> data_models.StoryPlotEventPool | None: ...

    def list_events(
        self,
        story_id: int,
        *,
        pool_id: int | None = None,
    ) -> list[data_models.StoryPlotEvent]: ...

    def get_event(
        self,
        story_id: int,
        event_id: int,
    ) -> data_models.StoryPlotEvent | None: ...

    def get_outline(
        self,
        story_id: int,
        outline_id: int,
    ) -> data_models.StoryPlotOutline | None: ...

    def get_node(
        self,
        story_id: int,
        outline_id: int,
        node_id: int,
    ) -> data_models.StoryPlotOutlineNode | None: ...

    def create_pool(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        enabled: bool,
    ) -> data_models.StoryPlotEventPool: ...

    def update_pool(
        self,
        pool_id: int,
        *,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        enabled: bool,
    ) -> data_models.StoryPlotEventPool | None: ...

    def delete_pool(self, pool_id: int) -> int: ...

    def create_event(
        self,
        *,
        story_id: int,
        pool_id: int,
        title: str,
        description: str,
        directive: str,
        suitability_hint: str,
        dispatch_mode: str,
        scheduled_time: SceneTime | None,
        position: int,
        enabled: bool,
        allow_repeat: bool,
        repeat_cooldown_minutes: int,
    ) -> data_models.StoryPlotEvent: ...

    def update_event(
        self,
        event_id: int,
        *,
        pool_id: int,
        title: str,
        description: str,
        directive: str,
        suitability_hint: str,
        dispatch_mode: str,
        scheduled_time: SceneTime | None,
        position: int,
        enabled: bool,
        allow_repeat: bool,
        repeat_cooldown_minutes: int,
    ) -> data_models.StoryPlotEvent | None: ...

    def set_event_positions(self, event_ids: Sequence[int]) -> None: ...

    def delete_event(self, event_id: int) -> int: ...

    def create_outline(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> data_models.StoryPlotOutline: ...

    def update_outline(
        self,
        outline_id: int,
        *,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> data_models.StoryPlotOutline | None: ...

    def delete_outline(self, outline_id: int) -> int: ...

    def create_node(
        self,
        *,
        story_id: int,
        outline_id: int,
        event_id: int,
        scheduled_time: SceneTime,
        dispatch_mode: str,
        position: int,
        enabled: bool,
    ) -> data_models.StoryPlotOutlineNode: ...

    def update_node(
        self,
        node_id: int,
        *,
        event_id: int,
        scheduled_time: SceneTime,
        dispatch_mode: str,
        position: int,
        enabled: bool,
    ) -> data_models.StoryPlotOutlineNode | None: ...

    def set_node_positions(self, node_ids: Sequence[int]) -> None: ...

    def delete_node(self, node_id: int) -> int: ...

    def get_session_schedule(
        self,
        session_id: str,
    ) -> tuple[
        data_models.StoryPlotSchedule,
        data_models.SessionPlotOverrides,
    ]: ...

    def list_session_decisions(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[data_models.SessionPlotScheduleDecision]: ...

    def set_session_event_disabled(
        self,
        session_id: str,
        event_id: int,
        disabled: bool,
    ) -> data_models.SessionPlotOverrides: ...

    def set_session_node_disabled(
        self,
        session_id: str,
        node_id: int,
        disabled: bool,
    ) -> data_models.SessionPlotOverrides: ...


class PlotScheduleManagementService:
    """Apply Plot definition rules around the persistence-only data facade."""

    def __init__(self, data: PlotScheduleManagementDataPort) -> None:
        self._data = data

    def get_story_schedule(
        self,
        workspace_id: str,
        story_id: int,
    ) -> data_models.StoryPlotSchedule | None:
        return self._data.get_story_schedule(workspace_id, story_id)

    def get_session_schedule(
        self,
        session_id: str,
    ) -> tuple[data_models.StoryPlotSchedule, data_models.SessionPlotOverrides]:
        return self._data.get_session_schedule(session_id)

    def list_session_decisions(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[data_models.SessionPlotScheduleDecision]:
        return self._data.list_session_decisions(
            session_id,
            limit=limit,
            before_id=before_id,
        )

    def create_pool(
        self,
        command: CreatePlotPoolCommand,
    ) -> data_models.StoryPlotEventPool:
        with self._transaction():
            self._require_story(command.workspace_id, command.story_id)
            return self._data.create_pool(
                story_id=command.story_id,
                name=_required_text(command.name, "pool name"),
                description=_text(command.description),
                selection_mode=_pool_mode(command.selection_mode),
                priority=_integer(command.priority, "priority"),
                enabled=_boolean(command.enabled, "enabled"),
            )

    def update_pool(
        self,
        command: UpdatePlotPoolCommand,
    ) -> data_models.StoryPlotEventPool:
        with self._transaction():
            current = self._require_pool(
                command.workspace_id,
                command.story_id,
                command.pool_id,
            )
            updated = self._data.update_pool(
                current.id,
                name=_required_text(
                    _resolve_patch(command.name, current.name),
                    "pool name",
                ),
                description=_text(
                    _resolve_patch(command.description, current.description)
                ),
                selection_mode=_pool_mode(
                    _resolve_patch(command.selection_mode, current.selection_mode)
                ),
                priority=_integer(
                    _resolve_patch(command.priority, current.priority),
                    "priority",
                ),
                enabled=_boolean(
                    _resolve_patch(command.enabled, current.enabled),
                    "enabled",
                ),
            )
            if updated is None:
                raise FileNotFoundError(f"plot event pool not found: {current.id}")
            return updated

    def delete_pool(self, workspace_id: str, story_id: int, pool_id: int) -> None:
        with self._transaction():
            pool = self._require_pool(workspace_id, story_id, pool_id)
            if self._data.list_events(story_id, pool_id=pool.id):
                raise PlotDefinitionInUseError("event pool must be empty before deletion")
            try:
                self._data.delete_pool(pool.id)
            except DataIntegrityError as exc:
                raise PlotDefinitionInUseError(
                    "event pool must be empty before deletion"
                ) from exc

    def create_event(
        self,
        command: CreatePlotEventCommand,
    ) -> data_models.StoryPlotEvent:
        with self._transaction():
            pool = self._require_pool(
                command.workspace_id,
                command.story_id,
                command.pool_id,
            )
            events = self._data.list_events(command.story_id, pool_id=pool.id)
            position = (
                _next_position(events)
                if command.position is None
                else _non_negative(command.position, "position")
            )
            allow_repeat, cooldown = _repeat_config(
                command.allow_repeat,
                command.repeat_cooldown_minutes,
            )
            return self._data.create_event(
                story_id=command.story_id,
                pool_id=pool.id,
                title=_required_text(command.title, "event title"),
                description=_text(command.description),
                directive=_required_text(command.directive, "event directive"),
                suitability_hint=_text(command.suitability_hint),
                dispatch_mode=_dispatch_mode(command.dispatch_mode),
                scheduled_time=_optional_scene_time(command.scheduled_time),
                position=position,
                enabled=_boolean(command.enabled, "enabled"),
                allow_repeat=allow_repeat,
                repeat_cooldown_minutes=cooldown,
            )

    def update_event(
        self,
        command: UpdatePlotEventCommand,
    ) -> data_models.StoryPlotEvent:
        with self._transaction():
            current = self._require_event(
                command.workspace_id,
                command.story_id,
                command.event_id,
            )
            pool_id = _positive(
                _resolve_patch(command.pool_id, current.pool_id),
                "pool_id",
            )
            self._require_pool(command.workspace_id, command.story_id, pool_id)
            allow_repeat, cooldown = _repeat_config(
                _resolve_patch(command.allow_repeat, current.allow_repeat),
                _resolve_patch(
                    command.repeat_cooldown_minutes,
                    current.repeat_cooldown_minutes,
                ),
            )
            if command.position is not PLOT_PATCH_UNSET:
                position = _non_negative(command.position, "position")
            elif pool_id != current.pool_id:
                position = _next_position(
                    self._data.list_events(command.story_id, pool_id=pool_id)
                )
            else:
                position = current.position
            updated = self._data.update_event(
                current.id,
                pool_id=pool_id,
                title=_required_text(
                    _resolve_patch(command.title, current.title),
                    "event title",
                ),
                description=_text(
                    _resolve_patch(command.description, current.description)
                ),
                directive=_required_text(
                    _resolve_patch(command.directive, current.directive),
                    "event directive",
                ),
                suitability_hint=_text(
                    _resolve_patch(
                        command.suitability_hint,
                        current.suitability_hint,
                    )
                ),
                dispatch_mode=_dispatch_mode(
                    _resolve_patch(command.dispatch_mode, current.dispatch_mode)
                ),
                scheduled_time=_optional_scene_time(
                    _resolve_patch(command.scheduled_time, current.scheduled_time)
                ),
                position=position,
                enabled=_boolean(
                    _resolve_patch(command.enabled, current.enabled),
                    "enabled",
                ),
                allow_repeat=allow_repeat,
                repeat_cooldown_minutes=cooldown,
            )
            if updated is None:
                raise FileNotFoundError(f"plot event not found: {current.id}")
            return updated

    def reorder_events(
        self,
        workspace_id: str,
        story_id: int,
        pool_id: int,
        event_ids: Sequence[int],
    ) -> list[data_models.StoryPlotEvent]:
        with self._transaction():
            pool = self._require_pool(workspace_id, story_id, pool_id)
            current = self._data.list_events(story_id, pool_id=pool.id)
            normalized = _require_full_reorder(
                [item.id for item in current],
                event_ids,
                "event",
            )
            self._data.set_event_positions(normalized)
            return self._data.list_events(story_id, pool_id=pool.id)

    def delete_event(self, workspace_id: str, story_id: int, event_id: int) -> None:
        with self._transaction():
            event = self._require_event(workspace_id, story_id, event_id)
            try:
                self._data.delete_event(event.id)
            except DataIntegrityError as exc:
                raise PlotDefinitionInUseError(
                    "event is referenced by an outline node and cannot be deleted"
                ) from exc

    def create_outline(
        self,
        command: CreatePlotOutlineCommand,
    ) -> data_models.StoryPlotOutline:
        with self._transaction():
            self._require_story(command.workspace_id, command.story_id)
            return self._data.create_outline(
                story_id=command.story_id,
                name=_required_text(command.name, "outline name"),
                description=_text(command.description),
                priority=_integer(command.priority, "priority"),
                enabled=_boolean(command.enabled, "enabled"),
            )

    def update_outline(
        self,
        command: UpdatePlotOutlineCommand,
    ) -> data_models.StoryPlotOutline:
        with self._transaction():
            current = self._require_outline(
                command.workspace_id,
                command.story_id,
                command.outline_id,
            )
            updated = self._data.update_outline(
                current.id,
                name=_required_text(
                    _resolve_patch(command.name, current.name),
                    "outline name",
                ),
                description=_text(
                    _resolve_patch(command.description, current.description)
                ),
                priority=_integer(
                    _resolve_patch(command.priority, current.priority),
                    "priority",
                ),
                enabled=_boolean(
                    _resolve_patch(command.enabled, current.enabled),
                    "enabled",
                ),
            )
            if updated is None:
                raise FileNotFoundError(f"plot outline not found: {current.id}")
            return updated

    def delete_outline(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
    ) -> None:
        with self._transaction():
            outline = self._require_outline(workspace_id, story_id, outline_id)
            self._data.delete_outline(outline.id)

    def create_node(
        self,
        command: CreatePlotNodeCommand,
    ) -> data_models.StoryPlotOutlineNode:
        with self._transaction():
            outline = self._require_outline(
                command.workspace_id,
                command.story_id,
                command.outline_id,
            )
            event = self._require_event(
                command.workspace_id,
                command.story_id,
                command.event_id,
            )
            position = (
                _next_position(outline.nodes)
                if command.position is None
                else _non_negative(command.position, "position")
            )
            created = self._data.create_node(
                story_id=command.story_id,
                outline_id=outline.id,
                event_id=event.id,
                scheduled_time=_scene_time(command.scheduled_time),
                dispatch_mode=_dispatch_mode(command.dispatch_mode),
                position=position,
                enabled=_boolean(command.enabled, "enabled"),
            )
            self._validate_outline_times(command.story_id, outline.id)
            return created

    def update_node(
        self,
        command: UpdatePlotNodeCommand,
    ) -> data_models.StoryPlotOutlineNode:
        with self._transaction():
            current = self._require_node(
                command.workspace_id,
                command.story_id,
                command.outline_id,
                command.node_id,
            )
            event_id = _positive(
                _resolve_patch(command.event_id, current.event_id),
                "event_id",
            )
            self._require_event(command.workspace_id, command.story_id, event_id)
            updated = self._data.update_node(
                current.id,
                event_id=event_id,
                scheduled_time=_scene_time(
                    _resolve_patch(command.scheduled_time, current.scheduled_time)
                ),
                dispatch_mode=_dispatch_mode(
                    _resolve_patch(command.dispatch_mode, current.dispatch_mode)
                ),
                position=_non_negative(
                    _resolve_patch(command.position, current.position),
                    "position",
                ),
                enabled=_boolean(
                    _resolve_patch(command.enabled, current.enabled),
                    "enabled",
                ),
            )
            if updated is None:
                raise FileNotFoundError(f"plot outline node not found: {current.id}")
            self._validate_outline_times(command.story_id, command.outline_id)
            return updated

    def reorder_nodes(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_ids: Sequence[int],
    ) -> list[data_models.StoryPlotOutlineNode]:
        with self._transaction():
            outline = self._require_outline(workspace_id, story_id, outline_id)
            normalized = _require_full_reorder(
                [item.id for item in outline.nodes],
                node_ids,
                "node",
            )
            self._data.set_node_positions(normalized)
            self._validate_outline_times(story_id, outline.id)
            refreshed = self._data.get_outline(story_id, outline.id)
            if refreshed is None:
                raise FileNotFoundError(f"plot outline not found: {outline.id}")
            return list(refreshed.nodes)

    def delete_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_id: int,
    ) -> None:
        with self._transaction():
            node = self._require_node(
                workspace_id,
                story_id,
                outline_id,
                node_id,
            )
            self._data.delete_node(node.id)

    def set_session_event_disabled(
        self,
        session_id: str,
        event_id: int,
        disabled: bool,
    ) -> data_models.SessionPlotOverrides:
        with self._transaction():
            return self._data.set_session_event_disabled(
                session_id,
                event_id,
                _boolean(disabled, "disabled"),
            )

    def set_session_node_disabled(
        self,
        session_id: str,
        node_id: int,
        disabled: bool,
    ) -> data_models.SessionPlotOverrides:
        with self._transaction():
            return self._data.set_session_node_disabled(
                session_id,
                node_id,
                _boolean(disabled, "disabled"),
            )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            with self._data.transaction():
                yield
        except DataIntegrityError as exc:
            raise PlotScheduleConflictError(
                "plot schedule command conflicts with persisted data"
            ) from exc

    def _validate_outline_times(self, story_id: int, outline_id: int) -> None:
        outline = self._data.get_outline(story_id, outline_id)
        if outline is None:
            raise FileNotFoundError(f"plot outline not found: {outline_id}")
        previous: SceneTime | None = None
        for node in sorted(outline.nodes, key=lambda item: (item.position, item.id)):
            if previous is not None and node.scheduled_time < previous:
                raise ValueError("outline node times must be nondecreasing in node order")
            previous = node.scheduled_time

    def _require_story(
        self,
        workspace_id: str,
        story_id: int,
    ) -> data_models.StoryPlotSchedule:
        schedule = self._data.get_story_schedule(workspace_id, story_id)
        if schedule is None:
            raise FileNotFoundError(f"story not found in workspace: {story_id}")
        return schedule

    def _require_pool(
        self,
        workspace_id: str,
        story_id: int,
        pool_id: int,
    ) -> data_models.StoryPlotEventPool:
        self._require_story(workspace_id, story_id)
        pool = self._data.get_pool(story_id, _positive(pool_id, "pool_id"))
        if pool is None:
            raise FileNotFoundError(f"plot event pool not found in Story: {pool_id}")
        return pool

    def _require_event(
        self,
        workspace_id: str,
        story_id: int,
        event_id: int,
    ) -> data_models.StoryPlotEvent:
        self._require_story(workspace_id, story_id)
        event = self._data.get_event(story_id, _positive(event_id, "event_id"))
        if event is None:
            raise FileNotFoundError(f"plot event not found in Story: {event_id}")
        return event

    def _require_outline(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
    ) -> data_models.StoryPlotOutline:
        self._require_story(workspace_id, story_id)
        outline = self._data.get_outline(
            story_id,
            _positive(outline_id, "outline_id"),
        )
        if outline is None:
            raise FileNotFoundError(f"plot outline not found in Story: {outline_id}")
        return outline

    def _require_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_id: int,
    ) -> data_models.StoryPlotOutlineNode:
        self._require_outline(workspace_id, story_id, outline_id)
        node = self._data.get_node(
            story_id,
            outline_id,
            _positive(node_id, "node_id"),
        )
        if node is None:
            raise FileNotFoundError(f"plot outline node not found: {node_id}")
        return node


def _resolve_patch(
    value: _ValueT | PlotPatchUnset,
    current: _ValueT,
) -> _ValueT:
    if value is PLOT_PATCH_UNSET:
        return current
    return value


def _required_text(value: str, label: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("plot text fields must be strings")
    return value.strip()


def _pool_mode(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("plot pool mode must be a string")
    mode = value.strip().lower()
    if mode not in data_models.PLOT_POOL_MODES:
        raise ValueError(f"unsupported plot pool mode: {mode}")
    return mode


def _dispatch_mode(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("plot dispatch mode must be a string")
    mode = value.strip().lower()
    if mode not in data_models.PLOT_DISPATCH_MODES:
        raise ValueError(f"unsupported plot dispatch mode: {mode}")
    return mode


def _repeat_config(allow_repeat: bool, cooldown: int) -> tuple[bool, int]:
    repeat = _boolean(allow_repeat, "allow_repeat")
    minutes = _non_negative(cooldown, "repeat_cooldown_minutes")
    if repeat and minutes <= 0:
        raise ValueError("repeat_cooldown_minutes must be positive when repeat is enabled")
    return repeat, minutes if repeat else 0


def _integer(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive(value: int, label: str) -> int:
    parsed = _integer(value, label)
    if parsed <= 0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _non_negative(value: int, label: str) -> int:
    parsed = _integer(value, label)
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative")
    return parsed


def _boolean(value: bool, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _optional_scene_time(value: SceneTime | None) -> SceneTime | None:
    if value is None:
        return None
    return _scene_time(value)


def _scene_time(value: SceneTime) -> SceneTime:
    if not isinstance(value, SceneTime):
        raise ValueError("scheduled_time must be a SceneTime")
    return value


def _require_full_reorder(
    current: list[int],
    requested: Sequence[int],
    label: str,
) -> tuple[int, ...]:
    normalized = tuple(int(item) for item in requested)
    if len(normalized) != len(set(normalized)) or set(normalized) != set(current):
        raise ValueError(f"{label} reorder must contain every current id exactly once")
    return normalized


def _next_position(
    items: Iterable[data_models.StoryPlotEvent | data_models.StoryPlotOutlineNode],
) -> int:
    return max((item.position for item in items), default=-1) + 1


__all__ = [
    "PlotDefinitionInUseError",
    "PlotScheduleConflictError",
    "PlotScheduleManagementDataPort",
    "PlotScheduleManagementService",
]
