"""Read-only SQL projection for the main Agent Persistent Memory layer."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistentMemoryItem:
    """One evidence-valid active memory projected for the main Context."""

    memory_id: str
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float


class PersistentMemoryStore:
    """Read the current Session ledger through the typed ``rpg_data`` boundary."""

    def __init__(self, session_id: str) -> None:
        self._session_id = str(session_id)
        self._last_snapshot: tuple[PersistentMemoryItem, ...] = ()
        self._refresh_lock = asyncio.Lock()

    @property
    def session_id(self) -> str:
        return self._session_id

    async def load_snapshot(self) -> tuple[PersistentMemoryItem, ...]:
        """Load one immutable projection off-loop, retaining a stale fallback."""

        async with self._refresh_lock:
            try:
                memories = tuple(await asyncio.to_thread(self._load_memories))
            except Exception:
                logger.warning(
                    "persistent memory projection refresh failed; using stale snapshot",
                    exc_info=True,
                )
                return self._last_snapshot
            self._last_snapshot = memories
            return memories

    def _load_memories(self) -> list[PersistentMemoryItem]:
        from rpg_data.services import get_data_service_gateway

        gateway = get_data_service_gateway()
        database = gateway.database
        try:
            bundles = gateway.dream.list_context_memories(self._session_id)
            return [
                PersistentMemoryItem(
                    memory_id=bundle.memory.id,
                    revision_number=bundle.current_revision.revision_number,
                    text=bundle.text,
                    memory_kind=bundle.memory_kind,
                    epistemic_status=bundle.epistemic_status,
                    salience=bundle.salience,
                )
                for bundle in bundles
            ]
        finally:
            # Peewee connections are thread-local. Close the worker's handle;
            # the shared gateway/database object remains initialized.
            if not database.is_closed():
                database.close()
