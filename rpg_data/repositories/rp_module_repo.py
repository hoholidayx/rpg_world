"""Persistence for built-in RP Module catalog, Story mounts and Session overrides."""

from __future__ import annotations

from typing import Mapping

from peewee import Database, SQL

from commons.types import JsonValue
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    StoryRPModule,
)
from rpg_data.repositories._utils import (
    serialize_rp_module_config,
    to_rp_module_catalog,
    to_session_rp_module_override,
    to_story_rp_module,
)
from rpg_data.repositories.records import (
    RPModuleCatalogRecord,
    SessionRPModuleOverrideRecord,
    StoryRPModuleRecord,
    bind_database,
)


class RPModuleRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def list_catalog(self) -> list[RPModuleCatalogEntry]:
        rows = RPModuleCatalogRecord.select().order_by(
            RPModuleCatalogRecord.sort_order,
            RPModuleCatalogRecord.module_name,
        )
        return [to_rp_module_catalog(row) for row in rows]

    def get_catalog(self, module_name: str) -> RPModuleCatalogEntry | None:
        row = RPModuleCatalogRecord.get_or_none(
            RPModuleCatalogRecord.module_name == module_name
        )
        return to_rp_module_catalog(row) if row is not None else None

    def list_story(self, story_id: int) -> list[StoryRPModule]:
        rows = (
            StoryRPModuleRecord.select(StoryRPModuleRecord, RPModuleCatalogRecord)
            .join(RPModuleCatalogRecord)
            .where(StoryRPModuleRecord.story == story_id)
            .order_by(RPModuleCatalogRecord.sort_order, StoryRPModuleRecord.module_name)
        )
        return [to_story_rp_module(row) for row in rows]

    def get_story(self, story_id: int, module_name: str) -> StoryRPModule | None:
        row = StoryRPModuleRecord.get_or_none(
            (StoryRPModuleRecord.story == story_id)
            & (StoryRPModuleRecord.module_name == module_name)
        )
        return to_story_rp_module(row) if row is not None else None

    def upsert_story(
        self,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, JsonValue],
    ) -> StoryRPModule:
        row, created = StoryRPModuleRecord.get_or_create(
            story=story_id,
            module_name=module_name,
            defaults={
                "enabled": bool(enabled),
                "config_json": serialize_rp_module_config(config),
            },
        )
        if not created:
            (
                StoryRPModuleRecord.update(
                    enabled=bool(enabled),
                    config_json=serialize_rp_module_config(config),
                    version=StoryRPModuleRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(StoryRPModuleRecord.id == row.id)
                .execute()
            )
            row = StoryRPModuleRecord.get_by_id(row.id)
        return to_story_rp_module(row)

    def list_session(self, session_id: str) -> list[SessionRPModuleOverride]:
        rows = (
            SessionRPModuleOverrideRecord.select(
                SessionRPModuleOverrideRecord,
                RPModuleCatalogRecord,
            )
            .join(RPModuleCatalogRecord)
            .where(SessionRPModuleOverrideRecord.session == session_id)
            .order_by(
                RPModuleCatalogRecord.sort_order,
                SessionRPModuleOverrideRecord.module_name,
            )
        )
        return [to_session_rp_module_override(row) for row in rows]

    def get_session(
        self,
        session_id: str,
        module_name: str,
    ) -> SessionRPModuleOverride | None:
        row = SessionRPModuleOverrideRecord.get_or_none(
            (SessionRPModuleOverrideRecord.session == session_id)
            & (SessionRPModuleOverrideRecord.module_name == module_name)
        )
        return to_session_rp_module_override(row) if row is not None else None

    def upsert_session(
        self,
        session_id: str,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, JsonValue],
    ) -> SessionRPModuleOverride:
        serialized = serialize_rp_module_config(config)
        row, created = SessionRPModuleOverrideRecord.get_or_create(
            session=session_id,
            module_name=module_name,
            defaults={"enabled": enabled, "config_json": serialized},
        )
        if not created:
            (
                SessionRPModuleOverrideRecord.update(
                    enabled=enabled,
                    config_json=serialized,
                    version=SessionRPModuleOverrideRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(SessionRPModuleOverrideRecord.id == row.id)
                .execute()
            )
            row = SessionRPModuleOverrideRecord.get_by_id(row.id)
        return to_session_rp_module_override(row)

    def delete_session(self, session_id: str, module_name: str) -> int:
        return (
            SessionRPModuleOverrideRecord.delete()
            .where(
                (SessionRPModuleOverrideRecord.session == session_id)
                & (SessionRPModuleOverrideRecord.module_name == module_name)
            )
            .execute()
        )
