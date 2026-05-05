"""BaseManager — shared file-watching and reload logic for Manager subclasses."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from rpg_world.rpg_core.utils.watcher import get_watcher


class BaseManager:
    """Base class that registers a file watcher for external-change reloading.

    Subclasses must implement:
        ``reload(self)`` — re-read all data from disk into memory
        ``_data_dir(self) -> Path`` — the root path being watched
    """

    def __init__(self) -> None:
        self._watcher = get_watcher()
        self._watcher.register(self._data_dir(), lambda: self.reload())

    @abstractmethod
    def reload(self) -> None:
        """Re-read all data from disk into memory. Called on external changes."""
        raise NotImplementedError

    @abstractmethod
    def _data_dir(self) -> Path:
        """Return the file/directory path being watched."""
        raise NotImplementedError
