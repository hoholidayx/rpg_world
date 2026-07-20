"""Typed CRUD facade for Plot Scheduler persistence."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator, Sequence
from contextlib import contextmanager

from peewee import Database, IntegrityError

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_data.repositories.plot_scheduling_repo import PlotSchedulingRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository

__all__ = [
    "PlotScheduleDataIntegrityError",
    "PlotSchedulingDataService",
]


class PlotScheduleDataIntegrityError(RuntimeError):
    """A Plot Scheduler write was rejected by persisted data constraints."""


class PlotSchedulingDataService:
    """Expose Plot definition, override, and decision-ledger data operations."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._records = PlotSchedulingRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

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

    def get_pool(
        self,
        story_id: int,
        pool_id: int,
    ) -> models.StoryPlotEventPool | None:
        pool = self._records.get_pool(int(pool_id))
        if pool is None or pool.story_id != int(story_id):
            return None
        return pool

    def list_events(
        self,
        story_id: int,
        *,
        pool_id: int | None = None,
    ) -> list[models.StoryPlotEvent]:
        return self._records.list_events(int(story_id), pool_id=pool_id)

    def get_event(
        self,
        story_id: int,
        event_id: int,
    ) -> models.StoryPlotEvent | None:
        event = self._records.get_event(int(event_id))
        if event is None or event.story_id != int(story_id):
            return None
        return event

    def get_outline(
        self,
        story_id: int,
        outline_id: int,
    ) -> models.StoryPlotOutline | None:
        outline = self._records.get_outline(int(outline_id))
        if outline is None or outline.story_id != int(story_id):
            return None
        return outline

    def get_node(
        self,
        story_id: int,
        outline_id: int,
        node_id: int,
    ) -> models.StoryPlotOutlineNode | None:
        node = self._records.get_node(int(node_id))
        if (
            node is None
            or node.story_id != int(story_id)
            or node.outline_id != int(outline_id)
        ):
            return None
        return node

    def create_pool(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotEventPool:
        self._require_story(story_id)
        try:
            return self._records.create_pool(
                story_id=story_id,
                name=name,
                description=description,
                selection_mode=selection_mode,
                priority=priority,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot pool write violated data constraints"
            ) from exc

    def update_pool(
        self,
        pool_id: int,
        *,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotEventPool | None:
        try:
            return self._records.update_pool(
                pool_id,
                name=name,
                description=description,
                selection_mode=selection_mode,
                priority=priority,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot pool write violated data constraints"
            ) from exc

    def delete_pool(self, pool_id: int) -> int:
        try:
            return self._records.delete_pool(pool_id)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError("plot pool is still referenced") from exc

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
    ) -> models.StoryPlotEvent:
        self._require_pool_owner(story_id, pool_id)
        try:
            return self._records.create_event(
                story_id=story_id,
                pool_id=pool_id,
                title=title,
                description=description,
                directive=directive,
                suitability_hint=suitability_hint,
                dispatch_mode=dispatch_mode,
                scheduled_time=scheduled_time,
                position=position,
                enabled=enabled,
                allow_repeat=allow_repeat,
                repeat_cooldown_minutes=repeat_cooldown_minutes,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot event write violated data constraints"
            ) from exc

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
    ) -> models.StoryPlotEvent | None:
        current = self._records.get_event(int(event_id))
        if current is None:
            return None
        self._require_pool_owner(current.story_id, pool_id)
        try:
            return self._records.update_event(
                event_id,
                pool_id=pool_id,
                title=title,
                description=description,
                directive=directive,
                suitability_hint=suitability_hint,
                dispatch_mode=dispatch_mode,
                scheduled_time=scheduled_time,
                position=position,
                enabled=enabled,
                allow_repeat=allow_repeat,
                repeat_cooldown_minutes=repeat_cooldown_minutes,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot event write violated data constraints"
            ) from exc

    def set_event_positions(self, event_ids: Sequence[int]) -> None:
        with self.transaction():
            for position, event_id in enumerate(event_ids):
                if self._records.set_event_position(int(event_id), position) != 1:
                    raise FileNotFoundError(f"plot event not found: {event_id}")

    def delete_event(self, event_id: int) -> int:
        try:
            return self._records.delete_event(event_id)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError("plot event is still referenced") from exc

    def create_outline(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotOutline:
        self._require_story(story_id)
        try:
            return self._records.create_outline(
                story_id=story_id,
                name=name,
                description=description,
                priority=priority,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot outline write violated data constraints"
            ) from exc

    def update_outline(
        self,
        outline_id: int,
        *,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotOutline | None:
        try:
            return self._records.update_outline(
                outline_id,
                name=name,
                description=description,
                priority=priority,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot outline write violated data constraints"
            ) from exc

    def delete_outline(self, outline_id: int) -> int:
        return self._records.delete_outline(outline_id)

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
    ) -> models.StoryPlotOutlineNode:
        self._require_outline_owner(story_id, outline_id)
        self._require_event_owner(story_id, event_id)
        try:
            return self._records.create_node(
                story_id=story_id,
                outline_id=outline_id,
                event_id=event_id,
                scheduled_time=scheduled_time,
                dispatch_mode=dispatch_mode,
                position=position,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot node write violated data constraints"
            ) from exc

    def update_node(
        self,
        node_id: int,
        *,
        event_id: int,
        scheduled_time: SceneTime,
        dispatch_mode: str,
        position: int,
        enabled: bool,
    ) -> models.StoryPlotOutlineNode | None:
        current = self._records.get_node(int(node_id))
        if current is None:
            return None
        self._require_event_owner(current.story_id, event_id)
        try:
            return self._records.update_node(
                node_id,
                event_id=event_id,
                scheduled_time=scheduled_time,
                dispatch_mode=dispatch_mode,
                position=position,
                enabled=enabled,
            )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot node write violated data constraints"
            ) from exc

    def set_node_positions(self, node_ids: Sequence[int]) -> None:
        with self.transaction():
            for position, node_id in enumerate(node_ids):
                if self._records.set_node_position(int(node_id), position) != 1:
                    raise FileNotFoundError(f"plot outline node not found: {node_id}")

    def delete_node(self, node_id: int) -> int:
        return self._records.delete_node(node_id)

    def get_session_state(
        self,
        session_id: str,
    ) -> tuple[
        models.StoryPlotSchedule,
        models.SessionPlotOverrides,
        list[models.SessionPlotScheduleDecision],
    ]:
        schedule, overrides = self.get_session_schedule(session_id)
        return schedule, overrides, self._records.list_decisions(session_id)

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
        normalized_limit = _positive_integer(limit, "limit") if limit is not None else None
        normalized_before = (
            _positive_integer(before_id, "before_id")
            if before_id is not None
            else None
        )
        return self._records.list_decisions(
            session_id,
            limit=normalized_limit,
            before_id=normalized_before,
        )

    def set_session_event_disabled(
        self,
        session_id: str,
        event_id: int,
        disabled: bool,
    ) -> models.SessionPlotOverrides:
        session = self._require_session(session_id)
        self._require_event_owner(session.story_id, event_id)
        try:
            self._records.set_event_disabled(session.id, int(event_id), disabled)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot event override write violated data constraints"
            ) from exc
        return self._records.list_overrides(session.id)

    def set_session_node_disabled(
        self,
        session_id: str,
        node_id: int,
        disabled: bool,
    ) -> models.SessionPlotOverrides:
        session = self._require_session(session_id)
        node = self._records.get_node(int(node_id))
        if node is None or node.story_id != session.story_id:
            raise FileNotFoundError(
                f"plot outline node not found in session Story: {node_id}"
            )
        try:
            self._records.set_node_disabled(session.id, node.id, disabled)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot node override write violated data constraints"
            ) from exc
        return self._records.list_overrides(session.id)

    def append_decisions(
        self,
        session_id: str,
        turn_id: int,
        decisions: Iterable[models.StagedPlotScheduleDecision],
    ) -> list[models.SessionPlotScheduleDecision]:
        session = self._require_session(session_id)
        turn = _positive_integer(turn_id, "turn_id")
        try:
            with self.transaction():
                return self._records.create_decisions(session.id, turn, decisions)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot decision write violated data constraints"
            ) from exc

    def delete_decisions_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_from_turn(
            session_id,
            _positive_integer(turn_id, "turn_id"),
        )

    def delete_decisions_for_turn(self, session_id: str, turn_id: int) -> int:
        return self._records.delete_for_turn(
            session_id,
            _positive_integer(turn_id, "turn_id"),
        )

    def retain_decision_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        return self._records.retain_turns(session_id, turn_ids)

    def clear_decisions(self, session_id: str) -> int:
        return self._records.clear_decisions(session_id)

    def copy_overrides(self, source_session_id: str, target_session_id: str) -> None:
        self._require_session(source_session_id)
        self._require_session(target_session_id)
        try:
            with self.transaction():
                self._records.copy_overrides(source_session_id, target_session_id)
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot override copy violated data constraints"
            ) from exc

    def copy_decisions(
        self,
        source_session_id: str,
        target_session_id: str,
        through_turn_id: int,
        *,
        decision_statuses: Collection[str],
    ) -> int:
        self._require_session(source_session_id)
        self._require_session(target_session_id)
        try:
            with self.transaction():
                return self._records.copy_decisions(
                    source_session_id,
                    target_session_id,
                    _positive_integer(through_turn_id, "through_turn_id"),
                    decision_statuses=decision_statuses,
                )
        except IntegrityError as exc:
            raise PlotScheduleDataIntegrityError(
                "plot decision copy violated data constraints"
            ) from exc

    def _require_story(self, story_id: int) -> None:
        if self._stories.get(int(story_id)) is None:
            raise FileNotFoundError(f"story not found: {story_id}")

    def _require_pool_owner(self, story_id: int, pool_id: int) -> None:
        if self.get_pool(story_id, pool_id) is None:
            raise FileNotFoundError(f"plot event pool not found in Story: {pool_id}")

    def _require_event_owner(self, story_id: int, event_id: int) -> None:
        if self.get_event(story_id, event_id) is None:
            raise FileNotFoundError(f"plot event not found in Story: {event_id}")

    def _require_outline_owner(self, story_id: int, outline_id: int) -> None:
        if self.get_outline(story_id, outline_id) is None:
            raise FileNotFoundError(f"plot outline not found in Story: {outline_id}")

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        return session


def _positive_integer(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
