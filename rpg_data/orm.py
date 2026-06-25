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

database_proxy = DatabaseProxy()


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

    if database_proxy.obj is not database:
        if database_proxy.obj is None:
            database_proxy.initialize(database)
        else:
            database_proxy.initialize(database)
    database.bind(MODELS, bind_refs=False, bind_backrefs=False)
    return database


class BaseModel(Model):
    class Meta:
        database = database_proxy


class Workspace(BaseModel):
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
        table_name = "workspaces"


class Story(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
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
        table_name = "stories"


class Session(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
        backref="sessions",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        Story,
        backref="sessions",
        column_name="story_id",
        null=True,
        on_delete="SET NULL",
    )
    session_key = TextField()
    title = TextField(default="")
    state_json = TextField(default="{}")
    last_story_turn_index = IntegerField(default=0)
    metadata_json = TextField(default="{}")
    version = IntegerField(default=1)
    created_at = TextField()
    updated_at = TextField()

    class Meta:
        table_name = "sessions"


class Character(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
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
        table_name = "characters"


class CharacterDetail(BaseModel):
    id = AutoField()
    character = ForeignKeyField(
        Character,
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
        table_name = "character_details"


class LorebookEntry(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
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
        table_name = "lorebook_entries"


class StoryCharacter(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
        backref="story_characters",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        Story,
        backref="character_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    character = ForeignKeyField(
        Character,
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
        table_name = "story_characters"


class StoryLorebookEntry(BaseModel):
    id = AutoField()
    workspace = ForeignKeyField(
        Workspace,
        backref="story_lorebook_entries",
        column_name="workspace_id",
        on_delete="CASCADE",
    )
    story = ForeignKeyField(
        Story,
        backref="lorebook_mounts",
        column_name="story_id",
        on_delete="CASCADE",
    )
    lorebook_entry = ForeignKeyField(
        LorebookEntry,
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
        table_name = "story_lorebook_entries"


MODELS = (
    Workspace,
    Story,
    Session,
    Character,
    CharacterDetail,
    LorebookEntry,
    StoryCharacter,
    StoryLorebookEntry,
)
