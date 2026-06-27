"""Gateway for rpg_data service initialization and access."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from peewee import Database

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.catalog import CatalogService
from rpg_data.services.lorebook import LorebookReadService
from rpg_data.settings import get_database_path

__all__ = [
    "DataServiceGateway",
    "get_data_service_gateway",
    "reset_data_service_gateways",
]


class DataServiceGateway:
    """Own the shared database lifecycle for rpg_data services."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._database_path = _normalize_database_path(db_path)
        self._database: Database | None = None
        self._catalog: CatalogService | None = None
        self._lorebook: LorebookReadService | None = None
        self._initialized = False

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
            self._catalog = CatalogService(database)
        self._ensure_bound()
        return self._catalog

    @property
    def lorebook(self) -> LorebookReadService:
        database = self.database
        if self._lorebook is None:
            self._lorebook = LorebookReadService(database)
        self._ensure_bound()
        return self._lorebook

    def initialize(self) -> None:
        if self._initialized:
            self._ensure_bound()
            return

        database = db.bind_peewee_database(db.make_peewee_database(self._database_path))
        database.connect(reuse_if_open=True)
        _run_migrations(database, self._database_path)
        self._database = database
        self._initialized = True
        self._ensure_bound()

    def close(self) -> None:
        if self._database is not None and not self._database.is_closed():
            self._database.close()
        self._initialized = False
        self._catalog = None
        self._lorebook = None

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
        gateway = DataServiceGateway(database_path)
        _GATEWAYS[cache_key] = gateway
    return gateway


def reset_data_service_gateways() -> None:
    """Close and clear cached gateways."""

    for gateway in list(_GATEWAYS.values()):
        gateway.close()
    _GATEWAYS.clear()


def _normalize_database_path(db_path: str | Path | None) -> Path:
    if db_path is None:
        return get_database_path()
    return Path(db_path).expanduser()


def _run_migrations(database: Database, database_path: Path) -> None:
    if str(database_path) == ":memory:":
        conn = database.connection()
        previous_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            run_migrations(conn)
        finally:
            conn.row_factory = previous_row_factory
        return

    conn = db.connect(database_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
