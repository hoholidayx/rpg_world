"""Peewee ORM bindings for the RPG World data module."""

from __future__ import annotations

from pathlib import Path

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    Database,
    DatabaseProxy,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from rpg_data.settings import resolve_database_path

__all__ = [
    "CharacterDetailRecord",
    "CharacterRecord",
    "LorebookEntryRecord",
    "SessionBackupMessageRecord",
    "SessionMessageRecord",
    "SessionProfileRecord",
    "SessionRecord",
    "SessionStoryMemoryRecord",
    "SessionStatusTableRecord",
    "SessionStatusTypeRecord",
    "StoryCharacterRecord",
    "StoryLorebookEntryRecord",
    "StoryStatusTableRecord",
    "StoryRecord",
    "StatusTableTemplateRecord",
    "StatusTypeRecord",
    "WorkspaceRecord",
    "bind_database",
    "make_database",
]

_database_proxy = DatabaseProxy()


def make_database(db_path: str | Path | None = None) -> SqliteDatabase:
    """Create a Peewee SQLite database using the rpg_data pragmas."""

    path = resolve_database_path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteDatabase(
        path,
        pragmas={
            "foreign_keys": 1,
            "journal_mode": "wal",
            "busy_timeout": 5000,
        },
    )


def bind_database(database: Database) -> Database:
    """Bind all ORM models to ``database`` and return it."""

    if _database_proxy.obj is not database:
        if _database_proxy.obj is None:
            _database_proxy.initialize(database)
        else:
            _database_proxy.initialize(database)
    database.bind(RECORD_MODELS, bind_refs=False, bind_backrefs=False)
    return database


class BaseRecord(Model):
    class Meta:
        database = _database_proxy


class WorkspaceRecord(BaseRecord):
    id = CharField(primary_key=True)
    name = TextField()
    root_path = TextField()
    description = TextField(default="")
    enabled = BooleanField(default=True)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_workspaces"


class StoryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="stories",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    title = TextField()
    summary = TextField(default="")
    # Story-level fixed system prompt; planned to be integrated into fix layer later.
    story_prompt = TextField(default="")
    first_message = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_stories"


class SessionRecord(BaseRecord):
    id = CharField(primary_key=True)
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="sessions",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="sessions",
        column_name="story_id",
        on_delete="CASCADE",
    )
    state_json = TextField(default="{}")
    story_memory_last_turn_id = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_sessions"


class SessionProfileRecord(BaseRecord):
    session = ForeignKeyField(
        SessionRecord,
        primary_key=True,
        backref="profile",
        column_name="session_id",
        on_delete="CASCADE",
    )
    title = TextField(default="")
    description = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_profiles"


class SessionMessageRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="messages",
        column_name="session_id",
        on_delete="CASCADE",
    )
    role = TextField()
    content = TextField(default="")
    turn_id = IntegerField(default=0)
    seq_in_turn = IntegerField(default=0)
    tool_call_id = TextField(default="")
    tool_calls_json = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_messages"


class SessionBackupMessageRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="backup_messages",
        column_name="session_id",
        on_delete="CASCADE",
    )
    role = TextField()
    content = TextField(default="")
    turn_id = IntegerField(default=0)
    seq_in_turn = IntegerField(default=0)
    tool_call_id = TextField(default="")
    tool_calls_json = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_backup_messages"


class SessionStoryMemoryRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="story_memories",
        column_name="session_id",
        on_delete="CASCADE",
    )
    turn_id = IntegerField(default=0)
    text = TextField(default="")
    dream_processed = BooleanField(default=False)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_story_memories"


class CharacterRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="characters",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    personality = TextField(default="")
    content = TextField(default="")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_characters"


class CharacterDetailRecord(BaseRecord):
    id = AutoField()
    character = ForeignKeyField(
        CharacterRecord,
        backref="details",
        column_name="character_id",
        on_delete="CASCADE",
    )
    name = TextField()
    content = TextField(default="")
    tags_json = TextField(default="[]")
    sort_order = IntegerField(default=0)
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_character_details"


class LorebookEntryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="lorebook_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    content = TextField(default="")
    description = TextField(default="")
    tags_json = TextField(default="[]")
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_lorebook_entries"


class StoryCharacterRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_characters",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="character_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    character = ForeignKeyField(
        CharacterRecord,
        backref="story_mounts",
        column_name="character_id",
        on_delete="CASCADE",
    )
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_characters"


class StoryLorebookEntryRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_lorebook_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="lorebook_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    lorebook_entry = ForeignKeyField(
        LorebookEntryRecord,
        backref="story_mounts",
        column_name="lorebook_entry_id",
        on_delete="CASCADE",
    )
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_lorebook_entries"


class StatusTypeRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="status_types",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    name = TextField()
    builtin_key = TextField(default="")
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_status_types"


class StatusTableTemplateRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="status_table_templates",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    status_type = ForeignKeyField(
        StatusTypeRecord,
        backref="templates",
        column_name="type_id",
        on_delete="CASCADE",
    )
    name = TextField()
    relative_path = TextField()
    description = TextField(default="")
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_status_table_templates"


class StoryStatusTableRecord(BaseRecord):
    id = AutoField()
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="story_status_tables",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="status_table_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    status_table = ForeignKeyField(
        StatusTableTemplateRecord,
        backref="story_mounts",
        column_name="status_table_id",
        on_delete="CASCADE",
    )
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_status_tables"


class SessionStatusTypeRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="status_types",
        column_name="session_id",
        on_delete="CASCADE",
    )
    workspace = ForeignKeyField(
        WorkspaceRecord,
        backref="session_status_types",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        StoryRecord,
        backref="session_status_types",
        column_name="story_id",
        on_delete="CASCADE",
    )
    source_type_id = IntegerField(null=True)
    name = TextField()
    builtin_key = TextField(default="")
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_status_types"


class SessionStatusTableRecord(BaseRecord):
    id = AutoField()
    session = ForeignKeyField(
        SessionRecord,
        backref="status_tables",
        column_name="session_id",
        on_delete="CASCADE",
    )
    session_type = ForeignKeyField(
        SessionStatusTypeRecord,
        backref="tables",
        column_name="session_type_id",
        on_delete="CASCADE",
    )
    source_table_id = IntegerField(null=True)
    name = TextField()
    relative_path = TextField()
    description = TextField(default="")
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_session_status_tables"


RECORD_MODELS = (
    WorkspaceRecord,
    StoryRecord,
    SessionRecord,
    SessionProfileRecord,
    SessionMessageRecord,
    SessionBackupMessageRecord,
    SessionStoryMemoryRecord,
    CharacterRecord,
    CharacterDetailRecord,
    LorebookEntryRecord,
    StoryCharacterRecord,
    StoryLorebookEntryRecord,
    StatusTypeRecord,
    StatusTableTemplateRecord,
    StoryStatusTableRecord,
    SessionStatusTypeRecord,
    SessionStatusTableRecord,
)
