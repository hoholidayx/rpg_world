"""Persistence for turn modes, narrative styles, and story quick replies."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database, SQL

from rpg_data import models
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


DEFAULT_TURN_MODES: tuple[tuple[str, str, str, int], ...] = (
    (
        models.TURN_MODE_IC,
        "角色内",
        "将本轮输入视为玩家角色在故事内的行动或发言，保持沉浸式叙事并自然推进当前场景。",
        10,
    ),
    (
        models.TURN_MODE_OOC,
        "场外",
        "将本轮输入视为场外讨论：直接、清晰地回应，不推进剧情，不产生剧情裁定或状态变化。",
        20,
    ),
    (
        models.TURN_MODE_GM,
        "主持",
        "将本轮输入视为主持人或导演指令，在遵守既有事实的前提下执行指令，并同步已经确定的剧情状态变化。",
        30,
    ),
)


class SessionComposerRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def ensure_workspace_modes(self, workspace_id: str) -> list[models.WorkspaceTurnMode]:
        for mode, short_name, prompt, sort_order in DEFAULT_TURN_MODES:
            WorkspaceTurnModeRecord.get_or_create(
                workspace=workspace_id,
                mode=mode,
                defaults={
                    "short_name": short_name,
                    "prompt": prompt,
                    "sort_order": sort_order,
                },
            )
        return self.list_workspace_modes(workspace_id)

    def list_workspace_modes(self, workspace_id: str) -> list[models.WorkspaceTurnMode]:
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
    ) -> models.WorkspaceTurnMode | None:
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

    def list_styles(self, workspace_id: str) -> list[models.NarrativeStyle]:
        rows = (
            NarrativeStyleRecord.select()
            .where(NarrativeStyleRecord.workspace == workspace_id)
            .order_by(NarrativeStyleRecord.sort_order, NarrativeStyleRecord.id)
        )
        return [to_narrative_style(row) for row in rows]

    def get_style(self, style_id: int) -> models.NarrativeStyle | None:
        row = NarrativeStyleRecord.get_or_none(NarrativeStyleRecord.id == int(style_id))
        return to_narrative_style(row) if row is not None else None

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int,
    ) -> models.NarrativeStyle:
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
    ) -> models.NarrativeStyle | None:
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
    ) -> list[models.StoryNarrativeStyle]:
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

    def mount_all_workspace_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryNarrativeStyle]:
        return self.mount_story_styles(
            workspace_id,
            story_id,
            (style.id for style in self.list_styles(workspace_id)),
        )

    def list_story_styles(self, story_id: int) -> list[models.StoryNarrativeStyle]:
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
    ) -> models.StoryNarrativeStyle | None:
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
    ) -> models.StoryNarrativeStyle | None:
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
    ) -> list[models.StoryQuickReply]:
        query = StoryQuickReplyRecord.select().where(
            StoryQuickReplyRecord.story == int(story_id)
        )
        if enabled_only:
            query = query.where(StoryQuickReplyRecord.enabled == True)  # noqa: E712
        query = query.order_by(StoryQuickReplyRecord.sort_order, StoryQuickReplyRecord.id)
        return [to_story_quick_reply(row) for row in query]

    def get_quick_reply(self, reply_id: int) -> models.StoryQuickReply | None:
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
    ) -> models.StoryQuickReply:
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
    ) -> models.StoryQuickReply | None:
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
