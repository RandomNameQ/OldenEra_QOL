from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from oldenera_qol.app.theme import DARK_STYLESHEET
from oldenera_qol.app.widgets import (
    FloatingActionOverlay,
    HotkeyCaptureEdit,
    LogPanel,
    OverlayAction,
    make_header,
    nav_button,
)
from oldenera_qol.automation.mouse import EmergencyStop
from oldenera_qol.automation.window import WindowController, WindowInfo
from oldenera_qol.config.settings import AppSettings, SettingsService, validate_hotkeys
from oldenera_qol.hotkeys.manager import HotkeyManager
from oldenera_qol.localization import Translator, supported_locales
from oldenera_qol.modules.placement_grid.panel import PlacementGridPanel
from oldenera_qol.modules.placement_grid.repository import PlacementTemplateRepository
from oldenera_qol.modules.unit_library.panel import UnitLibraryPanel
from oldenera_qol.modules.unit_placer.panel import UnitPlacerPanel
from oldenera_qol.paths import initialize_user_data
from oldenera_qol.profiles.repository import ProfileRepository
from oldenera_qol.units.repository import UnitRepository


ROOT = initialize_user_data()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OldenEra QOL")
        self.setMinimumSize(760, 480)
        self.resize(1280, 820)
        self.settings_service = SettingsService(ROOT / "config" / "settings.toml")
        self.settings = self.settings_service.load()
        self.translator = Translator(ROOT / "data" / "locales", self.settings.locale)
        self.setWindowTitle(self.tr("app.title"))
        self.profile_repository = ProfileRepository(ROOT / "profiles")
        self.unit_repository = UnitRepository(ROOT / "data" / "units.json")
        self.placement_template_repository = PlacementTemplateRepository(
            ROOT / "profiles" / "placement_grid_templates"
        )
        self.window_controller = WindowController()
        self.hotkey_manager = HotkeyManager()
        self.emergency_stop = EmergencyStop()
        self.selected_window: WindowInfo | None = None
        self.automation_state = "idle"

        self.log_panel = LogPanel()
        self._create_module_panels()
        self._create_status_labels()

        self._build_layout()
        self.control_overlay = FloatingActionOverlay(
            self._overlay_actions(),
            self._overlay_anchor_rect,
        )
        QTimer.singleShot(0, self.control_overlay.start)
        self._register_hotkeys()

    def _create_module_panels(self) -> None:
        self.unit_placer_panel = UnitPlacerPanel(
            settings=self.settings,
            settings_service=self.settings_service,
            profile_repository=self.profile_repository,
            window_controller=self.window_controller,
            emergency_stop=self.emergency_stop,
            log=self.log,
            on_window_selected=self.set_selected_window,
            set_automation_state=self.set_automation_state,
            placement_template_repository=self.placement_template_repository,
            unit_repository=self.unit_repository,
            app_root=ROOT,
            translator=self.translator,
        )
        self.unit_library_panel = UnitLibraryPanel(
            app_root=ROOT,
            repository=self.unit_repository,
            log=self.log,
            translator=self.translator,
            locale=self.settings.locale,
        )
        self.placement_grid_panel = PlacementGridPanel(
            app_root=ROOT,
            unit_repository=self.unit_repository,
            template_repository=self.placement_template_repository,
            log=self.log,
            on_templates_changed=self.unit_placer_panel.refresh_placement_templates,
            translator=self.translator,
            locale=self.settings.locale,
        )
        self.unit_placer_panel.refresh_placement_templates()

    def _create_status_labels(self) -> None:
        window_text = (
            self.tr("status.windowSelected", title=self.selected_window.title)
            if self.selected_window is not None
            else self.tr("status.windowNotSelected")
        )
        self.status_window = self._status_label(window_text)
        self.status_profile = self._status_label(
            self.tr("status.profile", profile=self.settings.active_profile)
        )
        self.status_ocr = self._status_label(self._ocr_status_text())
        self.status_state = self._status_label(
            self.tr("status.automation", state=self.automation_state)
            if self.automation_state != "idle"
            else self.tr("status.automationIdle")
        )

    def _build_layout(self) -> None:
        central = QWidget()
        self.stack = QStackedWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        brand = QLabel(self.tr("app.title"))
        brand.setObjectName("Title")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(12)
        sidebar_layout.addWidget(nav_button(self.tr("nav.dashboard"), lambda: self.stack.setCurrentIndex(0)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.unitPlacer"), lambda: self.stack.setCurrentIndex(1)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.placementGrid"), lambda: self.stack.setCurrentIndex(2)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.units"), lambda: self.stack.setCurrentIndex(3)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.hotkeys"), lambda: self.stack.setCurrentIndex(4)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.settings"), lambda: self.stack.setCurrentIndex(5)))
        sidebar_layout.addWidget(nav_button(self.tr("nav.logs"), lambda: self.stack.setCurrentIndex(6)))
        sidebar_layout.addStretch(1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 14, 18, 18)
        status = QHBoxLayout()
        status.addWidget(self.status_window)
        status.addWidget(self.status_profile)
        status.addWidget(self.status_ocr)
        status.addWidget(self.status_state)
        status.addStretch(1)
        content_layout.addLayout(status)

        self.stack.addWidget(self._scrollable_stack_page(self._dashboard_page()))
        self.stack.addWidget(self._scrollable_stack_page(self.unit_placer_panel))
        self.stack.addWidget(self._scrollable_stack_page(self.placement_grid_panel))
        self.stack.addWidget(self._scrollable_stack_page(self.unit_library_panel))
        self.stack.addWidget(self._scrollable_stack_page(self._hotkeys_page()))
        self.stack.addWidget(self._scrollable_stack_page(self._settings_page()))
        self.stack.addWidget(self._scrollable_stack_page(self._logs_page()))
        content_layout.addWidget(self.stack)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(content)
        self.setCentralWidget(central)

    def _status_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("StatusPill")
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return label

    def _scrollable_stack_page(self, page: QWidget) -> QScrollArea:
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setMinimumSize(0, 0)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_area.setWidget(page)
        return scroll_area

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            make_header(
                self.tr("dashboard.title"),
                self.tr("dashboard.subtitle"),
            )
        )
        modules = QListWidget()
        modules.addItems(
            [
                self.tr("dashboard.unitPlacer"),
                self.tr("dashboard.placementGrid"),
                self.tr("dashboard.units"),
                self.tr("dashboard.moreModules"),
            ]
        )
        layout.addWidget(modules)
        layout.addStretch(1)
        return page

    def _hotkeys_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_header(self.tr("hotkeys.title"), self.tr("hotkeys.subtitle")))
        table = QTableWidget(len(self.settings.hotkeys), 2)
        table.setHorizontalHeaderLabels([self.tr("hotkeys.action"), self.tr("hotkeys.hotkey")])
        table.horizontalHeader().setStretchLastSection(True)
        for row, (action, hotkey) in enumerate(self.settings.hotkeys.items()):
            table.setItem(row, 0, QTableWidgetItem(action))
            editor = HotkeyCaptureEdit(hotkey)
            editor.captured.connect(lambda value, action=action: self._update_hotkey(action, value))
            table.setCellWidget(row, 1, editor)
        layout.addWidget(table)
        layout.addStretch(1)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_header(self.tr("settings.title"), self.tr("settings.subtitle")))

        language = QComboBox()
        language.setObjectName("LanguageSelector")
        for locale in supported_locales():
            language.addItem(locale.label, locale.code)
        language.setCurrentIndex(max(0, language.findData(self.settings.locale)))
        language.currentIndexChanged.connect(lambda _index: self._update_locale(language.currentData()))
        layout.addWidget(QLabel(self.tr("settings.language")))
        layout.addWidget(language)

        tesseract = QLineEdit(self.settings.tesseract_cmd)
        tesseract.textChanged.connect(self._update_tesseract)
        layout.addWidget(QLabel(self.tr("settings.tesseractPath")))
        layout.addWidget(tesseract)

        profile = QLineEdit(self.settings.active_profile)
        profile.textChanged.connect(self._update_active_profile)
        layout.addWidget(QLabel(self.tr("settings.activeProfile")))
        layout.addWidget(profile)
        layout.addStretch(1)
        return page

    def _logs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_header(self.tr("logs.title"), self.tr("logs.subtitle")))
        layout.addWidget(self.log_panel)
        return page

    def _update_hotkey(self, action: str, value: str) -> None:
        updated = dict(self.settings.hotkeys)
        updated[action] = value
        issues = validate_hotkeys(updated)
        if issues:
            self.log("; ".join(issues))
            return
        self.settings.hotkeys = updated
        self.settings_service.save(self.settings)
        self._register_hotkeys()
        self.log(f"Updated hotkey {action}: {value}")

    def _update_tesseract(self, value: str) -> None:
        self.settings.tesseract_cmd = value.strip()
        self.settings_service.save(self.settings)
        self.status_ocr.setText(self._ocr_status_text())

    def _update_active_profile(self, value: str) -> None:
        self.settings.active_profile = value.strip() or "default"
        self.settings_service.save(self.settings)
        self.status_profile.setText(self.tr("status.profile", profile=self.settings.active_profile))
        self.unit_placer_panel.load_profile(self.settings.active_profile)

    def _update_locale(self, value) -> None:
        locale = str(value or "en")
        if locale == self.settings.locale:
            return
        previous_index = self.stack.currentIndex()
        self.unit_placer_panel.shutdown_scanner()
        self.control_overlay.close()
        old_central = self.centralWidget()
        self.settings.locale = locale
        self.translator.set_locale(self.settings.locale)
        self.settings_service.save(self.settings)
        self.setWindowTitle(self.tr("app.title"))
        self._create_module_panels()
        self._create_status_labels()
        self._build_layout()
        self.stack.setCurrentIndex(max(0, min(previous_index, self.stack.count() - 1)))
        self.control_overlay = FloatingActionOverlay(
            self._overlay_actions(),
            self._overlay_anchor_rect,
        )
        self.control_overlay.start()
        self._register_hotkeys()
        if old_central is not None:
            old_central.setParent(None)
            old_central.deleteLater()

    def _register_hotkeys(self) -> None:
        issues = self.hotkey_manager.register(
            self.settings.hotkeys,
            {
                "start_unit_placer": self.unit_placer_panel.start,
                "stop_all": self.stop_all,
                "capture_window": self.unit_placer_panel.capture_screen,
            },
        )
        for issue in issues:
            self.log(issue)

    def set_selected_window(self, window: WindowInfo) -> None:
        self.selected_window = window
        self.status_window.setText(self.tr("status.windowSelected", title=window.title))

    def set_automation_state(self, state: str) -> None:
        self.automation_state = state
        self.status_state.setText(self.tr("status.automation", state=state))

    def stop_all(self) -> None:
        self.emergency_stop.request()
        self.unit_placer_panel.stop()
        self.set_automation_state("stopped")
        self.log("Stop requested")

    def log(self, message: str) -> None:
        self.log_panel.append(message)
        self.unit_placer_panel.append_log(message)

    def _ocr_status_text(self) -> str:
        return self.tr("status.tesseractCustom") if self.settings.tesseract_cmd else self.tr("status.tesseractPath")

    def closeEvent(self, event) -> None:
        self.control_overlay.close()
        self.hotkey_manager.stop()
        self.unit_placer_panel.shutdown_scanner()
        super().closeEvent(event)

    def _overlay_actions(self) -> list[OverlayAction]:
        return [
            (
                self.tr("overlay.openApp"),
                self._show_main_window,
                self.tr("overlay.openAppTooltip"),
                "",
            ),
            (
                self.tr("overlay.selectGrid"),
                self.unit_placer_panel.select_grid_cells,
                self.tr("overlay.selectGridTooltip"),
                "",
            ),
            (
                self.tr("overlay.selectUnitArea"),
                self.unit_placer_panel.set_panel_area,
                self.tr("overlay.selectUnitAreaTooltip"),
                "",
            ),
            (
                self.tr("overlay.savePanel"),
                self.unit_placer_panel.save_unit_panel,
                self.tr("overlay.savePanelTooltip"),
                "",
            ),
            (
                self.tr("overlay.moveUnit"),
                self.unit_placer_panel.move_units,
                self.tr("overlay.moveUnitTooltip"),
                "SuccessButton",
            ),
        ]

    def tr(self, key: str, **values: object) -> str:
        return self.translator.t(key, **values)

    def _show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _overlay_anchor_rect(self) -> QRect:
        window = self._overlay_target_window()
        if window is None:
            return QRect()
        return QRect(
            window.bounds.left,
            window.bounds.top,
            window.bounds.width,
            window.bounds.height,
        )

    def _overlay_target_window(self) -> WindowInfo | None:
        foreground_handle = self.window_controller.foreground_handle()
        if foreground_handle is None:
            return None
        windows = self.window_controller.list_windows()
        foreground_is_current_app = self._is_current_app_process(foreground_handle)
        if self.selected_window is not None:
            for window in windows:
                if window.handle == self.selected_window.handle and (
                    window.handle == foreground_handle or foreground_is_current_app
                ):
                    return window
        hints = [
            self.unit_placer_panel.profile.window_title_hint.strip(),
            "HeroesOldenEra",
            "OldenEra",
        ]
        for hint in [value for value in hints if value]:
            normalized_hint = hint.lower()
            for window in windows:
                title = window.title.lower()
                if (
                    (window.handle == foreground_handle or foreground_is_current_app)
                    and normalized_hint in title
                    and title != self.windowTitle().lower()
                    and "qol" not in title
                ):
                    return window
        return None

    def _is_current_app_process(self, window_handle: int) -> bool:
        process_id = self.window_controller.process_id(window_handle)
        return process_id == os.getpid()


def run_app() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()
