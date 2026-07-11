"""Repository for story records."""

from __future__ import annotations

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories.records import StoryRecord, bind_database
from rpg_data.repositories._utils import (
    get_or_none,
    serialize_narrative_outcome_weights,
    to_story,
    update_timestamp,
)


class StoryRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        title: str,
        *,
        summary: str = "",
        story_prompt: str = "",
        first_message: str = "",
        metadata_json: str = "{}",
    ) -> models.Story:
        return to_story(StoryRecord.create(
            workspace=workspace_id,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            first_message=first_message,
            metadata_json=metadata_json,
        ))

    def list(self, workspace_id: str | None = None) -> list[models.Story]:
        query = StoryRecord.select()
        if workspace_id is not None:
            query = query.where(StoryRecord.workspace == workspace_id)
        return [to_story(row) for row in query.order_by(StoryRecord.created_at, StoryRecord.id)]

    def get(self, story_id: int) -> models.Story | None:
        row = get_or_none(StoryRecord, story_id)
        return to_story(row) if row is not None else None

    def update(
        self,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        first_message: str | None = None,
    ) -> models.Story | None:
        fields: dict[str, object] = {}
        if title is not None:
            fields["title"] = title
        if summary is not None:
            fields["summary"] = summary
        if story_prompt is not None:
            fields["story_prompt"] = story_prompt
        if first_message is not None:
            fields["first_message"] = first_message
        if not fields:
            row = get_or_none(StoryRecord, story_id)
            return to_story(row) if row is not None else None

        fields["version"] = StoryRecord.version + 1
        fields["updated_at"] = SQL("CURRENT_TIMESTAMP")
        updated = StoryRecord.update(**fields).where(StoryRecord.id == story_id).execute()
        if not updated:
            return None
        row = get_or_none(StoryRecord, story_id)
        return to_story(row) if row is not None else None

    def update_timestamp(self, story_id: int) -> models.Story | None:
        row = update_timestamp(StoryRecord, story_id)
        return to_story(row) if row is not None else None

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
        return to_story(row) if row is not None else None

    def set_narrative_outcome_weights(
        self,
        story_id: int,
        weights: models.NarrativeOutcomeWeights | None,
    ) -> models.Story | None:
        updated = (
            StoryRecord
            .update(
                narrative_outcome_weights_json=serialize_narrative_outcome_weights(weights),
                version=StoryRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(StoryRecord.id == story_id)
            .execute()
        )
        if not updated:
            return None
        row = get_or_none(StoryRecord, story_id)
        return to_story(row) if row is not None else None
