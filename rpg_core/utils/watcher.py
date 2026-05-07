"""FileWatcher — detect file changes and trigger Manager reload.

Any file change in a watched path triggers a reload (no distinction between
internal WebUI saves and external edits).  A debounce prevents rapid-fire
reloads from atomic-save strategies (DELETE + CREATE, etc.).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None

logger = logging.getLogger("rpg_core.watcher")

_DEBOUNCE_SEC = 0.5  # suppress duplicate events within this window


class _Handler(FileSystemEventHandler if _WATCHDOG_AVAILABLE else object):
    """Per-path handler registered with watchdog."""

    def __init__(self, watched_path: Path, on_reload: Callable[[], None]) -> None:
        self._path = watched_path
        self._is_dir = watched_path.is_dir()
        self._watch_str = str(watched_path)
        self._on_reload = on_reload

    def _accept(self, event) -> bool:
        if self._is_dir:
            return bool(event.src_path and event.src_path.startswith(self._watch_str))
        return event.src_path == self._watch_str

    def _on_any(self, event) -> None:
        if not self._accept(event):
            return
        logger.info("watchdog event: %s %s", event.event_type, event.src_path)
        self._on_reload()

    def on_modified(self, event) -> None:
        self._on_any(event)

    def on_created(self, event) -> None:
        self._on_any(event)

    def on_deleted(self, event) -> None:
        self._on_any(event)

    def on_moved(self, event) -> None:
        if self._accept(event):
            logger.info("watchdog event: moved %s -> %s", event.src_path, event.dest_path)
            self._on_reload()


class FileWatcher:
    """Singleton file-system watcher.

    Monitors registered file/directory paths and triggers the reload callback
    whenever a change is detected.  Debounced to coalesce rapid-fire events.
    """

    _instance: FileWatcher | None = None

    def __new__(cls) -> FileWatcher:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._callbacks: dict[Path, Callable[[], None]] = {}
        self._debounce_until: dict[Path, float] = {}
        self._observer: Observer | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, watched_path: Path, on_reload: Callable[[], None]) -> None:
        """Register a path to watch with a reload callback.

        Multiple callbacks for the same path are composed (all fire).
        """
        watched_path = watched_path.resolve()
        logger.info("register path=%s", watched_path)
        if watched_path in self._callbacks:
            existing = self._callbacks[watched_path]
            self._callbacks[watched_path] = lambda: (existing(), on_reload())
        else:
            self._callbacks[watched_path] = on_reload

    def start(self) -> None:
        """Start the watchdog observer (no-op if already running)."""
        if not _WATCHDOG_AVAILABLE:
            logger.warning("watchdog not available — file watching disabled")
            return
        if self._started:
            return

        logger.info("starting FileWatcher — %d paths to watch", len(self._callbacks))
        self._observer = Observer()
        for watched_path in list(self._callbacks):
            watch_target = str(watched_path.parent if watched_path.is_file() else watched_path)
            logger.info("  schedule handler dir=%s target=%s", watched_path, watch_target)
            if watched_path.exists():
                self._observer.schedule(
                    _Handler(watched_path, lambda p=watched_path: self._on_change(p)),
                    watch_target,
                    recursive=True,
                )
            else:
                logger.warning("  path does not exist, skipping: %s", watched_path)
        self._observer.start()
        self._started = True
        logger.info("FileWatcher started")

    def stop(self) -> None:
        """Stop the watchdog observer."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._started = False
            logger.info("FileWatcher stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_change(self, path: Path) -> None:
        """Called by watchdog (possibly multiple times in quick succession)."""

        # Per-path debounce within the configured window
        now = time.monotonic()
        deadline = self._debounce_until.get(path, 0.0)
        if now < deadline:
            logger.info("_on_change %s -> debounced", path)
            return
        self._debounce_until[path] = now + _DEBOUNCE_SEC

        logger.info("_on_change %s -> trigger reload", path)
        callback = self._callbacks.get(path)
        if callback:
            callback()
        else:
            logger.warning("  -> no callback registered for %s", path)


# Module-level singleton getter
_watcher: FileWatcher | None = None


def get_watcher() -> FileWatcher:
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher()
    return _watcher
