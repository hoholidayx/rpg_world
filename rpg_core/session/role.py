"""Session player-role and Story Opening application policy."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rpg_core.story.template import render_story_text_template
from rpg_data import models as data_models

if TYPE_CHECKING:
    from rpg_data.services.gateway import DataServiceGateway

logger = logging.getLogger("rpg_core.session.role")

_OPENING_MESSAGE_SOURCE = "story_opening"
_METADATA_SOURCE_KEY = "source"
_METADATA_OPENING_ID_KEY = "storyOpeningId"


class PlayerCharacterBindingStatus(StrEnum):
    BOUND = "bound"
    INVALID = "invalid"


@dataclass(frozen=True)
class PlayerCharacterOption:
    snapshot: data_models.SessionPlayerCharacterSnapshot
    summary: str


@dataclass(frozen=True)
class SessionPlayerCharacterState:
    status: PlayerCharacterBindingStatus
    player: data_models.SessionPlayerCharacterSnapshot | None = None


@dataclass(frozen=True)
class SessionPlayerCharacterBindResult:
    state: SessionPlayerCharacterState
    first_message: str = ""
    story_opening_id: int | None = None


@dataclass(frozen=True)
class SessionOpeningOption:
    opening: data_models.StoryOpening
    rendered_message: str


@dataclass(frozen=True)
class SessionOpeningReplayResult:
    story_opening_id: int | None = None
    first_message: str = ""


class SessionRoleService:
    """Apply role validity, binding, Opening selection, and replay rules."""

    def __init__(self, gateway: "DataServiceGateway") -> None:
        self._gateway = gateway
        self._data = gateway.session_roles

    def get_state(self, session_id: str) -> SessionPlayerCharacterState:
        session = self._require_session(session_id)
        options = self.list_options(session_id)
        if not options or session.player_character_id is None:
            return _invalid_state()

        snapshot = decode_player_character_snapshot(
            session.player_character_snapshot_json,
            expected_character_id=session.player_character_id,
        )
        if snapshot is None:
            logger.warning(
                "player character snapshot is invalid session_id=%s character_id=%s",
                session_id,
                session.player_character_id,
            )
            return _invalid_state()

        current = next(
            (
                option.snapshot
                for option in options
                if option.snapshot.character_id == session.player_character_id
            ),
            None,
        )
        if (
            current is None
            or snapshot.mount_id != current.mount_id
            or snapshot.story_id != current.story_id
        ):
            logger.warning(
                "player character binding no longer matches Story mount "
                "session_id=%s character_id=%s",
                session_id,
                session.player_character_id,
            )
            return _invalid_state()
        return SessionPlayerCharacterState(
            status=PlayerCharacterBindingStatus.BOUND,
            player=snapshot,
        )

    def list_options(self, session_id: str) -> list[PlayerCharacterOption]:
        return [
            PlayerCharacterOption(
                snapshot=_snapshot_from_mount(mount),
                summary=_character_summary(mount),
            )
            for mount in self._data.list_character_mounts(str(session_id))
        ]

    def list_opening_options(
        self,
        session_id: str,
        character_id: int,
    ) -> list[SessionOpeningOption]:
        player = self.require_player_option(session_id, character_id).snapshot
        return [
            SessionOpeningOption(
                opening=opening,
                rendered_message=_render_opening(opening, player),
            )
            for opening in self._data.list_story_openings(str(session_id))
        ]

    def can_select_opening(self, session_id: str) -> bool:
        session = self._require_session(session_id)
        return (
            session.player_character_id is None
            and self._gateway.messages.count(str(session_id)) == 0
        )

    def bind_player_character(
        self,
        session_id: str,
        character_id: int,
        *,
        story_opening_id: int | None = None,
    ) -> SessionPlayerCharacterBindResult:
        normalized_session_id = str(session_id)
        target_id = _positive_id(character_id, "character_id")
        with self._data.transaction():
            session = self._require_session(normalized_session_id)
            option = self.require_player_option(normalized_session_id, target_id)
            initial_binding = (
                session.player_character_id is None
                and self._gateway.messages.count(normalized_session_id) == 0
            )
            if not initial_binding and story_opening_id is not None:
                raise ValueError(
                    "story opening can only be selected for an empty unbound session"
                )
            selected_opening = (
                self._resolve_opening(
                    normalized_session_id,
                    story_opening_id,
                    fallback_to_default=False,
                )
                if initial_binding
                else None
            )
            prepared_message = _render_opening(selected_opening, option.snapshot)
            snapshot_json = encode_player_character_snapshot(option.snapshot)
            if initial_binding:
                updated = self._data.update_player_character_and_opening(
                    normalized_session_id,
                    player_character_id=target_id,
                    player_character_snapshot_json=snapshot_json,
                    story_opening_id=(
                        selected_opening.id
                        if selected_opening is not None
                        else None
                    ),
                )
            else:
                updated = self._data.update_player_character(
                    normalized_session_id,
                    player_character_id=target_id,
                    player_character_snapshot_json=snapshot_json,
                )
            if updated is None:
                raise FileNotFoundError(f"Session not found: {normalized_session_id}")
            first_message = self._append_opening_message_if_empty(
                normalized_session_id,
                prepared_message,
                story_opening_id=(
                    selected_opening.id if selected_opening is not None else None
                ),
            )

        return SessionPlayerCharacterBindResult(
            state=SessionPlayerCharacterState(
                status=PlayerCharacterBindingStatus.BOUND,
                player=option.snapshot,
            ),
            first_message=first_message,
            story_opening_id=(
                selected_opening.id if selected_opening is not None else None
            ),
        )

    def replay_opening_for_reset(
        self,
        session_id: str,
    ) -> SessionOpeningReplayResult:
        """Replay the saved or default Opening after a caller clears history."""

        normalized_session_id = str(session_id)
        state = self.get_state(normalized_session_id)
        if (
            state.status is not PlayerCharacterBindingStatus.BOUND
            or state.player is None
        ):
            return SessionOpeningReplayResult()

        session = self._require_session(normalized_session_id)
        selected = self._resolve_opening(
            normalized_session_id,
            session.story_opening_id,
            fallback_to_default=True,
        )
        prepared_message = _render_opening(selected, state.player)
        with self._data.transaction():
            updated = self._data.update_story_opening(
                normalized_session_id,
                selected.id if selected is not None else None,
            )
            if updated is None:
                raise FileNotFoundError(f"Session not found: {normalized_session_id}")
            first_message = self._append_opening_message_if_empty(
                normalized_session_id,
                prepared_message,
                story_opening_id=(selected.id if selected is not None else None),
            )
        return SessionOpeningReplayResult(
            story_opening_id=(selected.id if selected is not None else None),
            first_message=first_message,
        )

    def require_player_option(
        self,
        session_id: str,
        character_id: int,
    ) -> PlayerCharacterOption:
        target_id = _positive_id(character_id, "character_id")
        option = next(
            (
                item
                for item in self.list_options(session_id)
                if item.snapshot.character_id == target_id
            ),
            None,
        )
        if option is None:
            raise ValueError(
                "player character is not mounted to this session story: "
                f"{target_id}"
            )
        return option

    def _resolve_opening(
        self,
        session_id: str,
        story_opening_id: int | None,
        *,
        fallback_to_default: bool,
    ) -> data_models.StoryOpening | None:
        openings = self._data.list_story_openings(str(session_id))
        if story_opening_id is None:
            return openings[0] if openings else None
        selected_id = _positive_id(story_opening_id, "story_opening_id")
        selected = next(
            (opening for opening in openings if opening.id == selected_id),
            None,
        )
        if selected is not None:
            return selected
        if fallback_to_default:
            logger.warning(
                "saved Story Opening is unavailable; using default "
                "session_id=%s story_opening_id=%s",
                session_id,
                selected_id,
            )
            return openings[0] if openings else None
        raise ValueError(
            "story opening is not mounted to this session story: "
            f"{selected_id}"
        )

    def _append_opening_message_if_empty(
        self,
        session_id: str,
        content: str,
        *,
        story_opening_id: int | None,
    ) -> str:
        if not content or self._gateway.messages.count(session_id) > 0:
            return ""
        metadata_json = _opening_message_metadata(story_opening_id)
        self._gateway.messages.append(
            session_id,
            data_models.MESSAGE_ROLE_ASSISTANT,
            content,
            mode=data_models.TURN_MODE_IC,
            turn_id=1,
            seq_in_turn=1,
            metadata_json=metadata_json,
        )
        self._gateway.backup.messages.append(
            session_id,
            data_models.MESSAGE_ROLE_ASSISTANT,
            content,
            mode=data_models.TURN_MODE_IC,
            turn_id=1,
            seq_in_turn=1,
            metadata_json=metadata_json,
        )
        return content

    def _require_session(self, session_id: str) -> data_models.Session:
        session = self._data.get_session(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session


def encode_player_character_snapshot(
    snapshot: data_models.SessionPlayerCharacterSnapshot,
) -> str:
    payload: dict[str, str | int] = {
        "characterId": snapshot.character_id,
        "mountId": snapshot.mount_id,
        "storyId": snapshot.story_id,
        "name": snapshot.name,
        "avatarUrl": snapshot.avatar_url,
        "roleLabel": snapshot.role_label,
        "updatedAt": snapshot.updated_at,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_player_character_snapshot(
    raw: str,
    *,
    expected_character_id: int,
) -> data_models.SessionPlayerCharacterSnapshot | None:
    payload = _json_object(raw)
    try:
        character_id = int(payload.get("characterId") or 0)
        mount_id = int(payload.get("mountId") or 0)
        story_id = int(payload.get("storyId") or 0)
    except (TypeError, ValueError):
        return None
    name = _string_value(payload.get("name")).strip()
    if (
        character_id != int(expected_character_id)
        or mount_id <= 0
        or story_id <= 0
        or not name
    ):
        return None
    return data_models.SessionPlayerCharacterSnapshot(
        character_id=character_id,
        mount_id=mount_id,
        story_id=story_id,
        name=name,
        avatar_url=_string_value(payload.get("avatarUrl")),
        role_label=_string_value(payload.get("roleLabel")),
        updated_at=_string_value(payload.get("updatedAt")),
    )


def _snapshot_from_mount(
    mount: data_models.SessionCharacterMount,
) -> data_models.SessionPlayerCharacterSnapshot:
    metadata = _json_object(mount.metadata_json)
    raw_ui = metadata.get("ui")
    ui = raw_ui if isinstance(raw_ui, dict) else {}
    return data_models.SessionPlayerCharacterSnapshot(
        character_id=mount.character_id,
        mount_id=mount.mount_id,
        story_id=mount.story_id,
        name=mount.name,
        avatar_url=_string_value(ui.get("avatarUrl")),
        role_label=_string_value(ui.get("roleLabel")),
        updated_at=mount.character_updated_at,
    )


def _character_summary(mount: data_models.SessionCharacterMount) -> str:
    personality = mount.personality.strip()
    if personality:
        return " ".join(personality.split())[:96]
    content = mount.content.strip()
    if content:
        return " ".join(content.split())[:96]
    return "已挂载到当前故事。"


def _render_opening(
    opening: data_models.StoryOpening | None,
    player: data_models.SessionPlayerCharacterSnapshot,
) -> str:
    if opening is None:
        return ""
    return render_story_text_template(
        opening.message,
        user_play_role_name=player.name,
    )


def _opening_message_metadata(story_opening_id: int | None) -> str:
    payload: dict[str, str | int | None] = {
        _METADATA_SOURCE_KEY: _OPENING_MESSAGE_SOURCE,
        _METADATA_OPENING_ID_KEY: story_opening_id,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _json_object(raw: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _positive_id(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _invalid_state() -> SessionPlayerCharacterState:
    return SessionPlayerCharacterState(
        status=PlayerCharacterBindingStatus.INVALID,
    )


__all__ = [
    "PlayerCharacterBindingStatus",
    "PlayerCharacterOption",
    "SessionOpeningOption",
    "SessionOpeningReplayResult",
    "SessionPlayerCharacterBindResult",
    "SessionPlayerCharacterState",
    "SessionRoleService",
    "decode_player_character_snapshot",
    "encode_player_character_snapshot",
]
