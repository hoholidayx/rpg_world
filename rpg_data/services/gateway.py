"""Gateway for rpg_data service initialization and access."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from peewee import Database

from rpg_data import db
from rpg_data.bootstrap import bootstrap_runtime_data
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.backup import BackupService
from rpg_data.services.catalog import CatalogService
from rpg_data.services.character import CharacterReadService
from rpg_data.services.lorebook import LorebookManagementService, LorebookReadService
from rpg_data.services.message import MessageService
from rpg_data.services.story_memory import StoryMemoryService
from rpg_data.services.status import StatusTableService
from rpg_data.settings import resolve_database_path

__all__ = [
    "DataServiceGateway",
    "get_data_service_gateway",
    "reset_data_service_gateways",
]

logger = logging.getLogger("rpg_data.gateway")


class DataServiceGateway:
    """Own the shared database lifecycle for rpg_data services."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = _normalize_database_path(db_path)
        self._database: Database | None = None
        self._catalog: CatalogService | None = None
        self._character: CharacterReadService | None = None
        self._lorebook: LorebookReadService | None = None
        self._lorebook_management: LorebookManagementService | None = None
        self._messages: MessageService | None = None
        self._backup: BackupService | None = None
        self._story_memory: StoryMemoryService | None = None
        self._status: StatusTableService | None = None
        self._initialized = False
        logger.debug("data service gateway created db_path=%s", self._database_path)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def database(self) -> Database:
        self.initialize()
        if self._database is None:
            raise RuntimeError("rpg_data database is not initialized")
        self._ensure_bound()
        return self._database

    @property
    def catalog(self) -> CatalogService:
        database = self.database
        if self._catalog is None:
            logger.debug("creating catalog service db_path=%s", self._database_path)
            self._catalog = CatalogService(database, status_service=self.status)
        self._ensure_bound()
        return self._catalog

    @property
    def character(self) -> CharacterReadService:
        database = self.database
        if self._character is None:
            logger.debug("creating character service db_path=%s", self._database_path)
            self._character = CharacterReadService(database)
        self._ensure_bound()
        return self._character

    @property
    def lorebook(self) -> LorebookReadService:
        database = self.database
        if self._lorebook is None:
            logger.debug("creating lorebook service db_path=%s", self._database_path)
            self._lorebook = LorebookReadService(database)
        self._ensure_bound()
        return self._lorebook

    @property
    def lorebook_management(self) -> LorebookManagementService:
        database = self.database
        if self._lorebook_management is None:
            logger.debug("creating lorebook management service db_path=%s", self._database_path)
            self._lorebook_management = LorebookManagementService(database)
        self._ensure_bound()
        return self._lorebook_management

    @property
    def messages(self) -> MessageService:
        database = self.database
        if self._messages is None:
            logger.debug("creating message service db_path=%s", self._database_path)
            self._messages = MessageService(database)
        self._ensure_bound()
        return self._messages

    @property
    def backup(self) -> BackupService:
        database = self.database
        if self._backup is None:
            logger.debug("creating backup service db_path=%s", self._database_path)
            self._backup = BackupService(database)
        self._ensure_bound()
        return self._backup

    @property
    def story_memory(self) -> StoryMemoryService:
        database = self.database
        if self._story_memory is None:
            logger.debug("creating story memory service db_path=%s", self._database_path)
            self._story_memory = StoryMemoryService(database)
        self._ensure_bound()
        return self._story_memory

    @property
    def status(self) -> StatusTableService:
        database = self.database
        if self._status is None:
            logger.debug("creating status service db_path=%s", self._database_path)
            self._status = StatusTableService(database)
        self._ensure_bound()
        return self._status

    def initialize(self) -> None:
        if self._initialized:
            self._ensure_bound()
            return

        logger.info("initializing data service gateway db_path=%s", self._database_path)
        database = db.bind_peewee_database(db.make_peewee_database(self._database_path))
        database.connect(reuse_if_open=True)
        try:
            logger.debug("running migrations db_path=%s", self._database_path)
            _run_migrations(database, self._database_path)
            logger.debug("running runtime bootstrap db_path=%s", self._database_path)
            bootstrap_runtime_data(database)
        except Exception:
            logger.exception("data service gateway initialization failed db_path=%s", self._database_path)
            if not database.is_closed():
                database.close()
            raise
        self._database = database
        self._initialized = True
        self._ensure_bound()
        logger.info("data service gateway initialized db_path=%s", self._database_path)

    def close(self) -> None:
        if self._database is not None and not self._database.is_closed():
            logger.info("closing data service gateway db_path=%s", self._database_path)
            self._database.close()
        self._initialized = False
        self._catalog = None
        self._character = None
        self._lorebook = None
        self._lorebook_management = None
        self._messages = None
        self._backup = None
        self._story_memory = None
        self._status = None

    def _ensure_bound(self) -> None:
        if self._database is None:
            return
        db.bind_peewee_database(self._database)
        self._database.connect(reuse_if_open=True)


_GATEWAYS: dict[str, DataServiceGateway] = {}


def get_data_service_gateway(db_path: str | Path | None = None) -> DataServiceGateway:
    """Return a cached data service gateway for ``db_path``."""

    database_path = _normalize_database_path(db_path)
    cache_key = str(database_path)
    gateway = _GATEWAYS.get(cache_key)
    if gateway is None:
        logger.debug("creating cached data service gateway db_path=%s", database_path)
        gateway = DataServiceGateway(database_path)
        _GATEWAYS[cache_key] = gateway
    else:
        logger.debug("reusing cached data service gateway db_path=%s", database_path)
    return gateway


def reset_data_service_gateways() -> None:
    """Close and clear cached gateways."""

    logger.info("resetting data service gateways count=%s", len(_GATEWAYS))
    for gateway in list(_GATEWAYS.values()):
        gateway.close()
    _GATEWAYS.clear()


def _normalize_database_path(db_path: str | Path | None) -> Path:
    return resolve_database_path(db_path)


def _run_migrations(database: Database, database_path: Path) -> None:
    if str(database_path) == ":memory:":
        logger.debug("running migrations on in-memory peewee connection")
        conn = database.connection()
        previous_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            run_migrations(conn)
        finally:
            conn.row_factory = previous_row_factory
        return

    logger.debug("running migrations using sqlite connection db_path=%s", database_path)
    conn = db.connect(database_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
