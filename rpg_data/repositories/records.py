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

from rpg_data.settings import get_database_path

__all__ = [
    "CharacterDetailRecord",
    "CharacterRecord",
    "LorebookEntryRecord",
    "SessionProfileRecord",
    "SessionRecord",
    "StoryCharacterRecord",
    "StoryLorebookEntryRecord",
    "StoryRecord",
    "WorkspaceRecord",
    "bind_database",
    "make_database",
]

_database_proxy = DatabaseProxy()


def make_database(db_path: str | Path | None = None) -> SqliteDatabase:
    """Create a Peewee SQLite database using the rpg_data pragmas."""

    path = Path(db_path).expanduser() if db_path is not None else get_database_path()
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
    description = TextField(default="")
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
    last_story_turn_index = IntegerField(default=0)
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
    enabled = BooleanField(default=True)
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
    enabled = BooleanField(default=True)
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
    enabled = BooleanField(default=True)
    sort_order = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "rpg_story_lorebook_entries"


RECORD_MODELS = (
    WorkspaceRecord,
    StoryRecord,
    SessionRecord,
    SessionProfileRecord,
    CharacterRecord,
    CharacterDetailRecord,
    LorebookEntryRecord,
    StoryCharacterRecord,
    StoryLorebookEntryRecord,
)
