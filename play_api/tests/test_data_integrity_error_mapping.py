from __future__ import annotations

import pytest
from loguru import logger
from peewee import IntegrityError

from play_api.routers import characters
from play_api.routers._data_errors import data_integrity_conflict
from rpg_data.errors import DataIntegrityError


def _chained_integrity_error() -> DataIntegrityError:
    try:
        raise IntegrityError(
            "UNIQUE constraint failed: rpg_story_characters.story_id, "
            "rpg_story_characters.name"
        )
    except IntegrityError as cause:
        try:
            raise DataIntegrityError(
                "Character write violated persisted constraints"
            ) from cause
        except DataIntegrityError as exc:
            return exc


def test_data_integrity_conflict_logs_root_cause_and_returns_stable_detail() -> None:
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)),
        level="WARNING",
        format="{message}\n{exception}",
    )
    try:
        response = data_integrity_conflict(
            _chained_integrity_error(),
            operation="character.create",
            workspace_id="demo_workspace",
            story_id=1,
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 409
    assert response.detail == "Character write violated persisted constraints"
    assert "UNIQUE constraint failed" not in str(response.detail)
    rendered = "\n".join(messages)
    assert "operation=character.create" in rendered
    assert "workspace_id=demo_workspace" in rendered
    assert "story_id=1" in rendered
    assert "UNIQUE constraint failed: rpg_story_characters" in rendered


@pytest.mark.asyncio
async def test_character_route_does_not_convert_unexpected_errors(
    monkeypatch,
) -> None:
    class _UnexpectedBackend:
        async def create_character(self, *_args, **_kwargs):
            raise RuntimeError("unexpected backend failure")

    monkeypatch.setattr(
        characters,
        "get_data_manager_backend",
        lambda: _UnexpectedBackend(),
    )

    with pytest.raises(RuntimeError, match="unexpected backend failure"):
        await characters.create_character(
            "demo_workspace",
            1,
            characters.PlayCharacterPayload(name="Visible Name"),
        )
