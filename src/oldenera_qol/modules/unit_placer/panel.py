from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import json
from math import cos, pi, sin
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QBrush, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from oldenera_qol.app.widgets import LogPanel, ScreenshotCanvas, SelectionOverlay, make_header
from oldenera_qol.automation.mouse import AutomationTiming, DragExecutor, EmergencyStop
from oldenera_qol.automation.window import WindowController
from oldenera_qol.config.settings import AppSettings, SettingsService
from oldenera_qol.modules.base import ValidationIssue
from oldenera_qol.modules.placement_grid.geometry import build_deployment_grid
from oldenera_qol.modules.placement_grid.models import PlacementTemplate
from oldenera_qol.modules.placement_grid.repository import PlacementTemplateRepository
from oldenera_qol.modules.unit_placer.calibration import (
    CalibratedCell,
    UnitPlacerCalibration,
    UnitPlacerCalibrationRepository,
)
from oldenera_qol.modules.unit_placer.service import CalibratedUnitPlacerService
from oldenera_qol.modules.unit_placer.saved_panels import SavedUnitPanel, SavedUnitPanelRepository
from oldenera_qol.profiles.models import UnitProfile, validate_profile
from oldenera_qol.profiles.repository import ProfileRepository
from oldenera_qol.units.repository import UnitRepository
from oldenera_qol.vision.capture import ScreenCapture, WindowBounds
from oldenera_qol.vision.ocr import QuantityOcr
from oldenera_qol.vision.models import Rect


class _ScanSignals(QObject):
    finished = Signal(object, object)
    failed = Signal(str)


class _RunSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _PanelHighlightOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(38, 214, 91, 35))
        painter.setPen(QPen(QColor(38, 214, 91), 3))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))


