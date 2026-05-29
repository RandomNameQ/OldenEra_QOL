from __future__ import annotations

from dataclasses import replace
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from oldenera_qol.app.main import MainWindow
from oldenera_qol.app.widgets import FloatingActionOverlay, HotkeyCaptureEdit
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


def test_overlay_actions_show_requested_unit_workflow_buttons(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    try:
        actions = window._overlay_actions()

        assert [action[0] for action in actions] == [
            window.tr("overlay.openApp"),
            window.tr("overlay.selectGrid"),
            window.tr("overlay.selectUnitArea"),
            window.tr("overlay.savePanel"),
            window.tr("overlay.moveUnit"),
        ]
        assert [action[3] for action in actions] == ["", "", "", "", "SuccessButton"]
        assert "Stop" not in [action[0] for action in actions]
    finally:
        window.close()
        app.processEvents()


def test_floating_overlay_collapses_after_action_click() -> None:
    app = _app()
    triggered: list[str] = []
    overlay = FloatingActionOverlay(
        [("Select Grid", lambda: triggered.append("grid"), "Select grid cells", "")],
        lambda: QRect(10, 20, 800, 600),
    )
    try:
        overlay.show()
        overlay._set_expanded(True)
        app.processEvents()
        button = next(
            button
            for button in overlay.findChildren(QPushButton)
            if button.text() == "Select Grid"
        )

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert triggered == ["grid"]
        assert not overlay.panel.isVisible()
    finally:
        overlay.close()
        app.processEvents()


def test_hotkey_capture_edit_prompts_and_saves_pressed_shortcut() -> None:
    app = _app()
    captured: list[str] = []
    edit = HotkeyCaptureEdit("ctrl+1")
    edit.captured.connect(captured.append)
    try:
        edit.show()
        edit.setFocus()
        app.processEvents()

        assert edit.text() == "Press a key or shortcut..."

        QTest.keyClick(edit, Qt.Key.Key_F8, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()

        assert captured == ["ctrl+f8"]
        assert edit.text() == "ctrl+f8"
    finally:
        edit.close()
        app.processEvents()


def test_hotkey_capture_edit_restores_existing_value_on_escape() -> None:
    app = _app()
    captured: list[str] = []
    edit = HotkeyCaptureEdit("ctrl+2")
    edit.captured.connect(captured.append)
    try:
        edit.show()
        edit.setFocus()
        app.processEvents()

        QTest.keyClick(edit, Qt.Key.Key_Escape)
        app.processEvents()

        assert captured == []
        assert edit.text() == "ctrl+2"
    finally:
        edit.close()
        app.processEvents()


def test_settings_page_exposes_language_selector(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    try:
        selectors = [
            combo
            for combo in window.findChildren(QComboBox)
            if combo.objectName() == "LanguageSelector"
        ]

        assert len(selectors) == 1
        assert selectors[0].currentData() == window.settings.locale
    finally:
        window._update_locale("en")
        window.close()
        app.processEvents()


def test_changing_language_refreshes_visible_navigation(monkeypatch) -> None:
    monkeypatch.setattr(HotkeyManager, "register", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(HotkeyManager, "stop", lambda *_args, **_kwargs: None)
    app = _app()
    window = MainWindow()
    try:
        selectors = [
            combo
            for combo in window.findChildren(QComboBox)
            if combo.objectName() == "LanguageSelector"
        ]
        selector = selectors[0]
        selector.setCurrentIndex(selector.findData("ru"))
        app.processEvents()

        button_texts = {button.text() for button in window.findChildren(QPushButton)}
        assert "Настройки" in button_texts
        assert "Settings" not in button_texts
    finally:
        window._update_locale("en")
        window.close()
        app.processEvents()
