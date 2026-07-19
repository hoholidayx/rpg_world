"""Story plot-definition management and Session scheduling ledger."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from peewee import Database, IntegrityError

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_data.repositories.plot_scheduling_repo import PlotSchedulingRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = [
    "PlotDefinitionInUseError",
    "PlotSchedulingService",
]


class PlotDefinitionInUseError(ValueError):
    """Raised when deleting a definition would silently damage another one."""


class PlotSchedulingService:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._records = PlotSchedulingRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def get_story_schedule(
        self,
        workspace_id: str,
        story_id: int,
    ) -> models.StoryPlotSchedule | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            return None
        return self.get_story_schedule_by_id(story.id)

    def get_story_schedule_by_id(self, story_id: int) -> models.StoryPlotSchedule:
        if self._stories.get(int(story_id)) is None:
            raise FileNotFoundError(f"story not found: {story_id}")
        return models.StoryPlotSchedule(
            story_id=int(story_id),
            pools=tuple(self._records.list_pools(story_id)),
            events=tuple(self._records.list_events(story_id)),
            outlines=tuple(self._records.list_outlines(story_id)),
        )

    def create_pool(
        self,
        workspace_id: str,
        story_id: int,
        *,
        name: str,
        description: str = "",
        selection_mode: str = models.PLOT_POOL_RANDOM,
        priority: int = 0,
        enabled: bool = True,
    ) -> models.StoryPlotEventPool:
        self._require_story(workspace_id, story_id)
        return self._records.create_pool(
            story_id=story_id,
            name=_required_text(name, "pool name"),
            description=str(description).strip(),
            selection_mode=_pool_mode(selection_mode),
            priority=_integer(priority, "priority"),
            enabled=_boolean(enabled, "enabled"),
        )

    def update_pool(
        self,
        workspace_id: str,
        story_id: int,
        pool_id: int,
        **patch: object,
    ) -> models.StoryPlotEventPool:
        current = self._require_pool(workspace_id, story_id, pool_id)
        updated = self._records.update_pool(
            pool_id,
            name=_required_text(patch.get("name", current.name), "pool name"),
            description=str(patch.get("description", current.description)).strip(),
            selection_mode=_pool_mode(patch.get("selection_mode", current.selection_mode)),
            priority=_integer(patch.get("priority", current.priority), "priority"),
            enabled=_boolean(patch.get("enabled", current.enabled), "enabled"),
        )
        if updated is None:  # pragma: no cover - required above
            raise FileNotFoundError(f"plot event pool not found: {pool_id}")
        return updated

    def delete_pool(self, workspace_id: str, story_id: int, pool_id: int) -> None:
        self._require_pool(workspace_id, story_id, pool_id)
        if self._records.list_events(story_id, pool_id=pool_id):
            raise PlotDefinitionInUseError("event pool must be empty before deletion")
        try:
            self._records.delete_pool(pool_id)
        except IntegrityError as exc:
            raise PlotDefinitionInUseError(
                "event pool must be empty before deletion"
            ) from exc

    def create_event(
        self,
        workspace_id: str,
        story_id: int,
        *,
        pool_id: int,
        title: str,
        directive: str,
        description: str = "",
        suitability_hint: str = "",
        dispatch_mode: str = models.PLOT_DISPATCH_SOFT,
        scheduled_time: SceneTime | Mapping[str, object] | None = None,
        position: int | None = None,
        enabled: bool = True,
        allow_repeat: bool = False,
        repeat_cooldown_minutes: int = 0,
    ) -> models.StoryPlotEvent:
        self._require_pool(workspace_id, story_id, pool_id)
        existing = self._records.list_events(story_id, pool_id=pool_id)
        resolved_position = (
            _next_position(existing)
            if position is None
            else _non_negative(position, "position")
        )
        repeat, cooldown = _repeat_config(allow_repeat, repeat_cooldown_minutes)
        return self._records.create_event(
            story_id=story_id,
            pool_id=pool_id,
            title=_required_text(title, "event title"),
            description=str(description).strip(),
            directive=_required_text(directive, "event directive"),
            suitability_hint=str(suitability_hint).strip(),
            dispatch_mode=_dispatch_mode(dispatch_mode),
            scheduled_time=_scene_time(scheduled_time, required=False),
            position=resolved_position,
            enabled=_boolean(enabled, "enabled"),
            allow_repeat=repeat,
            repeat_cooldown_minutes=cooldown,
        )

    def update_event(
        self,
        workspace_id: str,
        story_id: int,
        event_id: int,
        **patch: object,
    ) -> models.StoryPlotEvent:
        current = self._require_event(workspace_id, story_id, event_id)
        pool_id = _positive(patch.get("pool_id", current.pool_id), "pool_id")
        self._require_pool(workspace_id, story_id, pool_id)
        repeat, cooldown = _repeat_config(
            patch.get("allow_repeat", current.allow_repeat),
            patch.get("repeat_cooldown_minutes", current.repeat_cooldown_minutes),
        )
        if "position" in patch:
            position = _non_negative(patch["position"], "position")
        elif pool_id != current.pool_id:
            position = _next_position(
                self._records.list_events(story_id, pool_id=pool_id)
            )
        else:
            position = current.position
        values = {
            "pool_id": pool_id,
            "title": _required_text(patch.get("title", current.title), "event title"),
            "description": str(patch.get("description", current.description)).strip(),
            "directive": _required_text(
                patch.get("directive", current.directive),
                "event directive",
            ),
            "suitability_hint": str(
                patch.get("suitability_hint", current.suitability_hint)
            ).strip(),
            "dispatch_mode": _dispatch_mode(
                patch.get("dispatch_mode", current.dispatch_mode)
            ),
            "scheduled_time": _scene_time(
                patch.get("scheduled_time", current.scheduled_time),
                required=False,
            ),
            "position": position,
            "enabled": _boolean(patch.get("enabled", current.enabled), "enabled"),
            "allow_repeat": repeat,
            "repeat_cooldown_minutes": cooldown,
        }
        updated = self._records.update_event(event_id, **values)
        if updated is None:  # pragma: no cover - required above
            raise FileNotFoundError(f"plot event not found: {event_id}")
        return updated

    def reorder_events(
        self,
        workspace_id: str,
        story_id: int,
        pool_id: int,
        event_ids: Sequence[int],
    ) -> list[models.StoryPlotEvent]:
        self._require_pool(workspace_id, story_id, pool_id)
        current = self._records.list_events(story_id, pool_id=pool_id)
        _require_full_reorder([item.id for item in current], event_ids, "event")
        with self._database.atomic():
            for position, event_id in enumerate(event_ids):
                self._records.update_event(int(event_id), position=position)
        return self._records.list_events(story_id, pool_id=pool_id)

    def delete_event(self, workspace_id: str, story_id: int, event_id: int) -> None:
        self._require_event(workspace_id, story_id, event_id)
        try:
            self._records.delete_event(event_id)
        except IntegrityError as exc:
            raise PlotDefinitionInUseError(
                "event is referenced by an outline node and cannot be deleted"
            ) from exc

    def create_outline(
        self,
        workspace_id: str,
        story_id: int,
        *,
        name: str,
        description: str = "",
        priority: int = 0,
        enabled: bool = True,
    ) -> models.StoryPlotOutline:
        self._require_story(workspace_id, story_id)
        return self._records.create_outline(
            story_id=story_id,
            name=_required_text(name, "outline name"),
            description=str(description).strip(),
            priority=_integer(priority, "priority"),
            enabled=_boolean(enabled, "enabled"),
        )

    def update_outline(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        **patch: object,
    ) -> models.StoryPlotOutline:
        current = self._require_outline(workspace_id, story_id, outline_id)
        updated = self._records.update_outline(
            outline_id,
            name=_required_text(patch.get("name", current.name), "outline name"),
            description=str(patch.get("description", current.description)).strip(),
            priority=_integer(patch.get("priority", current.priority), "priority"),
            enabled=_boolean(patch.get("enabled", current.enabled), "enabled"),
        )
        if updated is None:  # pragma: no cover - required above
            raise FileNotFoundError(f"plot outline not found: {outline_id}")
        return updated

    def delete_outline(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
    ) -> None:
        self._require_outline(workspace_id, story_id, outline_id)
        self._records.delete_outline(outline_id)

    def create_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        *,
        event_id: int,
        scheduled_time: SceneTime | Mapping[str, object],
        dispatch_mode: str = models.PLOT_DISPATCH_SOFT,
        position: int | None = None,
        enabled: bool = True,
    ) -> models.StoryPlotOutlineNode:
        outline = self._require_outline(workspace_id, story_id, outline_id)
        self._require_event(workspace_id, story_id, event_id)
        resolved_position = (
            _next_position(outline.nodes)
            if position is None
            else _non_negative(position, "position")
        )
        with self._database.atomic():
            created = self._records.create_node(
                story_id=story_id,
                outline_id=outline_id,
                event_id=event_id,
                scheduled_time=_scene_time(scheduled_time, required=True),
                dispatch_mode=_dispatch_mode(dispatch_mode),
                position=resolved_position,
                enabled=_boolean(enabled, "enabled"),
            )
            self._validate_outline_times(outline_id)
        return created

    def update_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_id: int,
        **patch: object,
    ) -> models.StoryPlotOutlineNode:
        self._require_outline(workspace_id, story_id, outline_id)
        current = self._require_node(workspace_id, story_id, outline_id, node_id)
        event_id = _positive(patch.get("event_id", current.event_id), "event_id")
        self._require_event(workspace_id, story_id, event_id)
        with self._database.atomic():
            updated = self._records.update_node(
                node_id,
                event_id=event_id,
                scheduled_time=_scene_time(
                    patch.get("scheduled_time", current.scheduled_time),
                    required=True,
                ),
                dispatch_mode=_dispatch_mode(
                    patch.get("dispatch_mode", current.dispatch_mode)
                ),
                position=_non_negative(
                    patch.get("position", current.position),
                    "position",
                ),
                enabled=_boolean(patch.get("enabled", current.enabled), "enabled"),
            )
            if updated is None:  # pragma: no cover - required above
                raise FileNotFoundError(f"plot outline node not found: {node_id}")
            self._validate_outline_times(outline_id)
        return updated

    def reorder_nodes(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_ids: Sequence[int],
    ) -> list[models.StoryPlotOutlineNode]:
        outline = self._require_outline(workspace_id, story_id, outline_id)
        _require_full_reorder([item.id for item in outline.nodes], node_ids, "node")
        with self._database.atomic():
            for position, node_id in enumerate(node_ids):
                self._records.update_node(int(node_id), position=position)
            self._validate_outline_times(outline_id)
        return self._records.list_nodes(story_id, outline_id=outline_id)

    def delete_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_id: int,
    ) -> None:
        self._require_node(workspace_id, story_id, outline_id, node_id)
        self._records.delete_node(node_id)

    def get_session_state(
        self,
        session_id: str,
    ) -> tuple[
        models.StoryPlotSchedule,
        models.SessionPlotOverrides,
        list[models.SessionPlotScheduleDecision],
    ]:
        schedule, overrides = self.get_session_schedule(session_id)
        return (
            schedule,
            overrides,
            self._records.list_decisions(session_id),
        )

    def get_session_schedule(
        self,
        session_id: str,
    ) -> tuple[models.StoryPlotSchedule, models.SessionPlotOverrides]:
        session = self._require_session(session_id)
        return (
            self.get_story_schedule_by_id(session.story_id),
            self._records.list_overrides(session.id),
        )

    def list_session_decisions(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[models.SessionPlotScheduleDecision]:
        self._require_session(session_id)
        normalized_limit = _positive(limit, "limit") if limit is not None else None
        if (
            normalized_limit is not None
            and normalized_limit > models.PLOT_DECISION_PAGE_SIZE_MAX + 1
        ):
            raise ValueError(
                "limit must be between 1 and "
                f"{models.PLOT_DECISION_PAGE_SIZE_MAX + 1}"
            )
        return self._records.list_decisions(
            session_id,
            limit=normalized_limit,
            before_id=(
                _positive(before_id, "before_id")
                if before_id is not None
                else None
            ),
        )

    def set_session_event_disabled(
        self,
        session_id: str,
        event_id: int,
        disabled: bool,
    ) -> models.SessionPlotOverrides:
        session = self._require_session(session_id)
        event = self._records.get_event(event_id)
        if event is None or event.story_id != session.story_id:
            raise FileNotFoundError(f"plot event not found in session Story: {event_id}")
        with self._database.atomic():
            self._records.set_event_disabled(
                session.id,
                event.id,
                _boolean(disabled, "disabled"),
            )
        return self._records.list_overrides(session.id)

    def set_session_node_disabled(
        self,
        session_id: str,
        node_id: int,
        disabled: bool,
    ) -> models.SessionPlotOverrides:
        session = self._require_session(session_id)
        node = self._records.get_node(node_id)
        if node is None or node.story_id != session.story_id:
            raise FileNotFoundError(f"plot outline node not found in session Story: {node_id}")
        with self._database.atomic():
            self._records.set_node_disabled(
                session.id,
                node.id,
                _boolean(disabled, "disabled"),
            )
        return self._records.list_overrides(session.id)

    def record_decisions(
        self,
        session_id: str,
        turn_id: int,
        decisions: Iterable[models.StagedPlotScheduleDecision],
    ) -> list[models.SessionPlotScheduleDecision]:
        session = self._require_session(session_id)
        turn = _positive(turn_id, "turn_id")
        staged = tuple(decisions)
        if len(staged) > 2:
            raise ValueError("at most two plot schedule decisions may be recorded per turn")
        kinds: set[str] = set()
        for decision in staged:
            if decision.source_kind not in models.PLOT_SOURCE_KINDS:
                raise ValueError(f"unsupported plot source kind: {decision.source_kind}")
            if decision.source_kind in kinds:
                raise ValueError("only one plot schedule decision is allowed per source kind")
            kinds.add(decision.source_kind)
            if decision.decision_status not in models.PLOT_DECISION_STATUSES:
                raise ValueError(f"unsupported plot decision status: {decision.decision_status}")
            _dispatch_mode(decision.dispatch_mode)
        return self._records.create_decisions(session.id, turn, staged)

    def delete_decisions_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_from_turn(session_id, _positive(turn_id, "turn_id"))

    def delete_decisions_for_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_for_turn(session_id, _positive(turn_id, "turn_id"))

    def retain_decision_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        return self._records.retain_turns(session_id, turn_ids)

    def clear_session_decisions(self, session_id: str) -> int:
        return self._records.clear_decisions(session_id)

    def copy_derivation_state(
        self,
        source_session_id: str,
        target_session_id: str,
        through_turn_id: int,
    ) -> int:
        source = self._require_session(source_session_id)
        target = self._require_session(target_session_id)
        if source.story_id != target.story_id:
            raise ValueError("plot scheduling derivation requires the same Story")
        with self._database.atomic():
            self._records.copy_overrides(source.id, target.id)
            return self._records.copy_triggered_decisions(
                source.id,
                target.id,
                _positive(through_turn_id, "through_turn_id"),
            )

    def _validate_outline_times(self, outline_id: int) -> None:
        outline = self._records.get_outline(outline_id)
        if outline is None:
            raise FileNotFoundError(f"plot outline not found: {outline_id}")
        previous: SceneTime | None = None
        for node in sorted(outline.nodes, key=lambda item: (item.position, item.id)):
            if previous is not None and node.scheduled_time < previous:
                raise ValueError("outline node times must be nondecreasing in node order")
            previous = node.scheduled_time

    def _require_story(self, workspace_id: str, story_id: int):
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            raise FileNotFoundError(f"story not found in workspace: {story_id}")
        return story

    def _require_pool(self, workspace_id: str, story_id: int, pool_id: int):
        self._require_story(workspace_id, story_id)
        pool = self._records.get_pool(_positive(pool_id, "pool_id"))
        if pool is None or pool.story_id != int(story_id):
            raise FileNotFoundError(f"plot event pool not found in Story: {pool_id}")
        return pool

    def _require_event(self, workspace_id: str, story_id: int, event_id: int):
        self._require_story(workspace_id, story_id)
        event = self._records.get_event(_positive(event_id, "event_id"))
        if event is None or event.story_id != int(story_id):
            raise FileNotFoundError(f"plot event not found in Story: {event_id}")
        return event

    def _require_outline(self, workspace_id: str, story_id: int, outline_id: int):
        self._require_story(workspace_id, story_id)
        outline = self._records.get_outline(_positive(outline_id, "outline_id"))
        if outline is None or outline.story_id != int(story_id):
            raise FileNotFoundError(f"plot outline not found in Story: {outline_id}")
        return outline

    def _require_node(
        self,
        workspace_id: str,
        story_id: int,
        outline_id: int,
        node_id: int,
    ):
        self._require_outline(workspace_id, story_id, outline_id)
        node = self._records.get_node(_positive(node_id, "node_id"))
        if (
            node is None
            or node.story_id != int(story_id)
            or node.outline_id != int(outline_id)
        ):
            raise FileNotFoundError(f"plot outline node not found: {node_id}")
        return node

    def _require_session(self, session_id: str):
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        return session


def _scene_time(
    value: SceneTime | Mapping[str, object] | None,
    *,
    required: bool,
) -> SceneTime | None:
    if value is None:
        if required:
            raise ValueError("scheduled_time is required")
        return None
    return value if isinstance(value, SceneTime) else SceneTime.from_mapping(value)


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _pool_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode not in models.PLOT_POOL_MODES:
        raise ValueError(f"unsupported plot pool mode: {mode}")
    return mode


def _dispatch_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode not in models.PLOT_DISPATCH_MODES:
        raise ValueError(f"unsupported plot dispatch mode: {mode}")
    return mode


def _repeat_config(allow_repeat: object, cooldown: object) -> tuple[bool, int]:
    repeat = _boolean(allow_repeat, "allow_repeat")
    minutes = _non_negative(cooldown, "repeat_cooldown_minutes")
    if repeat and minutes <= 0:
        raise ValueError("repeat_cooldown_minutes must be positive when repeat is enabled")
    if not repeat:
        minutes = 0
    return repeat, minutes


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive(value: object, label: str) -> int:
    parsed = _integer(value, label)
    if parsed <= 0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _non_negative(value: object, label: str) -> int:
    parsed = _integer(value, label)
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative")
    return parsed


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _require_full_reorder(current: list[int], requested: Sequence[int], label: str) -> None:
    normalized = [int(item) for item in requested]
    if len(normalized) != len(set(normalized)) or set(normalized) != set(current):
        raise ValueError(f"{label} reorder must contain every current id exactly once")


def _next_position(
    items: Iterable[models.StoryPlotEvent | models.StoryPlotOutlineNode],
) -> int:
    return max((item.position for item in items), default=-1) + 1
