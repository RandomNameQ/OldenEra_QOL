from __future__ import annotations

from dataclasses import replace
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from oldenera_qol.app.main import MainWindow
from oldenera_qol.automation.window import WindowInfo
from oldenera_qol.hotkeys.manager import HotkeyManager
from oldenera_qol.vision.capture import WindowBounds


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_can_resize_to_compact_height(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    try:
        window.show()
        app.processEvents()

        window.resize(820, 520)
        app.processEvents()

        assert window.width() <= 860
        assert window.height() <= 560
    finally:
        window.close()


def test_overlay_target_allows_current_app_process_foreground(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    game_window = WindowInfo(100, "HeroesOldenEra", WindowBounds(10, 20, 810, 620))

    class FakeWindowController:
        def list_windows(self) -> list[WindowInfo]:
            return [game_window]

        def foreground_handle(self) -> int:
            return 200

        def process_id(self, handle: int) -> int | None:
            return os.getpid() if handle == 200 else 1234

    try:
        window.window_controller = FakeWindowController()
        window.selected_window = game_window

        assert window._overlay_target_window() == game_window
    finally:
        window.close()
        app.processEvents()


def test_overlay_target_uses_title_hint_when_current_app_process_is_foreground(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    game_window = WindowInfo(100, "HeroesOldenEra", WindowBounds(10, 20, 810, 620))

    class FakeWindowController:
        def list_windows(self) -> list[WindowInfo]:
            return [game_window]

        def foreground_handle(self) -> int:
            return 200

        def process_id(self, handle: int) -> int | None:
            return os.getpid() if handle == 200 else 1234

    try:
        window.window_controller = FakeWindowController()
        window.selected_window = None
        window.unit_placer_panel.profile = replace(
            window.unit_placer_panel.profile,
            window_title_hint="HeroesOldenEra",
        )

        assert window._overlay_target_window() == game_window
    finally:
        window.close()
        app.processEvents()