class NumberedGridView(QGraphicsView):
    def __init__(self, cells) -> None:
        super().__init__()
        self.cells = cells
        self.calibrated_locations: set[tuple[int, int]] = set()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setMinimumHeight(360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.redraw()

    def set_calibrated_cells(self, calibrated_cells: list[CalibratedCell]) -> None:
        self.calibrated_locations = {(cell.row, cell.col) for cell in calibrated_cells}
        self.redraw()

    def labels(self) -> list[str]:
        return [str(index) for index in range(1, len(self.cells) + 1)]

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_to_scene()

    def redraw(self) -> None:
        self.scene.clear()
        for index, cell in enumerate(self.cells, start=1):
            calibrated = (cell.row, cell.col) in self.calibrated_locations
            polygon = QPolygonF([QPointF(*point) for point in self._hex_points(cell, 36)])
            item = self.scene.addPolygon(
                polygon,
                QPen(QColor("#26d65b" if calibrated else "#303849"), 3 if calibrated else 2),
                QBrush(QColor("#1f6f3e" if calibrated else "#202633")),
            )
            state = "selected" if calibrated else "not selected"
            item.setToolTip(f"Cell {index}: {state}")
            text = QGraphicsTextItem(str(index))
            text.setDefaultTextColor(QColor("#eef3f6"))
            text.setToolTip(f"Cell {index}: {state}")
            text.setPos(cell.center_x - text.boundingRect().width() / 2, cell.center_y - 12)
            text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(text)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.fit_to_scene()

    def fit_to_scene(self) -> None:
        if not self.scene.itemsBoundingRect().isEmpty():
            self.fitInView(
                self.scene.itemsBoundingRect().adjusted(-24, -24, 24, 24),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    @staticmethod
    def _hex_points(cell, radius: float) -> list[tuple[float, float]]:
        return [
            (
                cell.center_x + radius * cos(pi / 6 + index * pi / 3),
                cell.center_y + radius * sin(pi / 6 + index * pi / 3),
            )
            for index in range(6)
        ]


class UnitPlacerPanel(QWidget):
    id = "unit_placer"
    name = "Unit Placer"

    def __init__(
        self,
        settings: AppSettings,
        settings_service: SettingsService,
        profile_repository: ProfileRepository,
        window_controller: WindowController,
        emergency_stop: EmergencyStop,
        log,
        on_window_selected,
        set_automation_state,
        placement_template_repository: PlacementTemplateRepository | None = None,
        unit_repository: UnitRepository | None = None,
        app_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.settings_service = settings_service
        self.profile_repository = profile_repository
        self.window_controller = window_controller
        self.emergency_stop = emergency_stop
        self.log = log
        self.placement_template_repository = placement_template_repository
        self.unit_repository = unit_repository or UnitRepository(Path.cwd() / "data" / "units.json")
        self.app_root = app_root or Path.cwd()
        self.on_window_selected = on_window_selected
        self.set_automation_state = set_automation_state
        self.capture = ScreenCapture()
        self.current_screenshot = None
        self._calibrated_service_instance: CalibratedUnitPlacerService | None = None
        self._calibrated_service_key: tuple[str, int] | None = None
        self._placement_template_cache: dict[str, tuple[int, int, str]] = {}
        self._scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="unit-panel-scan")
        self._scan_future: Future | None = None
        self._scan_future_kind = ""
        self._scan_signals = _ScanSignals(self)
        self._scan_signals.finished.connect(self._position_update_finished)
        self._scan_signals.failed.connect(self._position_update_failed)
        self._run_future: Future | None = None
        self._run_signals = _RunSignals(self)
        self._run_signals.finished.connect(self._run_finished)
        self._run_signals.failed.connect(self._run_failed)
        self.destroyed.connect(lambda *_args: self.shutdown_scanner())
        self.pending_target: tuple[int, int] | None = None
        self.profile = UnitProfile(profile_name=self.settings.active_profile)
        self.calibration_repository = UnitPlacerCalibrationRepository(
            self.profile_repository.directory / "unit_placer_calibrations"
        )
        self.unit_panel_repository = SavedUnitPanelRepository(
            self.profile_repository.directory / "unit_panels"
        )
        self.calibration = self.calibration_repository.load(self.settings.active_profile)
        self.calibration_mode = ""
        self.panel_area_start: tuple[int, int] | None = None
        self.preview_panel_only = False
        self.numbered_grid_cells = build_deployment_grid(radius=36)
        self.selected_placement_template: PlacementTemplate | None = None
        self.latest_panel_detections = []
        self.saved_panel_detections = []
        self.selection_overlay: SelectionOverlay | None = None
        self._grid_selection_dirty = False
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update_detected_positions)

        self.canvas = ScreenshotCanvas()
        self.cell_map = NumberedGridView(self.numbered_grid_cells)
        self.cell_map.set_calibrated_cells(self.calibration.grid_cells)
        self.placement_template_list = QListWidget()
        self.placement_template_list.setIconSize(QSize(42, 42))
        self.placement_template_list.setUniformItemSizes(True)
        self.placement_template_summary = QLabel("No placement template selected")
        self.realtime_panel_checkbox = QCheckBox("Realtime unit panel")
        self.realtime_panel_checkbox.setChecked(True)
        self.realtime_panel_checkbox.toggled.connect(self._unit_panel_source_mode_changed)
        self.saved_unit_panel_selector_label = QLabel("Saved panel")
        self.saved_unit_panel_selector = QComboBox()
        self.saved_unit_panel_selector.currentIndexChanged.connect(
            self._saved_unit_panel_selector_changed
        )
        self.saved_unit_panel_list = QListWidget()
        self.saved_unit_panel_list.setUniformItemSizes(True)
        self.saved_unit_panel_summary = QLabel("No saved unit panel selected")
        self.saved_unit_panel_summary.setWordWrap(True)
        self.saved_unit_panel_preview = ScreenshotCanvas()
        self.module_log = LogPanel()
        self.update_positions_checkbox = QCheckBox("Update positions every second")
        self.update_positions_checkbox.toggled.connect(self._update_timer_toggled)
        self.readiness_indicator = QLabel()
        self.readiness_indicator.setObjectName("ReadinessIndicator")
        self.readiness_indicator.setFixedSize(16, 16)
        self.next_step_label = QLabel("")
        self.next_step_label.setWordWrap(True)
        self.next_step_label.setObjectName("StatusPill")
        self._build_layout()
        self.load_profile(self.settings.active_profile)
        self.refresh_placement_templates()
        self.refresh_unit_panels()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            make_header(
                "Unit Placer",
                "Calibrate the panel and grid, scan unit order, then move units into place.",
            )
        )

        tabs = QTabWidget()
        tabs.addTab(self._setup_tab(), "Placement Setup")
        tabs.addTab(self._cell_map_tab(), "Cell Map")
        tabs.addTab(self._unit_panel_tab(), "Unit Panel")
        layout.addWidget(tabs, 1)

    def _setup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        status = QHBoxLayout()
        status.addWidget(self.readiness_indicator, 0, Qt.AlignmentFlag.AlignVCenter)
        status.addWidget(self.next_step_label, 1)
        layout.addLayout(status)

        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Preview"))
        self.canvas.setMinimumWidth(156)
        left_layout.addWidget(self.canvas)
        self.canvas.clicked.connect(self._canvas_clicked)
        self.canvas.rectangle_selected.connect(self._canvas_rectangle_selected)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setObjectName("WorkflowScroll")
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._panel_scan_group())
        right_layout.addWidget(self._grid_calibration_group())
        right_layout.addWidget(self._placement_template_group())
        right_layout.addWidget(self._calibration_group())
        right_layout.addStretch(1)
        right_scroll.setWidget(right)
        splitter.addWidget(left)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 13)
        splitter.setStretchFactor(1, 37)
        splitter.setSizes([234, 1066])
        layout.addWidget(splitter, 1)

        layout.addWidget(QLabel("Module log"))
        layout.addWidget(self.module_log)
        return tab

    def _cell_map_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(
            make_header(
                "Cell Map",
                "Use these numbers as the reference when selecting battlefield cells in the game.",
            )
        )
        description = QLabel(
            "The app assigns these numbers to the hex grid. Click cells on the game screen in this order so the saved coordinates match the Placement Grid template."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(self.cell_map, 1)
        return tab

    def _unit_panel_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(
            make_header(
                "Unit Panel",
                "Saved unit panels can be reused when realtime panel capture is unavailable.",
            )
        )

        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Saved panels"))
        self.saved_unit_panel_list.setMinimumWidth(280)
        self.saved_unit_panel_list.currentItemChanged.connect(self._saved_unit_panel_list_selected)
        left_layout.addWidget(self.saved_unit_panel_list, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(
            self._action_button(
                "Refresh",
                self.refresh_unit_panels,
                "Reload saved unit panels from disk.",
            )
        )
        buttons.addWidget(
            self._action_button(
                "Select",
                self.select_listed_unit_panel,
                "Use the highlighted saved panel for saved-panel mode.",
            )
        )
        buttons.addWidget(
            self._action_button(
                "Delete",
                self.delete_selected_unit_panel,
                "Delete the highlighted saved panel and its image.",
                danger=True,
            )
        )
        left_layout.addLayout(buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview"))
        self.saved_unit_panel_preview.setMinimumHeight(220)
        right_layout.addWidget(self.saved_unit_panel_preview, 1)
        right_layout.addWidget(self.saved_unit_panel_summary)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return tab

    def cell_map_labels(self) -> list[str]:
        return self.cell_map.labels()

    def cell_map_reference_cells(self) -> list[tuple[int, int, str]]:
        return [
            (cell.row, cell.col, str(index))
            for index, cell in enumerate(self.numbered_grid_cells, start=1)
        ]

    def _panel_scan_group(self) -> QGroupBox:
        group = QGroupBox("1. Unit Area")
        layout = QVBoxLayout(group)
        description = QLabel(
            "Tell the app where the unit cards are. This is the panel with unit portraits and stack numbers."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        buttons.addWidget(
            self._action_button(
                "Select Unit Area",
                self.set_panel_area,
                "Open an overlay on the game window and drag around the unit cards.",
            )
        )
        buttons.addWidget(
            self._action_button(
                "Highlight Panel Area",
                self.highlight_panel_area,
                "Flash the saved panel rectangle over the game window.",
            )
        )
        buttons.addWidget(
            self._action_button(
                "Test Scan",
                self.test_scan,
                "Read the saved panel area and show detected units.",
            )
        )
        buttons.addWidget(
            self._action_button(
                "Save Panel",
                self.save_unit_panel,
                "Save the current unit area as a reusable panel image.",
            )
        )
        layout.addLayout(buttons)
        self.realtime_panel_checkbox.setToolTip(
            "When enabled, scan the live game panel. Disable it to use a saved panel image."
        )
        layout.addWidget(self.realtime_panel_checkbox)
        self.saved_unit_panel_selector_label.setToolTip("Saved panel used when realtime is disabled.")
        self.saved_unit_panel_selector.setToolTip("Select the saved panel image to scan and move from.")
        layout.addWidget(self.saved_unit_panel_selector_label)
        layout.addWidget(self.saved_unit_panel_selector)
        self.update_positions_checkbox.setToolTip("Rescan the panel once per second while enabled.")
        layout.addWidget(self.update_positions_checkbox)
        self._unit_panel_source_mode_changed(self.realtime_panel_checkbox.isChecked())
        return group

    def _grid_calibration_group(self) -> QGroupBox:
        group = QGroupBox("2. Numbered Grid Cells")
        layout = QVBoxLayout(group)
        description = QLabel(
            "Click battlefield cells in the same numeric order shown in the Cell Map and Placement Grid."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        buttons.addWidget(
            self._action_button(
                "Select Grid Cells",
                self.select_grid_cells,
                "Click battlefield cells in the numbered app-grid order.",
            )
        )
        layout.addLayout(buttons)
        return group

    def _calibration_group(self) -> QGroupBox:
        group = QGroupBox("4. Status")
        layout = QVBoxLayout(group)
        self.calibration_summary = QLabel("")
        self.calibration_summary.setWordWrap(True)
        layout.addWidget(self.calibration_summary)
        return group

    def _placement_template_group(self) -> QGroupBox:
        group = QGroupBox("3. Placement Template and Move")
        layout = QVBoxLayout(group)
        description = QLabel("Choose the saved layout you want to apply, then test scan and move units.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.placement_template_list.setMinimumHeight(100)
        self.placement_template_list.currentItemChanged.connect(self._placement_template_selected)
        refresh = QPushButton("Refresh Templates")
        refresh.clicked.connect(self.refresh_placement_templates)
        layout.addWidget(self.placement_template_list)
        layout.addWidget(self.placement_template_summary)
        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addWidget(
            self._action_button(
                "Move Units",
                self.move_units,
                "Drag matched units from calibrated source cells to template cells.",
                primary=True,
            )
        )
        buttons.addWidget(
            self._action_button(
                "Stop",
                self.stop,
                "Cancel remaining automated drags.",
                danger=True,
            )
        )
        layout.addLayout(buttons)
        return group

    def _action_button(
        self,
        text: str,
        handler,
        tooltip: str,
        primary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        if primary:
            button.setObjectName("PrimaryButton")
        if danger:
            button.setObjectName("DangerButton")
        button.clicked.connect(handler)
        return button

    def refresh_placement_templates(self) -> None:
        selected_name = self._current_template_name() or self.settings.last_placement_template
        self.placement_template_list.blockSignals(True)
        self.placement_template_list.clear()
        if self.placement_template_repository is None:
            self.placement_template_list.blockSignals(False)
            self.placement_template_summary.setText("Placement templates unavailable")
            self._update_workflow_status()
            return
        live_names: set[str] = set()
        for name in self.placement_template_repository.list_templates():
            live_names.add(name)
            unit_count, image_path = self._template_list_metadata(name)
            label = f"{name} ({unit_count} units)"
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(0, 56))
            absolute_image_path = self._absolute_path(image_path)
            if image_path and absolute_image_path.exists():
                item.setIcon(QIcon(str(absolute_image_path)))
            self.placement_template_list.addItem(item)
        self._placement_template_cache = {
            name: cached
            for name, cached in self._placement_template_cache.items()
            if name in live_names
        }
        row_to_select = -1
        if selected_name is not None:
            for row in range(self.placement_template_list.count()):
                if self.placement_template_list.item(row).text().split(" (", 1)[0] == selected_name:
                    row_to_select = row
                    break
        if row_to_select >= 0:
            self.placement_template_list.setCurrentRow(row_to_select)
        elif self.placement_template_list.count() > 0:
            self.placement_template_list.setCurrentRow(0)
        self.placement_template_list.blockSignals(False)
        self._placement_template_selected(self.placement_template_list.currentItem())
        self._update_workflow_status()

    def refresh_unit_panels(self, selected_name: str | None = None) -> None:
        selected_name = selected_name or self._current_unit_panel_name() or self.settings.last_unit_panel
        names = self.unit_panel_repository.list_panels()

        self.saved_unit_panel_selector.blockSignals(True)
        self.saved_unit_panel_list.blockSignals(True)
        self.saved_unit_panel_selector.clear()
        self.saved_unit_panel_list.clear()
        for name in names:
            label = name
            try:
                panel = self.unit_panel_repository.load(name)
                if panel.created_at:
                    label = f"{name} | {panel.created_at}"
            except (OSError, json.JSONDecodeError):
                panel = None
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setSizeHint(QSize(0, 48))
            self.saved_unit_panel_list.addItem(item)
            self.saved_unit_panel_selector.addItem(name, name)

        row_to_select = -1
        if selected_name:
            for row, name in enumerate(names):
                if name == selected_name:
                    row_to_select = row
                    break
        if row_to_select < 0 and names:
            row_to_select = 0
        if row_to_select >= 0:
            self.saved_unit_panel_selector.setCurrentIndex(row_to_select)
            self.saved_unit_panel_list.setCurrentRow(row_to_select)
        self.saved_unit_panel_selector.blockSignals(False)
        self.saved_unit_panel_list.blockSignals(False)
        self._saved_unit_panel_selector_changed(self.saved_unit_panel_selector.currentIndex())

    def save_unit_panel(self) -> None:
        if self.calibration.panel_scan_rect is None:
            self.append_log("Save Panel skipped: select the unit area first")
            return
        rect_issue = _panel_scan_rect_issue(self.calibration.panel_scan_rect)
        if rect_issue is not None:
            self.append_log(rect_issue)
            self.append_log("Save Panel skipped: reselect the full unit panel first")
            return
        panel_image = self._capture_live_panel_image(self._screen_bounds(), self.calibration)
        saved_panel = self.unit_panel_repository.save_image(
            panel_image,
            scan_summary=self._scan_summary(self.latest_panel_detections),
        )
        self.settings.last_unit_panel = saved_panel.name
        self.settings_service.save(self.settings)
        self.refresh_unit_panels(saved_panel.name)
        self.append_log(f"Saved unit panel: {saved_panel.name}")

    def select_listed_unit_panel(self) -> None:
        item = self.saved_unit_panel_list.currentItem()
        if item is None:
            self.append_log("Select saved panel skipped: no saved unit panel highlighted")
            return
        self._select_unit_panel_name(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def delete_selected_unit_panel(self) -> None:
        item = self.saved_unit_panel_list.currentItem()
        if item is None:
            self.append_log("Delete saved panel skipped: no saved unit panel highlighted")
            return
        name = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not name:
            return
        self.unit_panel_repository.delete(name)
        if self.settings.last_unit_panel == name:
            self.settings.last_unit_panel = ""
            self.settings_service.save(self.settings)
        self.refresh_unit_panels()
        self.append_log(f"Deleted saved unit panel: {name}")

    def _saved_unit_panel_selector_changed(self, index: int) -> None:
        if index < 0:
            self.saved_unit_panel_summary.setText("No saved unit panel selected")
            self.saved_unit_panel_preview.scene.clear()
            self._update_workflow_status()
            return
        name = str(self.saved_unit_panel_selector.itemData(index) or "")
        self._select_unit_panel_name(name, update_selector=False)

    def _saved_unit_panel_list_selected(self, current, _previous=None) -> None:
        if current is None:
            return
        self._select_unit_panel_name(str(current.data(Qt.ItemDataRole.UserRole) or ""))

    def _select_unit_panel_name(self, name: str, update_selector: bool = True) -> None:
        if not name:
            return
        if update_selector:
            for row in range(self.saved_unit_panel_selector.count()):
                if self.saved_unit_panel_selector.itemData(row) == name:
                    self.saved_unit_panel_selector.setCurrentIndex(row)
                    break
        self.saved_unit_panel_list.blockSignals(True)
        for row in range(self.saved_unit_panel_list.count()):
            if self.saved_unit_panel_list.item(row).data(Qt.ItemDataRole.UserRole) == name:
                self.saved_unit_panel_list.setCurrentRow(row)
                break
        self.saved_unit_panel_list.blockSignals(False)
        if self.settings.last_unit_panel != name:
            self.settings.last_unit_panel = name
            self.settings_service.save(self.settings)
        self._refresh_saved_unit_panel_preview(name)
        self._update_workflow_status()

    def _refresh_saved_unit_panel_preview(self, name: str) -> None:
        try:
            panel = self.unit_panel_repository.load(name)
        except (OSError, json.JSONDecodeError):
            self.saved_unit_panel_summary.setText(f"Saved panel missing metadata: {name}")
            self.saved_unit_panel_preview.scene.clear()
            return
        image_path = self.unit_panel_repository.image_path(panel)
        if not image_path.exists():
            self.saved_unit_panel_summary.setText(f"Saved panel image missing: {name}")
            self.saved_unit_panel_preview.scene.clear()
            return
        self.saved_unit_panel_preview.set_image_path(str(image_path))
        self.saved_unit_panel_summary.setText(
            f"Selected: {panel.name} | created: {panel.created_at or 'unknown'}"
        )

    def _unit_panel_source_mode_changed(self, realtime: bool) -> None:
        self.saved_unit_panel_selector_label.setVisible(not realtime)
        self.saved_unit_panel_selector.setVisible(not realtime)
        self.update_positions_checkbox.setEnabled(realtime)
        if not realtime:
            self.update_positions_checkbox.setChecked(False)
        self._update_workflow_status()

    def _placement_template_selected(self, current) -> None:
        if current is None or self.placement_template_repository is None:
            return
        template_name = current.text().split(" (", 1)[0]
        template = self.placement_template_repository.load(template_name)
        self.selected_placement_template = template
        if self.settings.last_placement_template != template.name:
            self.settings.last_placement_template = template.name
            self.settings_service.save(self.settings)
        self.placement_template_summary.setText(
            f"Loaded: {template.name} | units: {len(template.units)}"
        )
        self.append_log(f"Loaded placement template context: {template.name}")
        self._update_workflow_status()

    def capture_screen(self) -> None:
        self.preview_panel_only = False
        self.current_screenshot = self.capture.capture_window(self._screen_bounds())
        self.canvas.set_pixmap(self._image_to_pixmap(self.current_screenshot))
        self._refresh_canvas_overlays()
        self.append_log("Captured screen")
        self._update_workflow_status()

    def set_panel_area(self) -> None:
        if self.calibration.panel_scan_rect is not None and not self._confirm_reset(
            "Reset unit area"
        ):
            self.append_log("Unit area selection cancelled")
            return
        self.calibration_mode = "panel_area"
        self.panel_area_start = None
        existing = None
        if self.calibration.panel_scan_rect is not None:
            rect = self.calibration.panel_scan_rect
            existing = (rect.x, rect.y, rect.width, rect.height)
        overlay = SelectionOverlay(
            mode="rectangle",
            instruction="Drag around the unit cards. Right-click or Esc cancels.",
            existing_rect=existing,
        )
        overlay.rectangle_selected.connect(self._overlay_panel_area_selected)
        overlay.finished.connect(lambda: self.append_log("Panel area selection cancelled"))
        self._show_selection_overlay(overlay)
        self.append_log("Panel area selection overlay opened")

    def highlight_panel_area(self) -> None:
        rect = self.calibration.panel_scan_rect
        if rect is None:
            self.append_log("Highlight skipped: select the unit area first")
            return
        bounds = self._screen_bounds()
        overlay = _PanelHighlightOverlay()
        overlay.setGeometry(
            bounds.left + rect.x,
            bounds.top + rect.y,
            rect.width,
            rect.height,
        )
        overlay.show()
        overlay.raise_()
        QTimer.singleShot(1400, overlay.close)
        self._panel_highlight_overlay = overlay
        self.append_log("Highlighted panel scan area")

    def select_grid_cells(self) -> None:
        had_grid_cells = bool(self.calibration.grid_cells)
        if had_grid_cells and not self._confirm_reset("Reset numbered grid cells"):
            self.append_log("Grid-cell selection cancelled")
            return
        self.calibration_mode = "grid_cells"
        self.calibration = UnitPlacerCalibration(
            profile_name=self.calibration.profile_name,
            panel_scan_rect=self.calibration.panel_scan_rect,
            grid_cells=[],
            panel_source_cell_numbers=self.calibration.panel_source_cell_numbers,
        )
        self._grid_selection_dirty = had_grid_cells
        self.cell_map.set_calibrated_cells(self.calibration.grid_cells)
        self._update_calibration_summary()
        self._update_workflow_status()
        self._refresh_canvas_overlays()
        overlay = SelectionOverlay(
            mode="points",
            instruction="Click battlefield cells in app-number order. Right-click or Esc finishes.",
            reference_labels=self.cell_map_labels(),
            reference_cells=self.cell_map_reference_cells(),
        )
        overlay.point_selected.connect(self._overlay_grid_cell_selected)
        overlay.finished.connect(lambda: self._finish_overlay_calibration("Grid-cell selection finished"))
        self._show_selection_overlay(overlay)
        self.append_log("Grid-cell selection overlay opened")

    def _confirm_reset(self, title: str) -> bool:
        return (
            QMessageBox.question(
                self,
                title,
                "Are you sure you want to reset and start over?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def test_scan(self) -> None:
        if not self.realtime_panel_checkbox.isChecked():
            panel = self._selected_saved_unit_panel()
            if panel is None:
                self.append_log("Test scan skipped: no saved unit panel selected")
                return
            image_path = self.unit_panel_repository.image_path(panel)
            if not image_path.exists():
                self.append_log(f"Test scan skipped: saved unit panel image missing: {panel.name}")
                return
            if self._scan_future is not None and not self._scan_future.done():
                self.append_log("Scan already in progress")
                return
            service = self._calibrated_service()
            self.preview_panel_only = True
            self._scan_future_kind = "test"
            self.append_log(f"Saved unit panel scan started: {panel.name}")
            self._scan_future = self._scan_executor.submit(
                self._scan_saved_unit_panel,
                image_path,
                service,
            )
            self._scan_future.add_done_callback(self._emit_position_update)
            return

        if self.calibration.panel_scan_rect is None:
            detections = self._scan_panel_now(log_detections=True)
            self.latest_panel_detections = detections
            self._remember_successful_panel_scan(detections)
            self.append_log(f"Detected {len(detections)} panel units")
            self._refresh_canvas_overlays()
            return
        rect_issue = _panel_scan_rect_issue(self.calibration.panel_scan_rect)
        if rect_issue is not None:
            self.append_log(rect_issue)
            self.append_log("Test scan skipped: reselect the full unit panel first")
            return
        if self._scan_future is not None and not self._scan_future.done():
            self.append_log("Scan already in progress")
            return
        self.preview_panel_only = True
        bounds = self._screen_bounds()
        calibration = self.calibration
        service = self._calibrated_service()
        allowed_unit_names = self._selected_template_unit_names()
        if allowed_unit_names:
            self.append_log(
                "Recognition limited to placement template units: "
                + ", ".join(allowed_unit_names)
            )
        self._scan_future_kind = "test"
        self.append_log("Test scan started")
        self._scan_future = self._scan_executor.submit(
            self._capture_and_scan_positions,
            bounds,
            calibration,
            service,
        )
        self._scan_future.add_done_callback(self._emit_position_update)

    def _show_selection_overlay(self, overlay: SelectionOverlay) -> None:
        if self.selection_overlay is not None:
            self.selection_overlay.close()
        bounds = self._screen_bounds()
        overlay.setGeometry(bounds.left, bounds.top, bounds.width, bounds.height)
        overlay.destroyed.connect(lambda *_args: setattr(self, "selection_overlay", None))
        self.selection_overlay = overlay
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus()

    def _overlay_panel_area_selected(self, x: int, y: int, width: int, height: int) -> None:
        self._save_panel_rect(Rect(x, y, width, height))
        self.calibration_mode = ""
        if self.current_screenshot is None:
            self.capture_screen()

    def _overlay_grid_cell_selected(self, x: int, y: int) -> None:
        index = len(self.calibration.grid_cells)
        if index >= len(self.numbered_grid_cells):
            self.append_log("Numbered grid already has all cells")
            if self.selection_overlay is not None:
                self.selection_overlay.close()
            return
        logical_cell = self.numbered_grid_cells[index]
        grid_cells = [
            *self.calibration.grid_cells,
            CalibratedCell(row=logical_cell.row, col=logical_cell.col, x=x, y=y),
        ]
        self.calibration = UnitPlacerCalibration(
            profile_name=self.calibration.profile_name,
            panel_scan_rect=self.calibration.panel_scan_rect,
            grid_cells=grid_cells,
            panel_source_cell_numbers=self.calibration.panel_source_cell_numbers,
        )
        self._grid_selection_dirty = True
        if self.selection_overlay is None:
            self._save_calibration()
            self._grid_selection_dirty = False
        else:
            self._update_calibration_summary()
            self._update_workflow_status()
        self.append_log(
            f"Saved cell {index + 1} (row {logical_cell.row + 1}, col {logical_cell.col + 1}): {(x, y)}"
        )
        if len(grid_cells) >= len(self.numbered_grid_cells):
            self._finish_overlay_calibration("Numbered grid selection complete")
            if self.selection_overlay is not None:
                self.selection_overlay.close()

    def _finish_overlay_calibration(self, message: str) -> None:
        finishing_grid_selection = self.calibration_mode == "grid_cells"
        self.calibration_mode = ""
        if finishing_grid_selection and self._grid_selection_dirty:
            self._save_calibration()
            self._grid_selection_dirty = False
        self.append_log(message)

    def _save_panel_rect(self, rect: Rect) -> None:
        self.calibration = UnitPlacerCalibration(
            profile_name=self.calibration.profile_name,
            panel_scan_rect=rect,
            grid_cells=self.calibration.grid_cells,
            panel_source_cell_numbers=self.calibration.panel_source_cell_numbers,
        )
        self.panel_area_start = None
        self._save_calibration()
        self.append_log(f"Panel scan area saved: {(rect.x, rect.y, rect.width, rect.height)}")

    def _canvas_rectangle_selected(self, x: int, y: int, width: int, height: int) -> None:
        if self.calibration_mode != "panel_area":
            self.append_log("Use Select Unit Area before dragging a panel rectangle")
            return
        self._save_panel_rect(Rect(x, y, width, height))
        self.calibration_mode = ""

    def _canvas_clicked(self, x: int, y: int) -> None:
        if self.calibration_mode == "panel_area":
            if self.panel_area_start is None:
                self.panel_area_start = (x, y)
                self.append_log(f"Panel area start set: {(x, y)}; click the opposite corner or drag")
                return
            start_x, start_y = self.panel_area_start
            left = min(start_x, x)
            top = min(start_y, y)
            rect = Rect(left, top, abs(x - start_x), abs(y - start_y))
            if rect.width <= 0 or rect.height <= 0:
                self.append_log("Panel area ignored: rectangle must have positive size")
                return
            self.calibration = UnitPlacerCalibration(
                profile_name=self.calibration.profile_name,
                panel_scan_rect=rect,
                grid_cells=self.calibration.grid_cells,
                panel_source_cell_numbers=self.calibration.panel_source_cell_numbers,
            )
            self.panel_area_start = None
            self.calibration_mode = ""
            self._save_calibration()
            self.append_log(f"Panel scan area saved: {(rect.x, rect.y, rect.width, rect.height)}")
            return

        if self.calibration_mode == "grid_cells":
            self._overlay_grid_cell_selected(x, y)
            return

        self.append_log("No calibration action active")

    def test_detection(self) -> None:
        self.test_scan()

    def start(self) -> None:
        self.move_units()

    def move_units(self) -> None:
        if self._run_future is not None and not self._run_future.done():
            self.append_log("Move Units already in progress")
            return
        self.emergency_stop.reset()
        saved_panel = None
        if not self.realtime_panel_checkbox.isChecked():
            saved_panel = self._selected_saved_unit_panel()
            if saved_panel is None:
                self.append_log("Move Units skipped: no saved unit panel selected")
                return
            if not self.unit_panel_repository.image_path(saved_panel).exists():
                self.append_log(f"Move Units skipped: saved unit panel image missing: {saved_panel.name}")
                return
        issues = self.validate_profile()
        if issues:
            for issue in issues:
                self.append_log(issue.message)
            return
        template = self._selected_template()
        if template is None:
            self.append_log("Move Units skipped: no placement template selected")
            return
        bounds = self._screen_bounds()
        service = self._calibrated_service()
        timing = AutomationTiming(
            move_duration_seconds=self.settings.automation.move_duration_seconds,
            pause_between_moves_seconds=self.settings.automation.pause_between_moves_seconds,
            drag_button=self.settings.automation.drag_button,
        )
        self.set_automation_state("running")
        self._run_future = self._scan_executor.submit(
            self._run_automation,
            bounds,
            self.calibration,
            service,
            template,
            timing,
            list(self.saved_panel_detections),
            self.unit_panel_repository.image_path(saved_panel) if saved_panel is not None else None,
            saved_panel.name if saved_panel is not None else "",
        )
        self._run_future.add_done_callback(self._emit_run_finished)

    def stop(self) -> None:
        self.emergency_stop.request()
        if self._run_future is not None and not self._run_future.done():
            self.set_automation_state("stopping")
        self.append_log("Unit Placer stop requested")

    def validate_profile(self) -> list[ValidationIssue]:
        issues = [ValidationIssue(message) for message in validate_profile(self.profile)]
        if self.realtime_panel_checkbox.isChecked() and self.calibration.panel_scan_rect is None:
            issues.append(ValidationIssue("Panel scan area is not calibrated"))
        elif (
            self.realtime_panel_checkbox.isChecked()
            and self.calibration.panel_scan_rect is not None
            and (rect_issue := _panel_scan_rect_issue(self.calibration.panel_scan_rect)) is not None
        ):
            issues.append(ValidationIssue(rect_issue))
        grid_cell_count = len(self.calibration.grid_cells)
        required_grid_cell_count = len(self.numbered_grid_cells)
        if grid_cell_count <= 0:
            issues.append(ValidationIssue("Numbered grid cells are not calibrated"))
        elif grid_cell_count < required_grid_cell_count:
            issues.append(
                ValidationIssue(
                    "Numbered grid cells are not fully calibrated "
                    f"({grid_cell_count}/{required_grid_cell_count})"
                )
            )
        return issues

    def load_profile(self, profile_name: str) -> None:
        self.profile = UnitProfile(profile_name=profile_name)
        try:
            self.profile = self.profile_repository.load(profile_name)
        except FileNotFoundError:
            self.save_profile()
        self.calibration = self.calibration_repository.load(profile_name)
        self.refresh_profile_view()

    def save_profile(self) -> None:
        self.profile_repository.save(self.profile)

    def refresh_profile_view(self) -> None:
        self._update_calibration_summary()
        self._refresh_canvas_overlays()

    def append_log(self, message: str) -> None:
        self.module_log.append(message)

    def _calibrated_service(self) -> CalibratedUnitPlacerService:
        units = None
        repository_mtime = 0
        allowed_unit_names = self._selected_template_unit_names()
        if self._calibrated_service_instance is None:
            units = self.unit_repository.load()
        try:
            repository_mtime = self.unit_repository.path.stat().st_mtime_ns
        except OSError:
            pass
        key = (self.settings.tesseract_cmd, repository_mtime, allowed_unit_names)
        if self._calibrated_service_instance is None or self._calibrated_service_key != key:
            if units is None:
                units = self.unit_repository.load()
            if allowed_unit_names:
                filtered_units = {
                    name: record
                    for name, record in units.items()
                    if name in allowed_unit_names
                }
                if filtered_units:
                    units = filtered_units
            self._calibrated_service_instance = CalibratedUnitPlacerService(
                units=units,
                app_root=self.app_root,
                ocr=QuantityOcr(self.settings.tesseract_cmd),
                log=self.append_log,
            )
            self._calibrated_service_key = key
        return self._calibrated_service_instance

    def _selected_template_unit_names(self) -> tuple[str, ...]:
        template = self._selected_template()
        if template is None:
            return ()
        return tuple(sorted({unit.unit_name for unit in template.units if unit.unit_name}))

    def _selected_template(self) -> PlacementTemplate | None:
        if self.selected_placement_template is not None:
            return self.selected_placement_template
        current = self.placement_template_list.currentItem()
        if current is None or self.placement_template_repository is None:
            return None
        template_name = current.text().split(" (", 1)[0]
        self.selected_placement_template = self.placement_template_repository.load(template_name)
        return self.selected_placement_template

    def _save_calibration(self) -> None:
        self.calibration_repository.save(self.calibration)
        self.cell_map.set_calibrated_cells(self.calibration.grid_cells)
        self._update_calibration_summary()
        self._update_workflow_status()
        self._refresh_canvas_overlays()

    def _update_calibration_summary(self) -> None:
        if not hasattr(self, "calibration_summary"):
            return
        panel = "set" if self.calibration.panel_scan_rect is not None else "missing"
        self.calibration_summary.setText(
            f"Panel: {panel} | Numbered grid cells: "
            f"{len(self.calibration.grid_cells)}/{len(self.numbered_grid_cells)}"
        )

    def _update_workflow_status(self) -> None:
        if not hasattr(self, "next_step_label"):
            return
        self.next_step_label.setText(self._next_step_text())
        ready, issues = self._workflow_readiness()
        self.readiness_indicator.setProperty("ready", ready)
        color = "#26d65b" if ready else "#ff4545"
        border = "#8df0a8" if ready else "#ff9696"
        self.readiness_indicator.setStyleSheet(
            f"background: {color}; border: 1px solid {border}; border-radius: 8px;"
        )
        if ready:
            mode = "realtime" if self.realtime_panel_checkbox.isChecked() else "saved-panel"
            self.readiness_indicator.setToolTip(f"Ready to use in {mode} mode.")
        else:
            self.readiness_indicator.setToolTip(f"Not ready: {issues[0]}")

    def _next_step_text(self) -> str:
        if self.realtime_panel_checkbox.isChecked() and self.calibration.panel_scan_rect is None:
            return "Next: open 1. Unit Area and click Select Unit Area."
        if not self.realtime_panel_checkbox.isChecked() and self._selected_saved_unit_panel() is None:
            return "Next: turn off realtime only after selecting a saved Unit Panel."
        grid_cell_count = len(self.calibration.grid_cells)
        required_grid_cell_count = len(self.numbered_grid_cells)
        if grid_cell_count < required_grid_cell_count:
            return (
                "Next: open 2. Numbered Grid Cells and click Select Grid Cells "
                f"({grid_cell_count}/{required_grid_cell_count} saved)."
            )
        if self._selected_template() is None:
            return "Next: choose a Placement Template in 3. Placement Template and Move."
        return "Ready: click Test Scan to verify panel detection, then Move Units to place units."

    def _workflow_readiness(self) -> tuple[bool, list[str]]:
        issues = [issue.message for issue in self.validate_profile()]
        if not self.realtime_panel_checkbox.isChecked():
            issues = [
                issue
                for issue in issues
                if issue != "Panel scan area is not calibrated"
                and not issue.startswith("Panel scan area is too small")
            ]
            saved_panel = self._selected_saved_unit_panel()
            if saved_panel is None:
                issues.append("Saved unit panel is not selected")
            elif not self.unit_panel_repository.image_path(saved_panel).exists():
                issues.append(f"Saved unit panel image is missing: {saved_panel.name}")
        if self._selected_template() is None:
            issues.append("Placement template is not selected")
        return not issues, issues

    def _refresh_canvas_overlays(self, actions=None) -> None:
        rects: list[tuple] = []
        points: list[tuple[int, int]] = []
        lines: list[tuple[tuple[int, int], tuple[int, int]]] = []
        labels: list[tuple[int, int, str, str]] = []
        if self.calibration.panel_scan_rect is not None:
            rect = self.calibration.panel_scan_rect
            origin_x = rect.x
            origin_y = rect.y
            if self.preview_panel_only:
                origin_x = 0
                origin_y = 0
            rects.append((origin_x, origin_y, rect.width, rect.height, "#5badff"))
            for detection in self.latest_panel_detections:
                if detection.card_rect is None:
                    continue
                card = detection.card_rect
                x = origin_x + card.x
                y = origin_y + card.y
                recognized = detection.unit_name != "unknown"
                color = "#26d65b" if recognized else "#ff6b6b"
                rects.append((x, y, card.width, card.height, color))
                labels.append((x + 3, y + 3, self._panel_detection_label(detection), color))
        if not self.preview_panel_only:
            points.extend(cell.point for cell in self.calibration.grid_cells)
        if actions and not self.preview_panel_only:
            lines.extend((action.source, action.target) for action in actions)
        self.canvas.set_overlays(rects=rects, points=points, lines=lines, labels=labels)

    @staticmethod
    def _panel_detection_label(detection) -> str:
        name = detection.unit_name if detection.unit_name != "unknown" else "unknown"
        quantity = f" x{detection.quantity}" if detection.quantity is not None else ""
        return f"{detection.panel_index + 1}: {name}{quantity} ({detection.confidence:.2f})"

    def _screen_bounds(self) -> WindowBounds:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return WindowBounds(0, 0, 1920, 1080)
        geometry = screen.virtualGeometry()
        return WindowBounds(
            geometry.left(),
            geometry.top(),
            geometry.width(),
            geometry.height(),
        )

    def _update_timer_toggled(self, checked: bool) -> None:
        if checked:
            self.update_timer.start()
            self.append_log("Position updates enabled")
        else:
            self.update_timer.stop()
            self.append_log("Position updates disabled")

    def update_detected_positions(self) -> None:
        if not self.realtime_panel_checkbox.isChecked():
            return
        if self.calibration.panel_scan_rect is None:
            return
        if self._run_future is not None and not self._run_future.done():
            return
        if self._scan_future is not None and not self._scan_future.done():
            return
        bounds = self._screen_bounds()
        calibration = self.calibration
        service = self._calibrated_service()
        self._scan_future_kind = "position"
        self._scan_future = self._scan_executor.submit(
            self._capture_and_scan_positions,
            bounds,
            calibration,
            service,
        )
        self._scan_future.add_done_callback(self._emit_position_update)

    def _capture_and_scan_positions(
        self,
        bounds: WindowBounds,
        calibration: UnitPlacerCalibration,
        service: CalibratedUnitPlacerService,
    ):
        screenshot = self._capture_live_panel_image(bounds, calibration)
        detections = service.scan(
            screenshot,
            self._panel_image_calibration(calibration),
            log_detections=False,
        )
        return screenshot, detections

    def _scan_saved_unit_panel(
        self,
        image_path: Path,
        service: CalibratedUnitPlacerService,
    ):
        from PIL import Image

        with Image.open(image_path) as image:
            panel_image = image.convert("RGB")
        detections = service.scan_panel_image(panel_image, log_detections=False)
        return panel_image, detections

    def _capture_live_panel_image(
        self,
        bounds: WindowBounds,
        calibration: UnitPlacerCalibration,
    ):
        return self.capture.capture_window(self._panel_capture_bounds(bounds, calibration))

    def _emit_position_update(self, future: Future) -> None:
        try:
            screenshot, detections = future.result()
        except Exception as exc:
            self._scan_signals.failed.emit(str(exc))
            return
        self._scan_signals.finished.emit(screenshot, detections)

    def _position_update_finished(self, screenshot, detections) -> None:
        self.latest_panel_detections = detections
        if self._scan_future_kind == "test":
            self._remember_successful_panel_scan(detections)
            self.preview_panel_only = True
            self.current_screenshot = screenshot
            self.canvas.set_pixmap(self._scan_preview_pixmap(screenshot, detections), initial_zoom=1.85)
            self.canvas.clear_overlays()
            debug_path = self._save_scan_debug(screenshot, detections)
            self.append_log(f"Saved scan debug: {debug_path}")
            self._log_panel_detections(detections)
            self.append_log(f"Detected {len(detections)} panel units")
            self._scan_future_kind = ""
            return
        self._refresh_canvas_overlays()
        self._scan_future_kind = ""

    def _position_update_failed(self, message: str) -> None:
        if self._scan_future_kind == "test":
            self.append_log(f"Test scan failed: {message}")
        else:
            self.append_log(f"Position update failed: {message}")
        self._scan_future_kind = ""

    def _log_panel_detections(self, detections) -> None:
        ocr_unavailable = False
        for detection in detections:
            if detection.quantity_text and "tesseract" in detection.quantity_text.lower():
                ocr_unavailable = True
            if detection.unit_name == "unknown":
                self.append_log(
                    f"Panel card {detection.panel_index + 1}: unknown unit "
                    f"(confidence {detection.confidence:.2f})"
                    f"{_candidate_log_suffix(detection)}"
                )
            elif detection.quantity is None:
                detail = (
                    ""
                    if detection.quantity_text and "tesseract" in detection.quantity_text.lower()
                    else f": {detection.quantity_text}" if detection.quantity_text else ""
                )
                self.append_log(
                    f"Panel card {detection.panel_index + 1}: {detection.unit_name}; "
                    f"OCR returned no digits{detail}{_candidate_log_suffix(detection)}"
                )
            else:
                self.append_log(
                    f"Panel card {detection.panel_index + 1}: "
                    f"{detection.unit_name} x{detection.quantity}"
                    f"{_candidate_log_suffix(detection)}"
                )
        if ocr_unavailable:
            self.append_log("OCR unavailable: install Tesseract or set tesseract_cmd in Settings")

    def _remember_successful_panel_scan(self, detections) -> None:
        if not _usable_panel_detections(detections):
            return
        self.saved_panel_detections = list(detections)
        cells = [
            self.calibration.source_cell_for_panel_index(detection.panel_index)
            for detection in detections
        ]
        labels = [
            str(self.calibration.grid_cells.index(cell) + 1)
            for cell in cells
            if cell is not None and cell in self.calibration.grid_cells
        ]
        suffix = f" in source cells {', '.join(labels)}" if labels else ""
        self.append_log(f"Saved successful panel scan{suffix}")

    def _save_scan_debug(self, panel_image, detections) -> Path:
        debug_dir = self.app_root / "data" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        capture_path = debug_dir / "last_panel_capture.png"
        panel_image.save(capture_path)
        for detection in detections:
            if detection.card_rect is None:
                continue
            rect = detection.card_rect
            crop = panel_image.crop((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height))
            crop.save(debug_dir / f"last_panel_card_{detection.panel_index + 1}.png")
        scan_data = [
            {
                "panel_index": detection.panel_index + 1,
                "unit_name": detection.unit_name,
                "quantity": detection.quantity,
                "confidence": detection.confidence,
                "card_rect": None
                if detection.card_rect is None
                else {
                    "x": detection.card_rect.x,
                    "y": detection.card_rect.y,
                    "width": detection.card_rect.width,
                    "height": detection.card_rect.height,
                },
                "match_candidates": [
                    {"unit_name": name, "score": score}
                    for name, score in detection.match_candidates
                ],
            }
            for detection in detections
        ]
        path = debug_dir / "last_panel_scan.json"
        path.write_text(json.dumps(scan_data, indent=2), encoding="utf-8")
        return path

    def _run_automation(
        self,
        bounds: WindowBounds,
        calibration: UnitPlacerCalibration,
        service: CalibratedUnitPlacerService,
        template: PlacementTemplate,
        timing: AutomationTiming,
        saved_detections=None,
        saved_panel_path: Path | None = None,
        saved_panel_name: str = "",
    ) -> dict:
        saved_detections = list(saved_detections or [])
        logs: list[str] = []
        if saved_panel_path is not None:
            try:
                from PIL import Image

                with Image.open(saved_panel_path) as image:
                    panel_image = image.convert("RGB")
                detections = service.scan_panel_image(panel_image, log_detections=False)
                logs.append(
                    f"Using saved unit panel: {saved_panel_name or saved_panel_path.stem}"
                )
            except Exception as exc:
                return {
                    "detections": [],
                    "actions": [],
                    "logs": [f"Move Units skipped: saved unit panel scan failed: {exc}"],
                }
        else:
            try:
                panel_image = self._capture_live_panel_image(bounds, calibration)
                live_detections = service.scan(
                    panel_image,
                    self._panel_image_calibration(calibration),
                    log_detections=False,
                )
            except Exception as exc:
                live_detections = []
                logs.append(f"Live unit area scan failed: {exc}")

            if _usable_panel_detections(live_detections):
                detections = live_detections
            elif _usable_panel_detections(saved_detections):
                detections = saved_detections
                logs.append("Live unit area unavailable; using saved successful panel scan")
            elif live_detections:
                detections = live_detections
            else:
                return {
                    "detections": [],
                    "actions": [],
                    "logs": [*logs, "Move Units skipped: no live or saved panel scan is available"],
                }

        unknown_detections = [
            detection.panel_index + 1
            for detection in detections
            if detection.unit_name == "unknown"
        ]
        if unknown_detections:
            cards = ", ".join(str(index) for index in unknown_detections)
            return {
                "detections": detections,
                "actions": [],
                "logs": [
                    *logs,
                    f"Move Units skipped: scan has unknown units on panel card(s) {cards}"
                ],
            }
        plan = service.plan(detections, template, calibration)
        logs = [*logs, *plan.log_messages]
        if not plan.actions:
            logs.append("Move Units skipped: no calibrated moves planned")
            return {"detections": detections, "actions": [], "logs": logs}
        DragExecutor(timing).execute(plan, bounds, self.emergency_stop, logs.append)
        return {"detections": detections, "actions": plan.actions, "logs": logs}

    def _emit_run_finished(self, future: Future) -> None:
        try:
            result = future.result()
        except Exception as exc:
            self._run_signals.failed.emit(str(exc))
            return
        self._run_signals.finished.emit(result)

    def _run_finished(self, result: dict) -> None:
        self.latest_panel_detections = result["detections"]
        self._remember_successful_panel_scan(result["detections"])
        for message in result["logs"]:
            self.append_log(message)
        self._refresh_canvas_overlays(result["actions"])
        self.set_automation_state("idle")

    def _run_failed(self, message: str) -> None:
        self.append_log(f"Move Units failed: {message}")
        self.set_automation_state("idle")

    def closeEvent(self, event) -> None:
        self.shutdown_scanner()
        super().closeEvent(event)

    def shutdown_scanner(self) -> None:
        self.update_timer.stop()
        self._scan_executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _image_to_pixmap(image) -> QPixmap:
        from PIL.ImageQt import ImageQt

        return QPixmap.fromImage(ImageQt(image.convert("RGBA")))

    def _scan_preview_pixmap(self, panel_image, detections) -> QPixmap:
        preview = self._scan_preview_image(panel_image, detections)
        return self._image_to_pixmap(preview)

    def _scan_preview_image(self, panel_image, detections):
        from PIL import Image, ImageDraw, ImageFont

        image_width, image_height, *_layout = self._scan_preview_layout()
        preview = Image.new("RGB", (image_width, image_height), "#101318")
        draw = ImageDraw.Draw(preview)
        font = ImageFont.load_default()

        for index, cell in enumerate(self.numbered_grid_cells, start=1):
            points = [
                self._scan_preview_point(x, y)
                for x, y in self._hex_points(cell, 36)
            ]
            draw.polygon(points, fill="#27331f")
            draw.line([*points, points[0]], fill="#6d7c55", width=3)
            center_x, center_y = self._scan_preview_cell_center(cell)
            radius = self._scan_preview_radius()
            number = str(index)
            text_width, text_height = _preview_text_size(draw, number, font)
            draw.text(
                (
                    center_x - text_width / 2,
                    center_y - radius * 0.78 - text_height / 2,
                ),
                number,
                fill="#eef3f6",
                font=font,
            )

        unit_records = self.unit_repository.load()
        for detection in detections:
            cell = self._scan_preview_cell_for_detection(detection)
            if cell is None:
                continue
            center_x, center_y = self._scan_preview_cell_center(cell)
            recognized = detection.unit_name != "unknown"
            icon = None
            if recognized:
                record = unit_records.get(detection.unit_name)
                if record is not None:
                    icon = self._scan_preview_unit_icon(record.icon)
            if icon is not None:
                icon_left = center_x - icon.width // 2
                icon_top = center_y - icon.height // 2
                preview.paste(icon.convert("RGB"), (icon_left, icon_top), icon)
            else:
                self._draw_scan_preview_marker(draw, center_x, center_y, recognized, font)
            self._draw_scan_preview_quantity_badge(
                draw,
                center_x,
                center_y,
                "?" if detection.quantity is None else str(detection.quantity),
                font,
            )
            label = _clip_preview_text(detection.unit_name, 16)
            label_width, label_height = _preview_text_size(draw, label, font)
            draw.text(
                (center_x - label_width / 2, center_y - self._scan_preview_radius() - label_height - 2),
                label,
                fill="#eef3f6",
                font=font,
            )

        return preview

    def _scan_preview_cell_for_detection(self, detection):
        if detection.panel_index < 0 or detection.panel_index >= 7:
            return None
        calibrated_cell = self.calibration.source_cell_for_panel_index(detection.panel_index)
        if calibrated_cell is not None:
            return self._numbered_grid_cell_at(calibrated_cell.row, calibrated_cell.col)
        if detection.panel_index < len(self.numbered_grid_cells):
            return self.numbered_grid_cells[detection.panel_index]
        return None

    def _numbered_grid_cell_at(self, row: int, col: int):
        return next(
            (
                cell
                for cell in self.numbered_grid_cells
                if cell.row == row and cell.col == col
            ),
            None,
        )

    def _scan_preview_cell_center(self, cell) -> tuple[int, int]:
        _width, _height, min_x, min_y, scale, offset_x, offset_y = self._scan_preview_layout()
        return (
            int(round((cell.center_x - min_x) * scale + offset_x)),
            int(round((cell.center_y - min_y) * scale + offset_y)),
        )

    def _scan_preview_point(self, x: float, y: float) -> tuple[int, int]:
        _width, _height, min_x, min_y, scale, offset_x, offset_y = self._scan_preview_layout()
        return (
            int(round((x - min_x) * scale + offset_x)),
            int(round((y - min_y) * scale + offset_y)),
        )

    def _scan_preview_layout(self) -> tuple[int, int, float, float, float, float, float]:
        from math import ceil

        scale = 2.15
        margin = 70
        points = [
            point
            for cell in self.numbered_grid_cells
            for point in self._hex_points(cell, 36)
        ]
        min_x = min(x for x, _y in points)
        max_x = max(x for x, _y in points)
        min_y = min(y for _x, y in points)
        max_y = max(y for _x, y in points)
        natural_width = (max_x - min_x) * scale
        image_width = max(360, int(ceil(natural_width + margin * 2)))
        image_height = int(ceil((max_y - min_y) * scale + margin * 2))
        offset_x = margin + (image_width - natural_width - margin * 2) / 2
        offset_y = margin
        return image_width, image_height, min_x, min_y, scale, offset_x, offset_y

    @staticmethod
    def _scan_preview_radius() -> float:
        return 36 * 1.3

    @staticmethod
    def _hex_points(cell, radius: float) -> list[tuple[float, float]]:
        return [
            (
                cell.center_x + radius * cos(pi / 6 + index * pi / 3),
                cell.center_y + radius * sin(pi / 6 + index * pi / 3),
            )
            for index in range(6)
        ]

    def _scan_preview_unit_icon(self, icon_path: str):
        from PIL import Image

        path = self._absolute_path(icon_path)
        if not path.exists():
            return None
        try:
            icon = Image.open(path).convert("RGBA")
        except OSError:
            return None
        icon.thumbnail(
            (int(self._scan_preview_radius() * 1.7), int(self._scan_preview_radius() * 1.7)),
            Image.Resampling.LANCZOS,
        )
        return icon

    def _draw_scan_preview_marker(self, draw, center_x: int, center_y: int, recognized: bool, font) -> None:
        color = "#f2c14e" if recognized else "#ff4545"
        label = "!" if recognized else "?"
        radius = 18
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=color,
            outline="#101318",
            width=2,
        )
        text_width, text_height = _preview_text_size(draw, label, font)
        draw.text(
            (center_x - text_width / 2, center_y - text_height / 2),
            label,
            fill="#101318",
            font=font,
        )
        if not recognized:
            text = "unknown"
            label_width, label_height = _preview_text_size(draw, text, font)
            draw.text(
                (center_x - label_width / 2, center_y + radius + 2),
                text,
                fill=color,
                font=font,
            )

    def _draw_scan_preview_quantity_badge(
        self,
        draw,
        center_x: int,
        center_y: int,
        label: str,
        font,
    ) -> None:
        radius = self._scan_preview_radius()
        text_width, text_height = _preview_text_size(draw, label, font)
        badge_width = max(24, int(text_width) + 12)
        badge_height = max(20, int(text_height) + 8)
        left = int(center_x + radius * 0.10)
        top = int(center_y + radius * 0.35)
        draw.rounded_rectangle(
            (left, top, left + badge_width, top + badge_height),
            radius=8,
            fill="#101318",
            outline="#eef3f6",
            width=2,
        )
        draw.text(
            (
                left + (badge_width - text_width) / 2,
                top + (badge_height - text_height) / 2,
            ),
            label,
            fill="#eef3f6",
            font=font,
        )

    def _scan_panel_now(
        self,
        log_detections: bool,
        bounds: WindowBounds | None = None,
        service: CalibratedUnitPlacerService | None = None,
    ):
        service = service or self._calibrated_service()
        if self.calibration.panel_scan_rect is None:
            if self.current_screenshot is None:
                self.capture_screen()
            return service.scan(self.current_screenshot, self.calibration, log_detections)
        bounds = bounds or self._screen_bounds()
        panel_image = self.capture.capture_window(self._panel_capture_bounds(bounds, self.calibration))
        self.preview_panel_only = True
        self.current_screenshot = panel_image
        self.canvas.set_pixmap(self._image_to_pixmap(panel_image))
        return service.scan(
            panel_image,
            self._panel_image_calibration(self.calibration),
            log_detections,
        )

    def _panel_capture_bounds(
        self,
        bounds: WindowBounds,
        calibration: UnitPlacerCalibration,
    ) -> WindowBounds:
        rect = calibration.panel_scan_rect
        if rect is None:
            return bounds
        return WindowBounds(
            bounds.left + rect.x,
            bounds.top + rect.y,
            rect.width,
            rect.height,
        )

    @staticmethod
    def _panel_image_calibration(calibration: UnitPlacerCalibration) -> UnitPlacerCalibration:
        rect = calibration.panel_scan_rect
        if rect is None:
            return calibration
        return UnitPlacerCalibration(
            profile_name=calibration.profile_name,
            panel_scan_rect=Rect(0, 0, rect.width, rect.height),
            grid_cells=calibration.grid_cells,
            panel_source_cell_numbers=calibration.panel_source_cell_numbers,
        )

    def _template_list_metadata(self, name: str) -> tuple[int, str]:
        if self.placement_template_repository is None:
            return 0, ""
        path = self.placement_template_repository.path_for(name)
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        cached = self._placement_template_cache.get(name)
        if cached is not None and cached[0] == mtime:
            return cached[1], cached[2]
        template = self.placement_template_repository.load(name)
        metadata = (mtime, len(template.units), template.image_path)
        self._placement_template_cache[name] = metadata
        return metadata[1], metadata[2]

    def _current_template_name(self) -> str | None:
        if self.selected_placement_template is not None:
            return self.selected_placement_template.name
        current = self.placement_template_list.currentItem()
        if current is None:
            return None
        return current.text().split(" (", 1)[0]

    def _current_unit_panel_name(self) -> str | None:
        index = self.saved_unit_panel_selector.currentIndex()
        if index < 0:
            return None
        name = self.saved_unit_panel_selector.itemData(index)
        return str(name) if name else None

    def _selected_saved_unit_panel(self) -> SavedUnitPanel | None:
        name = self._current_unit_panel_name() or self.settings.last_unit_panel
        if not name:
            return None
        try:
            return self.unit_panel_repository.load(name)
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _scan_summary(detections) -> list[dict]:
        return [
            {
                "panel_index": detection.panel_index,
                "unit_name": detection.unit_name,
                "quantity": detection.quantity,
                "confidence": detection.confidence,
            }
            for detection in detections
        ]

    def _absolute_path(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.app_root / candidate


def _panel_scan_rect_issue(rect: Rect) -> str | None:
    if rect.width < 180 or rect.height < 45:
        return (
            "Panel scan area is too small for a 7-card unit panel; "
            "reselect the full unit area from the leftmost card to the rightmost card"
        )
    return None


def _usable_panel_detections(detections) -> bool:
    return bool(detections) and all(
        detection.unit_name != "unknown" for detection in detections
    )


def _candidate_log_suffix(detection) -> str:
    if not detection.match_candidates:
        return ""
    candidates = ", ".join(
        f"{name} {score:.2f}" for name, score in detection.match_candidates[:3]
    )
    return f"; candidates: {candidates}"


def _clip_preview_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _preview_text_size(draw, text: str, font) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top
