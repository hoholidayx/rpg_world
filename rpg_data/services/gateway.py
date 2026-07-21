"""Gateway for rpg_data service initialization and access."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from peewee import Database

from rpg_data import db
from rpg_data.bootstrap import bootstrap_runtime_data
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.backup import BackupService
from rpg_data.services.catalog import CatalogService
from rpg_data.services.character import CharacterManagementService, CharacterReadService
from rpg_data.services.dream_memory import DreamMemoryDataService
from rpg_data.services.lorebook import LorebookManagementService, LorebookReadService
from rpg_data.services.message import MessageDataService
from rpg_data.services.media import MediaDataService
from rpg_data.services.narrative_outcome import NarrativeOutcomeDataService
from rpg_data.services.plot_scheduling import PlotSchedulingDataService
from rpg_data.services.rp_modules import RPModuleDataService
from rpg_data.services.session import SessionDataService
from rpg_data.services.session_composer import SessionComposerDataService
from rpg_data.services.story_memory import StoryMemoryDataService
from rpg_data.services.status import StatusDataService
from rpg_data.services.tts import TTSDataService
from rpg_data.settings import resolve_database_path

__all__ = [
    "DataServiceGateway",
    "get_data_service_gateway",
    "reset_data_service_gateways",
]

logger = logging.getLogger("rpg_data.gateway")


class DataServiceGateway:
    """Own database lifecycle and lazily register public Data Services.

    Composition roots may use this registry to obtain concrete services. Domain
    services receive the resulting narrow service/Protocol dependency instead
    of retaining the whole registry as a service locator.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = _normalize_database_path(db_path)
        self._database: Database | None = None
        self._catalog: CatalogService | None = None
        self._character: CharacterReadService | None = None
        self._character_management: CharacterManagementService | None = None
        self._lorebook: LorebookReadService | None = None
        self._lorebook_management: LorebookManagementService | None = None
        self._messages: MessageDataService | None = None
        self._dream_memory: DreamMemoryDataService | None = None
        self._media: MediaDataService | None = None
        self._narrative_outcomes: NarrativeOutcomeDataService | None = None
        self._plot_scheduling: PlotSchedulingDataService | None = None
        self._rp_modules: RPModuleDataService | None = None
        self._sessions: SessionDataService | None = None
        self._session_composer: SessionComposerDataService | None = None
        self._backup: BackupService | None = None
        self._story_memory: StoryMemoryDataService | None = None
        self._status: StatusDataService | None = None
        self._tts: TTSDataService | None = None
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
            self._catalog = CatalogService(database)
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
    def character_management(self) -> CharacterManagementService:
        database = self.database
        if self._character_management is None:
            logger.debug("creating character management service db_path=%s", self._database_path)
            self._character_management = CharacterManagementService(database)
        self._ensure_bound()
        return self._character_management

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
    def messages(self) -> MessageDataService:
        database = self.database
        if self._messages is None:
            logger.debug("creating message service db_path=%s", self._database_path)
            self._messages = MessageDataService(database)
        self._ensure_bound()
        return self._messages

    @property
    def dream_memory(self) -> DreamMemoryDataService:
        database = self.database
        if self._dream_memory is None:
            logger.debug(
                "creating Dream memory data service db_path=%s",
                self._database_path,
            )
            self._dream_memory = DreamMemoryDataService(database)
        self._ensure_bound()
        return self._dream_memory

    @property
    def media(self) -> MediaDataService:
        database = self.database
        if self._media is None:
            logger.debug("creating media data service db_path=%s", self._database_path)
            self._media = MediaDataService(database)
        self._ensure_bound()
        return self._media

    @property
    def tts(self) -> TTSDataService:
        database = self.database
        if self._tts is None:
            logger.debug("creating TTS data service db_path=%s", self._database_path)
            self._tts = TTSDataService(database)
        self._ensure_bound()
        return self._tts

    @property
    def narrative_outcomes(self) -> NarrativeOutcomeDataService:
        database = self.database
        if self._narrative_outcomes is None:
            logger.debug("creating narrative outcome service db_path=%s", self._database_path)
            self._narrative_outcomes = NarrativeOutcomeDataService(database)
        self._ensure_bound()
        return self._narrative_outcomes

    @property
    def plot_scheduling(self) -> PlotSchedulingDataService:
        database = self.database
        if self._plot_scheduling is None:
            logger.debug("creating plot scheduling service db_path=%s", self._database_path)
            self._plot_scheduling = PlotSchedulingDataService(database)
        self._ensure_bound()
        return self._plot_scheduling

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Expose a business-neutral transaction boundary to application services."""

        with self.database.atomic():
            yield

    @property
    def rp_modules(self) -> RPModuleDataService:
        database = self.database
        if self._rp_modules is None:
            logger.debug("creating RP module service db_path=%s", self._database_path)
            self._rp_modules = RPModuleDataService(database)
        self._ensure_bound()
        return self._rp_modules

    @property
    def sessions(self) -> SessionDataService:
        database = self.database
        if self._sessions is None:
            logger.debug("creating Session data service db_path=%s", self._database_path)
            self._sessions = SessionDataService(database)
        self._ensure_bound()
        return self._sessions

    @property
    def session_composer(self) -> SessionComposerDataService:
        database = self.database
        if self._session_composer is None:
            logger.debug("creating session composer service db_path=%s", self._database_path)
            self._session_composer = SessionComposerDataService(database)
        self._ensure_bound()
        return self._session_composer

    @property
    def backup(self) -> BackupService:
        database = self.database
        if self._backup is None:
            logger.debug("creating backup service db_path=%s", self._database_path)
            self._backup = BackupService(database)
        self._ensure_bound()
        return self._backup

    @property
    def story_memory(self) -> StoryMemoryDataService:
        database = self.database
        if self._story_memory is None:
            logger.debug(
                "creating Story Memory data service db_path=%s",
                self._database_path,
            )
            self._story_memory = StoryMemoryDataService(database)
        self._ensure_bound()
        return self._story_memory

    @property
    def status(self) -> StatusDataService:
        database = self.database
        if self._status is None:
            logger.debug("creating status service db_path=%s", self._database_path)
            self._status = StatusDataService(database)
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
        self._character_management = None
        self._lorebook = None
        self._lorebook_management = None
        self._messages = None
        self._dream_memory = None
        self._media = None
        self._narrative_outcomes = None
        self._plot_scheduling = None
        self._rp_modules = None
        self._sessions = None
        self._session_composer = None
        self._backup = None
        self._story_memory = None
        self._status = None
        self._tts = None

    def close_thread_connection(self) -> None:
        """Close only the current thread's Peewee connection, if one exists."""

        if self._database is not None and not self._database.is_closed():
            self._database.close()

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
