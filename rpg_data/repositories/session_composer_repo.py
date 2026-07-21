"""Persistence for turn modes, narrative styles, and story quick replies."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database, SQL

from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
    WorkspaceTurnMode,
    WorkspaceTurnModeSeed,
)
from rpg_data.repositories._utils import (
    to_narrative_style,
    to_story_narrative_style,
    to_story_quick_reply,
    to_workspace_turn_mode,
)
from rpg_data.repositories.records import (
    NarrativeStyleRecord,
    StoryNarrativeStyleRecord,
    StoryQuickReplyRecord,
    WorkspaceTurnModeRecord,
    bind_database,
)


class SessionComposerRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def ensure_workspace_modes(
        self,
        workspace_id: str,
        seeds: Iterable[WorkspaceTurnModeSeed],
    ) -> list[WorkspaceTurnMode]:
        for seed in seeds:
            WorkspaceTurnModeRecord.get_or_create(
                workspace=workspace_id,
                mode=seed.mode,
                defaults={
                    "short_name": seed.short_name,
                    "prompt": seed.prompt,
                    "sort_order": seed.sort_order,
                },
            )
        return self.list_workspace_modes(workspace_id)

    def list_workspace_modes(self, workspace_id: str) -> list[WorkspaceTurnMode]:
        rows = (
            WorkspaceTurnModeRecord.select()
            .where(WorkspaceTurnModeRecord.workspace == workspace_id)
            .order_by(WorkspaceTurnModeRecord.sort_order, WorkspaceTurnModeRecord.mode)
        )
        return [to_workspace_turn_mode(row) for row in rows]

    def update_workspace_mode(
        self,
        workspace_id: str,
        mode: str,
        *,
        short_name: str,
        prompt: str,
    ) -> WorkspaceTurnMode | None:
        updated = (
            WorkspaceTurnModeRecord.update(
                short_name=short_name,
                prompt=prompt,
                version=WorkspaceTurnModeRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (WorkspaceTurnModeRecord.workspace == workspace_id)
                & (WorkspaceTurnModeRecord.mode == mode)
            )
            .execute()
        )
        if not updated:
            return None
        row = WorkspaceTurnModeRecord.get(
            (WorkspaceTurnModeRecord.workspace == workspace_id)
            & (WorkspaceTurnModeRecord.mode == mode)
        )
        return to_workspace_turn_mode(row)

    def list_styles(self, workspace_id: str) -> list[NarrativeStyle]:
        rows = (
            NarrativeStyleRecord.select()
            .where(NarrativeStyleRecord.workspace == workspace_id)
            .order_by(NarrativeStyleRecord.sort_order, NarrativeStyleRecord.id)
        )
        return [to_narrative_style(row) for row in rows]

    def get_style(self, style_id: int) -> NarrativeStyle | None:
        row = NarrativeStyleRecord.get_or_none(NarrativeStyleRecord.id == int(style_id))
        return to_narrative_style(row) if row is not None else None

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int,
    ) -> NarrativeStyle:
        row = NarrativeStyleRecord.create(
            workspace=workspace_id,
            name=name,
            prompt=prompt,
            sort_order=int(sort_order),
        )
        return to_narrative_style(row)

    def update_style(
        self,
        style_id: int,
        *,
        name: str | None = None,
        prompt: str | None = None,
        sort_order: int | None = None,
    ) -> NarrativeStyle | None:
        fields: dict[str, object] = {}
        if name is not None:
            fields["name"] = name
        if prompt is not None:
            fields["prompt"] = prompt
        if sort_order is not None:
            fields["sort_order"] = int(sort_order)
        if not fields:
            return self.get_style(style_id)
        fields["version"] = NarrativeStyleRecord.version + 1
        fields["updated_at"] = SQL("CURRENT_TIMESTAMP")
        updated = (
            NarrativeStyleRecord.update(**fields)
            .where(NarrativeStyleRecord.id == int(style_id))
            .execute()
        )
        return self.get_style(style_id) if updated else None

    def delete_style(self, style_id: int) -> bool:
        return bool(
            NarrativeStyleRecord.delete()
            .where(NarrativeStyleRecord.id == int(style_id))
            .execute()
        )

    def mount_story_styles(
        self,
        workspace_id: str,
        story_id: int,
        style_ids: Iterable[int],
    ) -> list[StoryNarrativeStyle]:
        requested = {int(value) for value in style_ids}
        styles = {
            style.id: style
            for style in self.list_styles(workspace_id)
            if style.id in requested
        }
        for style in styles.values():
            StoryNarrativeStyleRecord.get_or_create(
                workspace=workspace_id,
                story=story_id,
                narrative_style=style.id,
                defaults={"is_base": False, "sort_order": style.sort_order},
            )
        return self.list_story_styles(story_id)

    def list_story_styles(self, story_id: int) -> list[StoryNarrativeStyle]:
        rows = (
            StoryNarrativeStyleRecord.select(
                StoryNarrativeStyleRecord,
                NarrativeStyleRecord,
            )
            .join(NarrativeStyleRecord)
            .where(StoryNarrativeStyleRecord.story == int(story_id))
            .order_by(
                StoryNarrativeStyleRecord.sort_order,
                StoryNarrativeStyleRecord.id,
            )
        )
        return [to_story_narrative_style(row) for row in rows]

    def get_story_style_mount(
        self,
        story_id: int,
        style_id: int,
    ) -> StoryNarrativeStyle | None:
        row = StoryNarrativeStyleRecord.get_or_none(
            (StoryNarrativeStyleRecord.story == int(story_id))
            & (StoryNarrativeStyleRecord.narrative_style == int(style_id))
        )
        return to_story_narrative_style(row) if row is not None else None

    def unmount_story_style(self, story_id: int, mount_id: int) -> bool:
        return bool(
            StoryNarrativeStyleRecord.delete()
            .where(
                (StoryNarrativeStyleRecord.story == int(story_id))
                & (StoryNarrativeStyleRecord.id == int(mount_id))
            )
            .execute()
        )

    def set_story_base_style(
        self,
        story_id: int,
        mount_id: int | None,
    ) -> StoryNarrativeStyle | None:
        with self._database.atomic():
            (
                StoryNarrativeStyleRecord.update(
                    is_base=False,
                    version=StoryNarrativeStyleRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (StoryNarrativeStyleRecord.story == int(story_id))
                    & (StoryNarrativeStyleRecord.is_base == True)  # noqa: E712
                )
                .execute()
            )
            if mount_id is None:
                return None
            updated = (
                StoryNarrativeStyleRecord.update(
                    is_base=True,
                    version=StoryNarrativeStyleRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (StoryNarrativeStyleRecord.story == int(story_id))
                    & (StoryNarrativeStyleRecord.id == int(mount_id))
                )
                .execute()
            )
            if not updated:
                raise FileNotFoundError(f"story narrative style mount not found: {mount_id}")
            row = StoryNarrativeStyleRecord.get_by_id(int(mount_id))
            return to_story_narrative_style(row)

    def list_quick_replies(
        self,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[StoryQuickReply]:
        query = StoryQuickReplyRecord.select().where(
            StoryQuickReplyRecord.story == int(story_id)
        )
        if enabled_only:
            query = query.where(StoryQuickReplyRecord.enabled == True)  # noqa: E712
        query = query.order_by(StoryQuickReplyRecord.sort_order, StoryQuickReplyRecord.id)
        return [to_story_quick_reply(row) for row in query]

    def get_quick_reply(self, reply_id: int) -> StoryQuickReply | None:
        row = StoryQuickReplyRecord.get_or_none(StoryQuickReplyRecord.id == int(reply_id))
        return to_story_quick_reply(row) if row is not None else None

    def create_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str,
        message: str,
        sort_order: int,
        enabled: bool,
    ) -> StoryQuickReply:
        row = StoryQuickReplyRecord.create(
            workspace=workspace_id,
            story=story_id,
            title=title,
            message=message,
            sort_order=int(sort_order),
            enabled=bool(enabled),
        )
        return to_story_quick_reply(row)

    def update_quick_reply(
        self,
        reply_id: int,
        *,
        title: str | None = None,
        message: str | None = None,
        sort_order: int | None = None,
        enabled: bool | None = None,
    ) -> StoryQuickReply | None:
        fields: dict[str, object] = {}
        if title is not None:
            fields["title"] = title
        if message is not None:
            fields["message"] = message
        if sort_order is not None:
            fields["sort_order"] = int(sort_order)
        if enabled is not None:
            fields["enabled"] = bool(enabled)
        if not fields:
            return self.get_quick_reply(reply_id)
        fields["version"] = StoryQuickReplyRecord.version + 1
        fields["updated_at"] = SQL("CURRENT_TIMESTAMP")
        updated = (
            StoryQuickReplyRecord.update(**fields)
            .where(StoryQuickReplyRecord.id == int(reply_id))
            .execute()
        )
        return self.get_quick_reply(reply_id) if updated else None

    def delete_quick_reply(self, reply_id: int) -> bool:
        return bool(
            StoryQuickReplyRecord.delete()
            .where(StoryQuickReplyRecord.id == int(reply_id))
            .execute()
        )
