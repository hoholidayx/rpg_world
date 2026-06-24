"""FileWatcher debounce regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest


class _FakeTimer:
    def __init__(self, interval, function, args=None, kwargs=None):  # noqa: ANN001
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function(*self.args, **self.kwargs)


@pytest.fixture
def watcher_module():
    import rpg_core.utils.watcher as watcher_module

    watcher_module._watcher = None
    watcher_module.FileWatcher._instance = None
    yield watcher_module
    watcher_module._watcher = None
    watcher_module.FileWatcher._instance = None


def test_file_watcher_trailing_debounce_triggers_last_update(tmp_path: Path, monkeypatch, watcher_module):
    timers: list[_FakeTimer] = []

    def fake_timer(interval, function, args=None, kwargs=None):  # noqa: ANN001
        timer = _FakeTimer(interval, function, args=args, kwargs=kwargs)
        timers.append(timer)
        return timer

    monkeypatch.setattr(watcher_module.threading, "Timer", fake_timer)

    watcher = watcher_module.FileWatcher()
    watched_file = tmp_path / "data.json"
    watched_file.write_text("v1", encoding="utf-8")

    reloads: list[str] = []
    watcher.register(watched_file, lambda: reloads.append("reload"))

    watcher._on_change(watched_file)
    watcher._on_change(watched_file)
    watcher._on_change(watched_file)

    assert len(timers) == 3
    assert timers[0].cancelled is True
    assert timers[1].cancelled is True
    assert timers[2].cancelled is False
    assert reloads == []

    timers[0].fire()
    timers[1].fire()
    assert reloads == []

    timers[2].fire()
    assert reloads == ["reload"]


def test_file_watcher_clear_all_cancels_pending_timers(tmp_path: Path, monkeypatch, watcher_module):
    timers: list[_FakeTimer] = []

    def fake_timer(interval, function, args=None, kwargs=None):  # noqa: ANN001
        timer = _FakeTimer(interval, function, args=args, kwargs=kwargs)
        timers.append(timer)
        return timer

    monkeypatch.setattr(watcher_module.threading, "Timer", fake_timer)

    watcher = watcher_module.FileWatcher()
    watched_file = tmp_path / "data.json"
    watched_file.write_text("v1", encoding="utf-8")

    reloads: list[str] = []
    watcher.register(watched_file, lambda: reloads.append("reload"))
    watcher._on_change(watched_file)

    watcher.clear_all()

    assert timers[0].cancelled is True
    timers[0].fire()
    assert reloads == []
