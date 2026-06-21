"""FileWatcher — detect file changes and trigger Manager reload.

Any file change in a watched path triggers a reload (no distinction between
internal WebUI saves and external edits).  A debounce prevents rapid-fire
reloads from atomic-save strategies (DELETE + CREATE, etc.).
"""

from __future__ import annotations

import logging
import threading
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

_DEBOUNCE_SEC = 1.0  # coalesce bursty editor saves and fire on the trailing edge


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
        self._debounce_seq: dict[Path, int] = {}
        self._debounce_timers: dict[Path, threading.Timer] = {}
        self._lock = threading.RLock()
        self._observer: Observer | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, watched_path: Path, on_reload: Callable[[], None]) -> None:
        """Register a path to watch with a reload callback.

        Multiple callbacks for the same path are composed (all fire).

        If the observer is already running, the new path is scheduled
        immediately so late-registering managers are covered as well.
        """
        watched_path = watched_path.resolve()
        logger.info("register path=%s", watched_path)
        if watched_path in self._callbacks:
            existing = self._callbacks[watched_path]
            self._callbacks[watched_path] = lambda: (existing(), on_reload())
        else:
            self._callbacks[watched_path] = on_reload

        # If observer already running, schedule this path now
        if self._started and self._observer is not None:
            watch_target = str(watched_path.parent if watched_path.is_file() else watched_path)
            if watched_path.exists():
                self._observer.schedule(
                    _Handler(watched_path, lambda p=watched_path: self._on_change(p)),
                    watch_target,
                    recursive=True,
                )
                logger.info("  -> scheduled with running observer")

    @property
    def is_available(self) -> bool:
        """Whether the optional watchdog dependency is installed."""
        return _WATCHDOG_AVAILABLE

    @property
    def is_running(self) -> bool:
        """Whether the underlying observer is currently running."""
        return self._started

    def start(self) -> bool:
        """Start the watchdog observer.

        Returns ``True`` when file watching is active after the call. The
        method is idempotent and returns ``False`` when watchdog is unavailable.
        """
        if not _WATCHDOG_AVAILABLE:
            logger.warning("watchdog not available — file watching disabled")
            return False
        if self._started:
            return True

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
        return True

    def clear_all(self) -> None:
        """Clear all registered callbacks and debounce state.

        Call before re-registering paths (e.g. after a workspace switch).
        Does **not** stop the observer — use :meth:`stop` first if needed.
        """
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._callbacks.clear()
            self._debounce_seq.clear()
            self._debounce_timers.clear()
        logger.info("FileWatcher — all callbacks cleared")

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
        with self._lock:
            seq = self._debounce_seq.get(path, 0) + 1
            self._debounce_seq[path] = seq
            old_timer = self._debounce_timers.pop(path, None)
            if old_timer is not None:
                old_timer.cancel()

            timer = threading.Timer(_DEBOUNCE_SEC, self._emit_change, args=(path, seq))
            timer.daemon = True
            self._debounce_timers[path] = timer
            logger.info("_on_change %s -> scheduled reload in %.2fs (seq=%s)", path, _DEBOUNCE_SEC, seq)
            timer.start()

    def _emit_change(self, path: Path, seq: int) -> None:
        with self._lock:
            current_seq = self._debounce_seq.get(path)
            if current_seq != seq:
                logger.info("_emit_change %s -> stale timer ignored (seq=%s current=%s)", path, seq, current_seq)
                return
            self._debounce_timers.pop(path, None)
            callback = self._callbacks.get(path)

        if callback:
            logger.info("_emit_change %s -> trigger reload (seq=%s)", path, seq)
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
