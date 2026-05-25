from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
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
        self.profile_repository = ProfileRepository(ROOT / "profiles")
        self.unit_repository = UnitRepository(ROOT / "data" / "units.json")
        self.placement_template_repository = PlacementTemplateRepository(
            ROOT / "profiles" / "placement_grid_templates"
        )
        self.window_controller = WindowController()
        self.hotkey_manager = HotkeyManager()
        self.emergency_stop = EmergencyStop()
        self.selected_window: WindowInfo | None = None

        self.log_panel = LogPanel()
        self.stack = QStackedWidget()
        self.status_window = self._status_label("Window: not selected")
        self.status_profile = self._status_label(f"Profile: {self.settings.active_profile}")
        self.status_ocr = self._status_label(self._ocr_status_text())
        self.status_state = self._status_label("Automation: idle")

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
        )
        self.unit_library_panel = UnitLibraryPanel(
            app_root=ROOT,
            repository=self.unit_repository,
            log=self.log,
        )
        self.placement_grid_panel = PlacementGridPanel(
            app_root=ROOT,
            unit_repository=self.unit_repository,
            template_repository=self.placement_template_repository,
            log=self.log,
            on_templates_changed=self.unit_placer_panel.refresh_placement_templates,
        )
        self.unit_placer_panel.refresh_placement_templates()

        self._build_layout()
        self.control_overlay = FloatingActionOverlay(
            self._overlay_actions(),
            self._overlay_anchor_rect,
        )
        QTimer.singleShot(0, self.control_overlay.start)
        self._register_hotkeys()

    def _build_layout(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        brand = QLabel("OldenEra QOL")
        brand.setObjectName("Title")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(12)
        sidebar_layout.addWidget(nav_button("Dashboard", lambda: self.stack.setCurrentIndex(0)))
        sidebar_layout.addWidget(nav_button("Unit Placer", lambda: self.stack.setCurrentIndex(1)))
        sidebar_layout.addWidget(nav_button("Placement Grid", lambda: self.stack.setCurrentIndex(2)))
        sidebar_layout.addWidget(nav_button("Units", lambda: self.stack.setCurrentIndex(3)))
        sidebar_layout.addWidget(nav_button("Hotkeys", lambda: self.stack.setCurrentIndex(4)))
        sidebar_layout.addWidget(nav_button("Settings", lambda: self.stack.setCurrentIndex(5)))
        sidebar_layout.addWidget(nav_button("Logs", lambda: self.stack.setCurrentIndex(6)))
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
                "Dashboard",
                "Select a game window, configure visual profiles, and run modules from the sidebar.",
            )
        )
        modules = QListWidget()
        modules.addItems(
            [
                "Unit Placer - detect unit stacks, read quantities, and drag them to configured slots",
                "Placement Grid - build the full hex board and move unit icons around it",
                "Units - import and edit unit JSON data, including future 3D visual references",
                "More modules can be added through the module registry",
            ]
        )
        layout.addWidget(modules)
        layout.addStretch(1)
        return page

    def _hotkeys_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_header("Hotkeys", "Click a shortcut field and press a new combination."))
        table = QTableWidget(len(self.settings.hotkeys), 2)
        table.setHorizontalHeaderLabels(["Action", "Hotkey"])
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
        layout.addWidget(make_header("Settings", "Configure OCR and automation timing."))

        tesseract = QLineEdit(self.settings.tesseract_cmd)
        tesseract.textChanged.connect(self._update_tesseract)
        layout.addWidget(QLabel("Tesseract executable path"))
        layout.addWidget(tesseract)

        profile = QLineEdit(self.settings.active_profile)
        profile.textChanged.connect(self._update_active_profile)
        layout.addWidget(QLabel("Active profile name"))
        layout.addWidget(profile)
        layout.addStretch(1)
        return page

    def _logs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_header("Logs", "Module activity, skipped actions, and errors."))
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
        self.status_profile.setText(f"Profile: {self.settings.active_profile}")
        self.unit_placer_panel.load_profile(self.settings.active_profile)

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
        self.status_window.setText(f"Window: {window.title}")

    def set_automation_state(self, state: str) -> None:
        self.status_state.setText(f"Automation: {state}")

    def stop_all(self) -> None:
        self.emergency_stop.request()
        self.unit_placer_panel.stop()
        self.set_automation_state("stopped")
        self.log("Stop requested")

    def log(self, message: str) -> None:
        self.log_panel.append(message)
        self.unit_placer_panel.append_log(message)

    def _ocr_status_text(self) -> str:
        return "Tesseract: custom path" if self.settings.tesseract_cmd else "Tesseract: PATH"

    def closeEvent(self, event) -> None:
        self.control_overlay.close()
        self.hotkey_manager.stop()
        self.unit_placer_panel.shutdown_scanner()
        super().closeEvent(event)

    def _overlay_actions(self) -> list[OverlayAction]:
        return [
            ("Open App", self._show_main_window, "Show the main OldenEra QOL window.", ""),
            ("Capture", self.unit_placer_panel.capture_screen, "Capture the current screen.", ""),
            ("Unit Area", self.unit_placer_panel.set_panel_area, "Select the unit-card panel area.", ""),
            ("Grid Cells", self.unit_placer_panel.select_grid_cells, "Select battlefield cells.", ""),
            ("Test Scan", self.unit_placer_panel.test_scan, "Scan the configured unit panel.", ""),
            ("Move Units", self.unit_placer_panel.move_units, "Run the selected placement template.", "PrimaryButton"),
            ("Stop", self.stop_all, "Stop any running automation.", "DangerButton"),
        ]

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
