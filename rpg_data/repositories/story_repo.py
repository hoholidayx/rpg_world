"""Repository for story records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories.records import StoryOpeningRecord, StoryRecord, bind_database
from rpg_data.repositories._utils import (
    get_or_none,
    to_story,
    to_story_opening,
    update_timestamp,
)


class StoryRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        title: str,
        *,
        summary: str = "",
        story_prompt: str = "",
        openings: Sequence[models.StoryOpeningInput] = (),
        metadata_json: str = "{}",
    ) -> models.Story:
        with self._database.atomic():
            row = StoryRecord.create(
                workspace=workspace_id,
                title=title,
                summary=summary,
                story_prompt=story_prompt,
                metadata_json=metadata_json,
            )
            self._replace_openings(row, openings)
            return self.get(int(row.id)) or self._to_story(row)

    def list(self, workspace_id: str | None = None) -> list[models.Story]:
        query = StoryRecord.select()
        if workspace_id is not None:
            query = query.where(StoryRecord.workspace == workspace_id)
        return [self._to_story(row) for row in query.order_by(StoryRecord.created_at, StoryRecord.id)]

    def get(self, story_id: int) -> models.Story | None:
        row = get_or_none(StoryRecord, story_id)
        return self._to_story(row) if row is not None else None

    def list_openings(self, story_id: int) -> list[models.StoryOpening]:
        rows = (
            StoryOpeningRecord
            .select()
            .where(StoryOpeningRecord.story == int(story_id))
            .order_by(StoryOpeningRecord.sort_order, StoryOpeningRecord.id)
        )
        return [to_story_opening(row) for row in rows]

    def get_opening(self, opening_id: int) -> models.StoryOpening | None:
        row = get_or_none(StoryOpeningRecord, int(opening_id))
        return to_story_opening(row) if row is not None else None

    def update(
        self,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        openings: Sequence[models.StoryOpeningInput] | None = None,
    ) -> models.Story | None:
        with self._database.atomic():
            fields: dict[str, object] = {}
            if title is not None:
                fields["title"] = title
            if summary is not None:
                fields["summary"] = summary
            if story_prompt is not None:
                fields["story_prompt"] = story_prompt
            if not fields and openings is None:
                row = get_or_none(StoryRecord, story_id)
                return self._to_story(row) if row is not None else None

            fields["version"] = StoryRecord.version + 1
            fields["updated_at"] = SQL("CURRENT_TIMESTAMP")
            updated = StoryRecord.update(**fields).where(StoryRecord.id == story_id).execute()
            if not updated:
                return None
            row = get_or_none(StoryRecord, story_id)
            if row is None:
                return None
            if openings is not None:
                self._replace_openings(row, openings)
            return self._to_story(row)

    def update_timestamp(self, story_id: int) -> models.Story | None:
        row = update_timestamp(StoryRecord, story_id)
        return self._to_story(row) if row is not None else None

    def set_main_llm_provider_key(
        self,
        story_id: int,
        provider_key: str | None,
    ) -> models.Story | None:
        updated = (
            StoryRecord
            .update(
                main_llm_provider_key=provider_key,
                version=StoryRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryRecord.id == story_id)
            .execute()
        )
        if not updated:
            return None
        row = get_or_none(StoryRecord, story_id)
        return self._to_story(row) if row is not None else None

    def _to_story(self, row: StoryRecord) -> models.Story:
        return replace(
            to_story(row),
            openings=tuple(self.list_openings(int(row.id))),
        )

    def _replace_openings(
        self,
        story: StoryRecord,
        openings: Sequence[models.StoryOpeningInput],
    ) -> None:
        existing_rows = list(
            StoryOpeningRecord
            .select()
            .where(StoryOpeningRecord.story == int(story.id))
        )
        existing_by_id = {int(row.id): row for row in existing_rows}
        requested_ids = {int(item.id) for item in openings if item.id is not None}
        unknown_ids = requested_ids.difference(existing_by_id)
        if unknown_ids:
            raise ValueError(
                "story opening does not belong to story: "
                + ", ".join(str(item) for item in sorted(unknown_ids))
            )

        for opening_id in requested_ids:
            (
                StoryOpeningRecord
                .update(title=f"__opening_update_{uuid4().hex}")
                .where(StoryOpeningRecord.id == opening_id)
                .execute()
            )
        deleted_ids = sorted(set(existing_by_id) - requested_ids)
        if deleted_ids:
            (
                StoryOpeningRecord
                .delete()
                .where(StoryOpeningRecord.id.in_(deleted_ids))
                .execute()
            )

        for sort_order, item in enumerate(openings):
            if item.id is None:
                StoryOpeningRecord.create(
                    workspace=story.workspace_id,
                    story=story.id,
                    title=item.title,
                    message=item.message,
                    sort_order=sort_order,
                )
                continue
            (
                StoryOpeningRecord
                .update(
                    title=item.title,
                    message=item.message,
                    sort_order=sort_order,
                    version=StoryOpeningRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(StoryOpeningRecord.id == int(item.id))
                .execute()
            )
