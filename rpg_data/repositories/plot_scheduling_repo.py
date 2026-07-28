"""Persistence for Story plot definitions and Session scheduling decisions."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping

from peewee import Database, SQL, fn

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_data.repositories.records import (
    SessionPlotEventOverrideRecord,
    SessionPlotOutlineNodeOverrideRecord,
    SessionPlotPendingInjectionRecord,
    SessionPlotSceneOpportunityRecord,
    SessionPlotScheduleDecisionRecord,
    StoryPlotEventPoolRecord,
    StoryPlotEventRecord,
    StoryPlotOutlineNodeRecord,
    StoryPlotOutlineRecord,
    bind_database,
)


class PlotSchedulingRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def list_pools(self, story_id: int) -> list[models.StoryPlotEventPool]:
        rows = (
            StoryPlotEventPoolRecord.select()
            .where(StoryPlotEventPoolRecord.story == int(story_id))
            .order_by(
                StoryPlotEventPoolRecord.priority.desc(),
                StoryPlotEventPoolRecord.id,
            )
        )
        return [_to_pool(row) for row in rows]

    def get_pool(self, pool_id: int) -> models.StoryPlotEventPool | None:
        row = StoryPlotEventPoolRecord.get_or_none(
            StoryPlotEventPoolRecord.id == int(pool_id)
        )
        return _to_pool(row) if row is not None else None

    def create_pool(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        cooldown_minutes: int,
        enabled: bool,
    ) -> models.StoryPlotEventPool:
        row = StoryPlotEventPoolRecord.create(
            story=int(story_id),
            name=name,
            description=description,
            selection_mode=selection_mode,
            priority=int(priority),
            cooldown_minutes=int(cooldown_minutes),
            enabled=bool(enabled),
        )
        return _to_pool(StoryPlotEventPoolRecord.get_by_id(row.id))

    def update_pool(
        self,
        pool_id: int,
        *,
        name: str,
        description: str,
        selection_mode: str,
        priority: int,
        cooldown_minutes: int,
        enabled: bool,
    ) -> models.StoryPlotEventPool | None:
        changed = (
            StoryPlotEventPoolRecord.update(
                name=name,
                description=description,
                selection_mode=selection_mode,
                priority=int(priority),
                cooldown_minutes=int(cooldown_minutes),
                enabled=bool(enabled),
                version=StoryPlotEventPoolRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotEventPoolRecord.id == int(pool_id))
            .execute()
        )
        return self.get_pool(pool_id) if changed else None

    def delete_pool(self, pool_id: int) -> int:
        return int(
            StoryPlotEventPoolRecord.delete()
            .where(StoryPlotEventPoolRecord.id == int(pool_id))
            .execute()
        )

    def list_events(
        self,
        story_id: int,
        *,
        pool_id: int | None = None,
    ) -> list[models.StoryPlotEvent]:
        query = StoryPlotEventRecord.select().where(
            StoryPlotEventRecord.story == int(story_id)
        )
        if pool_id is not None:
            query = query.where(StoryPlotEventRecord.pool == int(pool_id))
        rows = query.order_by(
            StoryPlotEventRecord.pool,
            StoryPlotEventRecord.position,
            StoryPlotEventRecord.id,
        )
        return [_to_event(row) for row in rows]

    def get_event(self, event_id: int) -> models.StoryPlotEvent | None:
        row = StoryPlotEventRecord.get_or_none(
            StoryPlotEventRecord.id == int(event_id)
        )
        return _to_event(row) if row is not None else None

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
        deadline_time: SceneTime | None,
        position: int,
        enabled: bool,
        allow_repeat: bool,
        repeat_cooldown_minutes: int,
    ) -> models.StoryPlotEvent:
        row = StoryPlotEventRecord.create(
            story=int(story_id),
            pool=int(pool_id),
            title=title,
            description=description,
            directive=directive,
            suitability_hint=suitability_hint,
            dispatch_mode=dispatch_mode,
            scheduled_time_json=_serialize_time(scheduled_time),
            deadline_time_json=_serialize_time(deadline_time),
            position=int(position),
            enabled=bool(enabled),
            allow_repeat=bool(allow_repeat),
            repeat_cooldown_minutes=int(repeat_cooldown_minutes),
        )
        return _to_event(StoryPlotEventRecord.get_by_id(row.id))

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
        deadline_time: SceneTime | None,
        position: int,
        enabled: bool,
        allow_repeat: bool,
        repeat_cooldown_minutes: int,
    ) -> models.StoryPlotEvent | None:
        changed = (
            StoryPlotEventRecord.update(
                pool=int(pool_id),
                title=title,
                description=description,
                directive=directive,
                suitability_hint=suitability_hint,
                dispatch_mode=dispatch_mode,
                scheduled_time_json=_serialize_time(scheduled_time),
                deadline_time_json=_serialize_time(deadline_time),
                position=int(position),
                enabled=bool(enabled),
                allow_repeat=bool(allow_repeat),
                repeat_cooldown_minutes=int(repeat_cooldown_minutes),
                version=StoryPlotEventRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotEventRecord.id == int(event_id))
            .execute()
        )
        return self.get_event(event_id) if changed else None

    def set_event_position(self, event_id: int, position: int) -> int:
        return int(
            StoryPlotEventRecord.update(
                position=int(position),
                version=StoryPlotEventRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotEventRecord.id == int(event_id))
            .execute()
        )

    def delete_event(self, event_id: int) -> int:
        return int(
            StoryPlotEventRecord.delete()
            .where(StoryPlotEventRecord.id == int(event_id))
            .execute()
        )

    def list_outlines(self, story_id: int) -> list[models.StoryPlotOutline]:
        rows = (
            StoryPlotOutlineRecord.select()
            .where(StoryPlotOutlineRecord.story == int(story_id))
            .order_by(
                StoryPlotOutlineRecord.priority.desc(),
                StoryPlotOutlineRecord.id,
            )
        )
        nodes = self.list_nodes(story_id)
        by_outline: dict[int, list[models.StoryPlotOutlineNode]] = {}
        for node in nodes:
            by_outline.setdefault(node.outline_id, []).append(node)
        return [
            _to_outline(row, tuple(by_outline.get(int(row.id), ())))
            for row in rows
        ]

    def get_outline(self, outline_id: int) -> models.StoryPlotOutline | None:
        row = StoryPlotOutlineRecord.get_or_none(
            StoryPlotOutlineRecord.id == int(outline_id)
        )
        if row is None:
            return None
        return _to_outline(
            row,
            tuple(self.list_nodes(int(row.story_id), outline_id=int(row.id))),
        )

    def create_outline(
        self,
        *,
        story_id: int,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotOutline:
        row = StoryPlotOutlineRecord.create(
            story=int(story_id),
            name=name,
            description=description,
            priority=int(priority),
            enabled=bool(enabled),
        )
        result = self.get_outline(int(row.id))
        if result is None:  # pragma: no cover - create/get invariant
            raise RuntimeError("created plot outline disappeared")
        return result

    def update_outline(
        self,
        outline_id: int,
        *,
        name: str,
        description: str,
        priority: int,
        enabled: bool,
    ) -> models.StoryPlotOutline | None:
        changed = (
            StoryPlotOutlineRecord.update(
                name=name,
                description=description,
                priority=int(priority),
                enabled=bool(enabled),
                version=StoryPlotOutlineRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotOutlineRecord.id == int(outline_id))
            .execute()
        )
        return self.get_outline(outline_id) if changed else None

    def delete_outline(self, outline_id: int) -> int:
        return int(
            StoryPlotOutlineRecord.delete()
            .where(StoryPlotOutlineRecord.id == int(outline_id))
            .execute()
        )

    def list_nodes(
        self,
        story_id: int,
        *,
        outline_id: int | None = None,
    ) -> list[models.StoryPlotOutlineNode]:
        query = StoryPlotOutlineNodeRecord.select().where(
            StoryPlotOutlineNodeRecord.story == int(story_id)
        )
        if outline_id is not None:
            query = query.where(StoryPlotOutlineNodeRecord.outline == int(outline_id))
        rows = query.order_by(
            StoryPlotOutlineNodeRecord.outline,
            StoryPlotOutlineNodeRecord.position,
            StoryPlotOutlineNodeRecord.id,
        )
        return [_to_node(row) for row in rows]

    def get_node(self, node_id: int) -> models.StoryPlotOutlineNode | None:
        row = StoryPlotOutlineNodeRecord.get_or_none(
            StoryPlotOutlineNodeRecord.id == int(node_id)
        )
        return _to_node(row) if row is not None else None

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
        row = StoryPlotOutlineNodeRecord.create(
            story=int(story_id),
            outline=int(outline_id),
            event=int(event_id),
            scheduled_time_json=_serialize_time(scheduled_time),
            dispatch_mode=dispatch_mode,
            position=int(position),
            enabled=bool(enabled),
        )
        return _to_node(StoryPlotOutlineNodeRecord.get_by_id(row.id))

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
        changed = (
            StoryPlotOutlineNodeRecord.update(
                event=int(event_id),
                scheduled_time_json=_serialize_time(scheduled_time),
                dispatch_mode=dispatch_mode,
                position=int(position),
                enabled=bool(enabled),
                version=StoryPlotOutlineNodeRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotOutlineNodeRecord.id == int(node_id))
            .execute()
        )
        return self.get_node(node_id) if changed else None

    def set_node_position(self, node_id: int, position: int) -> int:
        return int(
            StoryPlotOutlineNodeRecord.update(
                position=int(position),
                version=StoryPlotOutlineNodeRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryPlotOutlineNodeRecord.id == int(node_id))
            .execute()
        )

    def delete_node(self, node_id: int) -> int:
        return int(
            StoryPlotOutlineNodeRecord.delete()
            .where(StoryPlotOutlineNodeRecord.id == int(node_id))
            .execute()
        )

    def list_overrides(self, session_id: str) -> models.SessionPlotOverrides:
        event_ids = frozenset(
            int(row.event_id)
            for row in SessionPlotEventOverrideRecord.select().where(
                SessionPlotEventOverrideRecord.session == str(session_id)
            )
        )
        node_ids = frozenset(
            int(row.node_id)
            for row in SessionPlotOutlineNodeOverrideRecord.select().where(
                SessionPlotOutlineNodeOverrideRecord.session == str(session_id)
            )
        )
        return models.SessionPlotOverrides(
            session_id=str(session_id),
            disabled_event_ids=event_ids,
            disabled_outline_node_ids=node_ids,
        )

    def set_event_disabled(self, session_id: str, event_id: int, disabled: bool) -> None:
        query = (
            SessionPlotEventOverrideRecord.delete()
            .where(
                (SessionPlotEventOverrideRecord.session == str(session_id))
                & (SessionPlotEventOverrideRecord.event == int(event_id))
            )
        )
        if not disabled:
            query.execute()
            return
        SessionPlotEventOverrideRecord.insert(
            session=str(session_id),
            event=int(event_id),
            disabled=True,
        ).on_conflict_replace().execute()

    def set_node_disabled(self, session_id: str, node_id: int, disabled: bool) -> None:
        query = (
            SessionPlotOutlineNodeOverrideRecord.delete()
            .where(
                (SessionPlotOutlineNodeOverrideRecord.session == str(session_id))
                & (SessionPlotOutlineNodeOverrideRecord.node == int(node_id))
            )
        )
        if not disabled:
            query.execute()
            return
        SessionPlotOutlineNodeOverrideRecord.insert(
            session=str(session_id),
            node=int(node_id),
            disabled=True,
        ).on_conflict_replace().execute()

    def get_pending_injection(
        self,
        session_id: str,
    ) -> models.SessionPlotPendingInjection | None:
        row = SessionPlotPendingInjectionRecord.get_or_none(
            (
                SessionPlotPendingInjectionRecord.session
                == str(session_id)
            )
            & (SessionPlotPendingInjectionRecord.active == True)  # noqa: E712
        )
        return _to_pending_injection(row) if row is not None else None

    def create_pending_injection(
        self,
        session_id: str,
        values: models.PendingPlotInjectionWrite,
    ) -> models.SessionPlotPendingInjection | None:
        inserted_or_reactivated = int(
            SessionPlotPendingInjectionRecord.insert(
                session=str(session_id),
                story=int(values.story_id),
                source_event_id=int(values.source_event_id),
                source_event_version=int(values.source_event_version),
                source_pool_id=int(values.source_pool_id),
                source_pool_name=values.source_pool_name,
                event_title=values.event_title,
                directive=values.directive,
                event_snapshot_json=_serialize_mapping(values.event_snapshot),
                requested_turn_id=int(values.requested_turn_id),
                active=True,
            )
            .on_conflict(
                conflict_target=[SessionPlotPendingInjectionRecord.session],
                update={
                    SessionPlotPendingInjectionRecord.story: int(
                        values.story_id
                    ),
                    SessionPlotPendingInjectionRecord.source_event_id: int(
                        values.source_event_id
                    ),
                    SessionPlotPendingInjectionRecord.source_event_version: int(
                        values.source_event_version
                    ),
                    SessionPlotPendingInjectionRecord.source_pool_id: int(
                        values.source_pool_id
                    ),
                    SessionPlotPendingInjectionRecord.source_pool_name: (
                        values.source_pool_name
                    ),
                    SessionPlotPendingInjectionRecord.event_title: (
                        values.event_title
                    ),
                    SessionPlotPendingInjectionRecord.directive: (
                        values.directive
                    ),
                    SessionPlotPendingInjectionRecord.event_snapshot_json: (
                        _serialize_mapping(values.event_snapshot)
                    ),
                    SessionPlotPendingInjectionRecord.requested_turn_id: int(
                        values.requested_turn_id
                    ),
                    SessionPlotPendingInjectionRecord.active: True,
                    SessionPlotPendingInjectionRecord.version: (
                        SessionPlotPendingInjectionRecord.version + 1
                    ),
                    SessionPlotPendingInjectionRecord.created_at: SQL(
                        "CURRENT_TIMESTAMP"
                    ),
                    SessionPlotPendingInjectionRecord.updated_at: SQL(
                        "CURRENT_TIMESTAMP"
                    ),
                },
                where=(
                    SessionPlotPendingInjectionRecord.active == False  # noqa: E712
                ),
            )
            .as_rowcount()
            .execute()
        )
        if inserted_or_reactivated != 1:
            return None
        pending = self.get_pending_injection(session_id)
        if pending is None:  # pragma: no cover - database create contract
            raise RuntimeError("created pending Plot injection could not be reloaded")
        return pending

    def update_pending_injection(
        self,
        session_id: str,
        *,
        expected_version: int,
        values: models.PendingPlotInjectionWrite,
    ) -> models.SessionPlotPendingInjection | None:
        changed = (
            SessionPlotPendingInjectionRecord.update(
                story=int(values.story_id),
                source_event_id=int(values.source_event_id),
                source_event_version=int(values.source_event_version),
                source_pool_id=int(values.source_pool_id),
                source_pool_name=values.source_pool_name,
                event_title=values.event_title,
                directive=values.directive,
                event_snapshot_json=_serialize_mapping(values.event_snapshot),
                requested_turn_id=int(values.requested_turn_id),
                version=SessionPlotPendingInjectionRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionPlotPendingInjectionRecord.session == str(session_id))
                & (
                    SessionPlotPendingInjectionRecord.active
                    == True  # noqa: E712
                )
                & (
                    SessionPlotPendingInjectionRecord.version
                    == int(expected_version)
                )
            )
            .execute()
        )
        return self.get_pending_injection(session_id) if changed else None

    def delete_pending_injection(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
    ) -> int:
        query = SessionPlotPendingInjectionRecord.update(
            active=False,
            version=SessionPlotPendingInjectionRecord.version + 1,
            updated_at=SQL("CURRENT_TIMESTAMP"),
        ).where(
            (
                SessionPlotPendingInjectionRecord.session
                == str(session_id)
            )
            & (SessionPlotPendingInjectionRecord.active == True)  # noqa: E712
        )
        if expected_version is not None:
            query = query.where(
                SessionPlotPendingInjectionRecord.version == int(expected_version)
            )
        return int(query.execute())

    def delete_pending_injection_requested_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return int(
            SessionPlotPendingInjectionRecord.update(
                active=False,
                version=SessionPlotPendingInjectionRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionPlotPendingInjectionRecord.session == str(session_id))
                & (
                    SessionPlotPendingInjectionRecord.active
                    == True  # noqa: E712
                )
                & (
                    SessionPlotPendingInjectionRecord.requested_turn_id
                    == int(turn_id)
                )
            )
            .execute()
        )

    def delete_pending_injection_requested_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return int(
            SessionPlotPendingInjectionRecord.update(
                active=False,
                version=SessionPlotPendingInjectionRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionPlotPendingInjectionRecord.session == str(session_id))
                & (
                    SessionPlotPendingInjectionRecord.active
                    == True  # noqa: E712
                )
                & (
                    SessionPlotPendingInjectionRecord.requested_turn_id
                    >= int(turn_id)
                )
            )
            .execute()
        )

    def retain_pending_injection_requested_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        query = SessionPlotPendingInjectionRecord.update(
            active=False,
            version=SessionPlotPendingInjectionRecord.version + 1,
            updated_at=SQL("CURRENT_TIMESTAMP"),
        ).where(
            (
                SessionPlotPendingInjectionRecord.session
                == str(session_id)
            )
            & (SessionPlotPendingInjectionRecord.active == True)  # noqa: E712
        )
        if ids:
            query = query.where(
                ~(
                    SessionPlotPendingInjectionRecord.requested_turn_id.in_(
                        ids
                    )
                )
            )
        return int(query.execute())

    def get_scene_opportunity(
        self,
        session_id: str,
    ) -> models.SessionPlotSceneOpportunity | None:
        row = SessionPlotSceneOpportunityRecord.get_or_none(
            SessionPlotSceneOpportunityRecord.session == str(session_id)
        )
        return _to_scene_opportunity(row) if row is not None else None

    def create_scene_opportunity(
        self,
        session_id: str,
        *,
        source_turn_id: int,
    ) -> models.SessionPlotSceneOpportunity:
        SessionPlotSceneOpportunityRecord.create(
            session=str(session_id),
            source_turn_id=int(source_turn_id),
        )
        opportunity = self.get_scene_opportunity(session_id)
        if opportunity is None:  # pragma: no cover - database create contract
            raise RuntimeError("created Plot Scene opportunity could not be reloaded")
        return opportunity

    def update_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int,
        source_turn_id: int,
    ) -> models.SessionPlotSceneOpportunity | None:
        changed = (
            SessionPlotSceneOpportunityRecord.update(
                source_turn_id=int(source_turn_id),
                version=SessionPlotSceneOpportunityRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionPlotSceneOpportunityRecord.session == str(session_id))
                & (
                    SessionPlotSceneOpportunityRecord.version
                    == int(expected_version)
                )
            )
            .execute()
        )
        return self.get_scene_opportunity(session_id) if changed else None

    def delete_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
    ) -> int:
        query = SessionPlotSceneOpportunityRecord.delete().where(
            SessionPlotSceneOpportunityRecord.session == str(session_id)
        )
        if expected_version is not None:
            query = query.where(
                SessionPlotSceneOpportunityRecord.version == int(expected_version)
            )
        return int(query.execute())

    def delete_scene_opportunity_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return int(
            SessionPlotSceneOpportunityRecord.delete()
            .where(
                (SessionPlotSceneOpportunityRecord.session == str(session_id))
                & (
                    SessionPlotSceneOpportunityRecord.source_turn_id
                    == int(turn_id)
                )
            )
            .execute()
        )

    def delete_scene_opportunity_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return int(
            SessionPlotSceneOpportunityRecord.delete()
            .where(
                (SessionPlotSceneOpportunityRecord.session == str(session_id))
                & (
                    SessionPlotSceneOpportunityRecord.source_turn_id
                    >= int(turn_id)
                )
            )
            .execute()
        )

    def retain_scene_opportunity_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        query = SessionPlotSceneOpportunityRecord.delete().where(
            SessionPlotSceneOpportunityRecord.session == str(session_id)
        )
        if ids:
            query = query.where(
                ~(SessionPlotSceneOpportunityRecord.source_turn_id.in_(ids))
            )
        return int(query.execute())

    def list_decisions(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[models.SessionPlotScheduleDecision]:
        query = SessionPlotScheduleDecisionRecord.select().where(
            SessionPlotScheduleDecisionRecord.session == str(session_id)
        )
        if before_id is not None:
            query = query.where(SessionPlotScheduleDecisionRecord.id < int(before_id))
        query = query.order_by(SessionPlotScheduleDecisionRecord.id.desc())
        if limit is not None:
            query = query.limit(int(limit))
        return [_to_decision(row) for row in query]

    def list_latest_decisions_by_container(
        self,
        session_id: str,
        *,
        source_kind: str,
        decision_statuses: Collection[str],
        selection_origins: Collection[str],
    ) -> list[models.SessionPlotScheduleDecision]:
        statuses = tuple(sorted(set(decision_statuses)))
        origins = tuple(sorted(set(selection_origins)))
        if not statuses or not origins:
            return []
        ranked = (
            SessionPlotScheduleDecisionRecord
            .select(
                SessionPlotScheduleDecisionRecord.id.alias("decision_id"),
                fn.ROW_NUMBER().over(
                    partition_by=[
                        SessionPlotScheduleDecisionRecord.container_id
                    ],
                    order_by=[
                        SessionPlotScheduleDecisionRecord.turn_id.desc(),
                        SessionPlotScheduleDecisionRecord.id.desc(),
                    ],
                ).alias("container_rank"),
            )
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (
                    SessionPlotScheduleDecisionRecord.source_kind
                    == str(source_kind)
                )
                & (
                    SessionPlotScheduleDecisionRecord.decision_status.in_(
                        statuses
                    )
                )
                & (
                    SessionPlotScheduleDecisionRecord.selection_origin.in_(
                        origins
                    )
                )
            )
            .cte("ranked_plot_container_decisions")
        )
        rows = (
            SessionPlotScheduleDecisionRecord
            .select()
            .join(
                ranked,
                on=(
                    SessionPlotScheduleDecisionRecord.id
                    == ranked.c.decision_id
                ),
            )
            .where(ranked.c.container_rank == 1)
            .with_cte(ranked)
            .order_by(
                SessionPlotScheduleDecisionRecord.container_id,
            )
        )
        return [_to_decision(row) for row in rows]

    def list_decisions_for_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> list[models.SessionPlotScheduleDecision]:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        if not ids:
            return []
        rows = (
            SessionPlotScheduleDecisionRecord
            .select()
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (SessionPlotScheduleDecisionRecord.turn_id.in_(ids))
            )
            .order_by(
                SessionPlotScheduleDecisionRecord.turn_id,
                SessionPlotScheduleDecisionRecord.id,
            )
        )
        return [_to_decision(row) for row in rows]

    def summarize_decisions(
        self,
        session_id: str,
        *,
        decision_statuses: Collection[str],
    ) -> models.SessionPlotDecisionAggregates:
        statuses = tuple(sorted(set(decision_statuses)))
        if not statuses:
            return models.SessionPlotDecisionAggregates()

        event_count = fn.COUNT(SessionPlotScheduleDecisionRecord.id).alias(
            "decision_count"
        )
        event_latest_turn = fn.MAX(
            SessionPlotScheduleDecisionRecord.turn_id
        ).alias("latest_turn_id")
        event_query = (
            SessionPlotScheduleDecisionRecord
            .select(
                SessionPlotScheduleDecisionRecord.event_id,
                event_count,
                event_latest_turn,
            )
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (
                    SessionPlotScheduleDecisionRecord.decision_status.in_(
                        statuses
                    )
                )
            )
            .group_by(SessionPlotScheduleDecisionRecord.event_id)
            .order_by(SessionPlotScheduleDecisionRecord.event_id)
        )

        source_count = fn.COUNT(SessionPlotScheduleDecisionRecord.id).alias(
            "decision_count"
        )
        source_latest_turn = fn.MAX(
            SessionPlotScheduleDecisionRecord.turn_id
        ).alias("latest_turn_id")
        source_query = (
            SessionPlotScheduleDecisionRecord
            .select(
                SessionPlotScheduleDecisionRecord.source_kind,
                SessionPlotScheduleDecisionRecord.source_id,
                source_count,
                source_latest_turn,
            )
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (
                    SessionPlotScheduleDecisionRecord.decision_status.in_(
                        statuses
                    )
                )
            )
            .group_by(
                SessionPlotScheduleDecisionRecord.source_kind,
                SessionPlotScheduleDecisionRecord.source_id,
            )
            .order_by(
                SessionPlotScheduleDecisionRecord.source_kind,
                SessionPlotScheduleDecisionRecord.source_id,
            )
        )
        with self._database.atomic():
            event_rows = list(event_query.dicts())
            source_rows = list(source_query.dicts())
        return models.SessionPlotDecisionAggregates(
            events=tuple(
                models.SessionPlotEventDecisionAggregate(
                    event_id=int(row["event_id"]),
                    decision_count=int(row["decision_count"]),
                    latest_turn_id=int(row["latest_turn_id"]),
                )
                for row in event_rows
            ),
            sources=tuple(
                models.SessionPlotSourceDecisionAggregate(
                    source_kind=str(row["source_kind"]),
                    source_id=int(row["source_id"]),
                    decision_count=int(row["decision_count"]),
                    latest_turn_id=int(row["latest_turn_id"]),
                )
                for row in source_rows
            ),
        )

    def create_decisions(
        self,
        session_id: str,
        turn_id: int,
        decisions: Iterable[models.StagedPlotScheduleDecision],
    ) -> list[models.SessionPlotScheduleDecision]:
        created: list[models.SessionPlotScheduleDecision] = []
        for decision in decisions:
            row = SessionPlotScheduleDecisionRecord.create(
                session=str(session_id),
                turn_id=int(turn_id),
                source_kind=decision.source_kind,
                source_id=int(decision.source_id),
                event_id=int(decision.event_id),
                container_id=int(decision.container_id),
                decision_status=decision.decision_status,
                dispatch_mode=decision.dispatch_mode,
                selection_origin=decision.selection_origin,
                scene_time_json=_serialize_time(decision.scene_time),
                scene_time_ordinal=(
                    decision.scene_time.ordinal_minutes
                    if decision.scene_time is not None
                    else None
                ),
                event_snapshot_json=json.dumps(
                    dict(decision.event_snapshot),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                reason=decision.reason,
                error_code=decision.error_code,
                error_message=decision.error_message,
            )
            created.append(_to_decision(SessionPlotScheduleDecisionRecord.get_by_id(row.id)))
        return created

    def delete_from_turn(self, session_id: str, turn_id: int) -> int:
        return int(
            SessionPlotScheduleDecisionRecord.delete()
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (SessionPlotScheduleDecisionRecord.turn_id >= int(turn_id))
            )
            .execute()
        )

    def delete_for_turn(self, session_id: str, turn_id: int) -> int:
        return int(
            SessionPlotScheduleDecisionRecord.delete()
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(session_id))
                & (SessionPlotScheduleDecisionRecord.turn_id == int(turn_id))
            )
            .execute()
        )

    def retain_turns(self, session_id: str, turn_ids: Iterable[int]) -> int:
        ids = sorted({int(turn_id) for turn_id in turn_ids if int(turn_id) > 0})
        query = SessionPlotScheduleDecisionRecord.delete().where(
            SessionPlotScheduleDecisionRecord.session == str(session_id)
        )
        if ids:
            query = query.where(~(SessionPlotScheduleDecisionRecord.turn_id.in_(ids)))
        return int(query.execute())

    def clear_decisions(self, session_id: str) -> int:
        return int(
            SessionPlotScheduleDecisionRecord.delete()
            .where(SessionPlotScheduleDecisionRecord.session == str(session_id))
            .execute()
        )

    def copy_decisions(
        self,
        source_session_id: str,
        target_session_id: str,
        through_turn_id: int,
        *,
        decision_statuses: Collection[str],
    ) -> int:
        statuses = tuple(sorted(set(decision_statuses)))
        if not statuses:
            return 0
        rows = (
            SessionPlotScheduleDecisionRecord.select()
            .where(
                (SessionPlotScheduleDecisionRecord.session == str(source_session_id))
                & (SessionPlotScheduleDecisionRecord.turn_id <= int(through_turn_id))
                & (SessionPlotScheduleDecisionRecord.decision_status.in_(statuses))
            )
            .order_by(SessionPlotScheduleDecisionRecord.id)
        )
        count = 0
        for row in rows:
            SessionPlotScheduleDecisionRecord.create(
                session=str(target_session_id),
                turn_id=int(row.turn_id),
                source_kind=str(row.source_kind),
                source_id=int(row.source_id),
                event_id=int(row.event_id),
                container_id=int(row.container_id),
                decision_status=str(row.decision_status),
                dispatch_mode=str(row.dispatch_mode),
                selection_origin=str(row.selection_origin),
                scene_time_json=(
                    str(row.scene_time_json)
                    if row.scene_time_json is not None
                    else None
                ),
                scene_time_ordinal=(
                    int(row.scene_time_ordinal)
                    if row.scene_time_ordinal is not None
                    else None
                ),
                event_snapshot_json=str(row.event_snapshot_json),
                reason=str(row.reason or ""),
                error_code=str(row.error_code or ""),
                error_message=str(row.error_message or ""),
            )
            count += 1
        return count

    def copy_overrides(self, source_session_id: str, target_session_id: str) -> None:
        source = self.list_overrides(source_session_id)
        for event_id in source.disabled_event_ids:
            self.set_event_disabled(target_session_id, event_id, True)
        for node_id in source.disabled_outline_node_ids:
            self.set_node_disabled(target_session_id, node_id, True)


def _serialize_time(value: SceneTime | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _serialize_mapping(value: Mapping[str, object]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_time(value: str | None, *, required: bool) -> SceneTime | None:
    if value is None or not str(value).strip():
        if required:
            raise ValueError("persisted plot schedule is missing SceneTime")
        return None
    raw = json.loads(str(value))
    if not isinstance(raw, Mapping):
        raise ValueError("persisted SceneTime must be an object")
    return SceneTime.from_mapping(raw)


def _to_pool(row: StoryPlotEventPoolRecord) -> models.StoryPlotEventPool:
    return models.StoryPlotEventPool(
        id=int(row.id),
        story_id=int(row.story_id),
        name=str(row.name),
        description=str(row.description or ""),
        selection_mode=str(row.selection_mode),
        priority=int(row.priority),
        cooldown_minutes=int(row.cooldown_minutes),
        enabled=bool(row.enabled),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_event(row: StoryPlotEventRecord) -> models.StoryPlotEvent:
    return models.StoryPlotEvent(
        id=int(row.id),
        story_id=int(row.story_id),
        pool_id=int(row.pool_id),
        title=str(row.title),
        directive=str(row.directive),
        description=str(row.description or ""),
        suitability_hint=str(row.suitability_hint or ""),
        dispatch_mode=str(row.dispatch_mode),
        scheduled_time=_parse_time(row.scheduled_time_json, required=False),
        deadline_time=_parse_time(row.deadline_time_json, required=False),
        position=int(row.position),
        enabled=bool(row.enabled),
        allow_repeat=bool(row.allow_repeat),
        repeat_cooldown_minutes=int(row.repeat_cooldown_minutes),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_node(row: StoryPlotOutlineNodeRecord) -> models.StoryPlotOutlineNode:
    scheduled_time = _parse_time(row.scheduled_time_json, required=True)
    if scheduled_time is None:  # pragma: no cover - required above
        raise ValueError("persisted outline node is missing SceneTime")
    return models.StoryPlotOutlineNode(
        id=int(row.id),
        story_id=int(row.story_id),
        outline_id=int(row.outline_id),
        event_id=int(row.event_id),
        scheduled_time=scheduled_time,
        dispatch_mode=str(row.dispatch_mode),
        position=int(row.position),
        enabled=bool(row.enabled),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_outline(
    row: StoryPlotOutlineRecord,
    nodes: tuple[models.StoryPlotOutlineNode, ...],
) -> models.StoryPlotOutline:
    return models.StoryPlotOutline(
        id=int(row.id),
        story_id=int(row.story_id),
        name=str(row.name),
        description=str(row.description or ""),
        priority=int(row.priority),
        enabled=bool(row.enabled),
        nodes=nodes,
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_pending_injection(
    row: SessionPlotPendingInjectionRecord,
) -> models.SessionPlotPendingInjection:
    snapshot = json.loads(str(row.event_snapshot_json))
    if not isinstance(snapshot, Mapping):
        raise ValueError("persisted pending Plot event snapshot must be an object")
    return models.SessionPlotPendingInjection(
        session_id=str(row.session_id),
        story_id=int(row.story_id),
        source_event_id=int(row.source_event_id),
        source_event_version=int(row.source_event_version),
        source_pool_id=int(row.source_pool_id),
        source_pool_name=str(row.source_pool_name),
        event_title=str(row.event_title),
        directive=str(row.directive),
        event_snapshot=dict(snapshot),
        requested_turn_id=int(row.requested_turn_id),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_scene_opportunity(
    row: SessionPlotSceneOpportunityRecord,
) -> models.SessionPlotSceneOpportunity:
    return models.SessionPlotSceneOpportunity(
        session_id=str(row.session_id),
        source_turn_id=int(row.source_turn_id),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_decision(
    row: SessionPlotScheduleDecisionRecord,
) -> models.SessionPlotScheduleDecision:
    selection_origin = str(row.selection_origin)
    scene_time = _parse_time(
        row.scene_time_json,
        required=(
            selection_origin == models.PLOT_SELECTION_ORIGIN_SCHEDULER
        ),
    )
    snapshot = json.loads(str(row.event_snapshot_json))
    if not isinstance(snapshot, Mapping):
        raise ValueError("persisted plot event snapshot must be an object")
    return models.SessionPlotScheduleDecision(
        id=int(row.id),
        session_id=str(row.session_id),
        turn_id=int(row.turn_id),
        source_kind=str(row.source_kind),
        source_id=int(row.source_id),
        event_id=int(row.event_id),
        container_id=int(row.container_id),
        decision_status=str(row.decision_status),
        dispatch_mode=str(row.dispatch_mode),
        selection_origin=selection_origin,
        scene_time=scene_time,
        scene_time_ordinal=(
            int(row.scene_time_ordinal)
            if row.scene_time_ordinal is not None
            else None
        ),
        event_snapshot=dict(snapshot),
        reason=str(row.reason or ""),
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )
