"""Session-level player character binding service."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import (
    CharacterRecord,
    StoryCharacterRecord,
    StoryRecord,
    bind_database,
)
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.services.backup import BackupService
from rpg_data.services.message import MessageService
from rpg_data.story_template import render_story_text_template

logger = logging.getLogger("rpg_data.session_role")


@dataclass(frozen=True)
class PlayerCharacterOption:
    snapshot: models.SessionPlayerCharacterSnapshot
    summary: str


@dataclass(frozen=True)
class SessionPlayerCharacterState:
    status: str
    player: models.SessionPlayerCharacterSnapshot | None = None


@dataclass(frozen=True)
class SessionPlayerCharacterBindResult:
    state: SessionPlayerCharacterState
    first_message: str = ""


class SessionRoleService:
    """Read and mutate the player-controlled character bound to a session."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._sessions = SessionRepository(database)
        self._messages = MessageService(database)
        self._backup = BackupService(database)

    def get_state(self, session_id: str) -> SessionPlayerCharacterState:
        session = self._require_session(session_id)
        options = self.list_options(session_id)
        if not options:
            logger.debug(
                "player character state invalid: no mounted options session_id=%s workspace_id=%s story_id=%s",
                session_id,
                session.workspace_id,
                session.story_id,
            )
            return SessionPlayerCharacterState(status=models.PLAYER_CHARACTER_STATUS_INVALID)
        if session.player_character_id is None:
            logger.debug(
                "player character state invalid: missing binding session_id=%s workspace_id=%s story_id=%s option_count=%s",
                session_id,
                session.workspace_id,
                session.story_id,
                len(options),
            )
            return SessionPlayerCharacterState(status=models.PLAYER_CHARACTER_STATUS_INVALID)
        snapshot = _snapshot_from_json(session.player_character_snapshot_json, session.player_character_id)
        if snapshot is None:
            logger.warning(
                "player character state invalid: corrupted snapshot session_id=%s character_id=%s",
                session_id,
                session.player_character_id,
            )
            return SessionPlayerCharacterState(status=models.PLAYER_CHARACTER_STATUS_INVALID)

        for option in options:
            if option.snapshot.character_id == session.player_character_id:
                if snapshot.mount_id != option.snapshot.mount_id or snapshot.story_id != option.snapshot.story_id:
                    logger.warning(
                        "player character state invalid: snapshot mount mismatch session_id=%s character_id=%s snapshot_mount_id=%s current_mount_id=%s snapshot_story_id=%s current_story_id=%s",
                        session_id,
                        session.player_character_id,
                        snapshot.mount_id,
                        option.snapshot.mount_id,
                        snapshot.story_id,
                        option.snapshot.story_id,
                    )
                    return SessionPlayerCharacterState(status=models.PLAYER_CHARACTER_STATUS_INVALID)
                logger.debug(
                    "player character state bound session_id=%s character_id=%s mount_id=%s story_id=%s",
                    session_id,
                    snapshot.character_id,
                    snapshot.mount_id,
                    snapshot.story_id,
                )
                return SessionPlayerCharacterState(
                    status=models.PLAYER_CHARACTER_STATUS_BOUND,
                    player=snapshot,
                )
        logger.warning(
            "player character state invalid: bound character no longer mounted session_id=%s character_id=%s option_count=%s",
            session_id,
            session.player_character_id,
            len(options),
        )
        return SessionPlayerCharacterState(status=models.PLAYER_CHARACTER_STATUS_INVALID)

    def list_options(self, session_id: str) -> list[PlayerCharacterOption]:
        session = self._require_session(session_id)
        rows = (
            StoryCharacterRecord
            .select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.workspace == session.workspace_id)
                & (StoryCharacterRecord.story == session.story_id)
            )
            .order_by(StoryCharacterRecord.sort_order, StoryCharacterRecord.id)
        )
        options = [_option_from_mount(row) for row in rows]
        logger.debug(
            "loaded player character options session_id=%s workspace_id=%s story_id=%s option_count=%s",
            session_id,
            session.workspace_id,
            session.story_id,
            len(options),
        )
        return options

    def bind_player_character(
        self,
        session_id: str,
        character_id: int,
    ) -> SessionPlayerCharacterBindResult:
        session = self._require_session(session_id)
        target_id = int(character_id)
        options = self.list_options(session_id)
        option = next((item for item in options if item.snapshot.character_id == target_id), None)
        if option is None:
            logger.warning(
                "player character bind rejected: character not mounted session_id=%s workspace_id=%s story_id=%s character_id=%s option_count=%s",
                session_id,
                session.workspace_id,
                session.story_id,
                target_id,
                len(options),
            )
            raise ValueError(f"player character is not mounted to this session story: {target_id}")

        snapshot_json = _snapshot_json(option.snapshot)
        prepared_first_message = (
            self._prepare_first_message(
                session_id,
                option.snapshot,
            )
            if session.player_character_id is None
            else ""
        )
        logger.info(
            "binding player character session_id=%s workspace_id=%s story_id=%s character_id=%s mount_id=%s",
            session_id,
            session.workspace_id,
            session.story_id,
            option.snapshot.character_id,
            option.snapshot.mount_id,
        )
        with self._database.atomic():
            updated = self._sessions.update_player_character(
                session_id,
                player_character_id=target_id,
                player_character_snapshot_json=snapshot_json,
            )
            if updated is None:
                logger.warning("player character bind lost session during update session_id=%s", session_id)
                raise FileNotFoundError(f"Session not found: {session_id}")
            first_message = self._append_prepared_first_message_if_empty(
                session_id,
                prepared_first_message,
                story_id=int(session.story_id),
            )

        logger.info(
            "player character bound session_id=%s character_id=%s first_message_appended=%s",
            session_id,
            target_id,
            bool(first_message),
        )
        return SessionPlayerCharacterBindResult(
            state=SessionPlayerCharacterState(
                status=models.PLAYER_CHARACTER_STATUS_BOUND,
                player=option.snapshot,
            ),
            first_message=first_message,
        )

    def render_role_bind_prompt(self, session_id: str, *, error: str = "") -> str:
        options = self.list_options(session_id)
        if not options:
            logger.info("rendering role bind prompt without options session_id=%s error=%s", session_id, bool(error))
            return "当前故事还没有可扮演角色。请先在角色库创建角色，并挂载到当前故事。"

        logger.debug(
            "rendering role bind prompt session_id=%s option_count=%s error=%s",
            session_id,
            len(options),
            bool(error),
        )
        lines: list[str] = []
        if error:
            lines.append(error.strip())
            lines.append("")
        state = self.get_state(session_id)
        current_character_id = (
            state.player.character_id
            if state.status == models.PLAYER_CHARACTER_STATUS_BOUND and state.player is not None
            else None
        )
        lines.append("请选择你要扮演的角色（回复 /role_bind 序号）：")
        for index, option in enumerate(options, start=1):
            marker = "（当前扮演）" if option.snapshot.character_id == current_character_id else ""
            lines.append(f"{index}. {option.snapshot.name}{marker}")
            lines.append(f"   {option.summary}")
        lines.append("")
        lines.append("示例：/role_bind 2")
        return "\n".join(lines)

    def bind_by_index(self, session_id: str, index: int) -> SessionPlayerCharacterBindResult:
        options = self.list_options(session_id)
        if index < 1 or index > len(options):
            logger.warning(
                "player character bind rejected: invalid index session_id=%s index=%s option_count=%s",
                session_id,
                index,
                len(options),
            )
            raise ValueError(f"无效角色序号: {index}")
        logger.info(
            "binding player character by index session_id=%s index=%s character_id=%s",
            session_id,
            index,
            options[index - 1].snapshot.character_id,
        )
        return self.bind_player_character(session_id, options[index - 1].snapshot.character_id)

    def _prepare_first_message(
        self,
        session_id: str,
        player: models.SessionPlayerCharacterSnapshot,
    ) -> str:
        message_count = self._messages.count(session_id)
        if message_count > 0:
            logger.debug(
                "skip first message append because history exists session_id=%s message_count=%s",
                session_id,
                message_count,
            )
            return ""
        session = self._require_session(session_id)
        story = StoryRecord.get_or_none(StoryRecord.id == session.story_id)
        first_message = str(story.first_message or "").strip() if story is not None else ""
        if not first_message:
            logger.debug(
                "skip first message append because story has no first_message session_id=%s story_id=%s",
                session_id,
                session.story_id,
            )
            return ""

        return render_story_text_template(
            first_message,
            user_play_role_name=player.name,
        )

    def _append_prepared_first_message_if_empty(
        self,
        session_id: str,
        first_message: str,
        *,
        story_id: int,
    ) -> str:
        if not first_message:
            return ""
        message_count = self._messages.count(session_id)
        if message_count > 0:
            logger.debug(
                "skip prepared first message append because history exists session_id=%s message_count=%s",
                session_id,
                message_count,
            )
            return ""

        metadata_json = json.dumps({"source": "story_first_message"}, ensure_ascii=False)
        self._messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            first_message,
            mode=models.TURN_MODE_IC,
            turn_id=1,
            seq_in_turn=1,
            metadata_json=metadata_json,
        )
        self._backup.messages.append(
            session_id,
            models.MESSAGE_ROLE_ASSISTANT,
            first_message,
            mode=models.TURN_MODE_IC,
            turn_id=1,
            seq_in_turn=1,
            metadata_json=metadata_json,
        )
        logger.info(
            "appended story first message after player bind session_id=%s story_id=%s first_message_chars=%s",
            session_id,
            story_id,
            len(first_message),
        )
        return first_message

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session


def _option_from_mount(row: StoryCharacterRecord) -> PlayerCharacterOption:
    character = row.character
    metadata = _json_object(str(character.metadata_json or "{}"))
    ui = metadata.get("ui") if isinstance(metadata.get("ui"), dict) else {}
    avatar_url = _string_value(ui.get("avatarUrl")) if isinstance(ui, dict) else ""
    role_label = _string_value(ui.get("roleLabel")) if isinstance(ui, dict) else ""
    snapshot = models.SessionPlayerCharacterSnapshot(
        character_id=int(row.character_id),
        mount_id=int(row.id),
        story_id=int(row.story_id),
        name=str(character.name),
        avatar_url=avatar_url,
        role_label=role_label,
        updated_at=str(character.updated_at),
    )
    return PlayerCharacterOption(snapshot=snapshot, summary=_character_summary(character))


def _snapshot_json(snapshot: models.SessionPlayerCharacterSnapshot) -> str:
    return json.dumps(
        {
            "characterId": snapshot.character_id,
            "mountId": snapshot.mount_id,
            "storyId": snapshot.story_id,
            "name": snapshot.name,
            "avatarUrl": snapshot.avatar_url,
            "roleLabel": snapshot.role_label,
            "updatedAt": snapshot.updated_at,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _snapshot_from_json(raw: str, character_id: int) -> models.SessionPlayerCharacterSnapshot | None:
    payload = _json_object(raw)
    if not payload:
        return None
    try:
        snapshot_character_id = int(payload.get("characterId") or 0)
        mount_id = int(payload.get("mountId") or 0)
        story_id = int(payload.get("storyId") or 0)
    except (TypeError, ValueError):
        return None
    name = _string_value(payload.get("name")).strip()
    if snapshot_character_id != int(character_id) or mount_id <= 0 or story_id <= 0 or not name:
        return None
    return models.SessionPlayerCharacterSnapshot(
        character_id=snapshot_character_id,
        mount_id=mount_id,
        story_id=story_id,
        name=name,
        avatar_url=_string_value(payload.get("avatarUrl")),
        role_label=_string_value(payload.get("roleLabel")),
        updated_at=_string_value(payload.get("updatedAt")),
    )


def _json_object(raw: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _character_summary(character: CharacterRecord) -> str:
    personality = str(character.personality or "").strip()
    if personality:
        return " ".join(personality.split())[:96]
    content = str(character.content or "").strip()
    if content:
        return " ".join(content.split())[:96]
    return "已挂载到当前故事。"
