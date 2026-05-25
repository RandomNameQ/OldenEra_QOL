from __future__ import annotations

import os
import time
from concurrent.futures import Future
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
)

from oldenera_qol.automation.mouse import AutomationTiming, EmergencyStop
from oldenera_qol.automation.window import WindowController
from oldenera_qol.config.settings import AppSettings, SettingsService
from oldenera_qol.modules.placement_grid.models import PlacedUnit, PlacementTemplate
from oldenera_qol.modules.placement_grid.repository import PlacementTemplateRepository
from oldenera_qol.modules.unit_placer.calibration import CalibratedCell, UnitPlacerCalibration
from oldenera_qol.modules.unit_placer.panel import UnitPlacerPanel
from oldenera_qol.modules.unit_placer.panel_scanner import PanelUnitDetection
from oldenera_qol.modules.unit_placer.planner import MovePlan
from oldenera_qol.profiles.repository import ProfileRepository
from oldenera_qol.units.models import UnitRecord
from oldenera_qol.units.repository import UnitRepository
from oldenera_qol.vision.capture import WindowBounds
from oldenera_qol.vision.models import Rect


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _panel(tmp_path: Path) -> UnitPlacerPanel:
    _app()
    settings = AppSettings()
    return UnitPlacerPanel(
        settings=settings,
        settings_service=SettingsService(tmp_path / "config" / "settings.toml"),
        profile_repository=ProfileRepository(tmp_path / "profiles"),
        window_controller=WindowController(),
        emergency_stop=EmergencyStop(),
        log=lambda _message: None,
        on_window_selected=lambda _window: None,
        set_automation_state=lambda _state: None,
        placement_template_repository=PlacementTemplateRepository(
            tmp_path / "placement_grid_templates"
        ),
        unit_repository=UnitRepository(tmp_path / "data" / "units.json"),
    )


def _complete_grid_cells(panel: UnitPlacerPanel) -> list[CalibratedCell]:
    return [
        CalibratedCell(cell.row, cell.col, int(cell.center_x), int(cell.center_y))
        for cell in panel.numbered_grid_cells
    ]


def _button_by_text(panel: UnitPlacerPanel, text: str) -> QPushButton:
    for button in panel.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Button not found: {text}")


def test_unit_placer_only_shows_placement_template_group(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    group_titles = {group.title() for group in panel.findChildren(QGroupBox)}

    assert "1. Unit Area" in group_titles
    assert "2. Numbered Grid Cells" in group_titles
    assert "3. Placement Template and Move" in group_titles
    assert "4. Status" in group_titles
    assert "Game Window" not in group_titles
    assert "Templates" not in group_titles
    assert "Destination Slots" not in group_titles
    assert all(not group.isCheckable() for group in panel.findChildren(QGroupBox))
    tabs = panel.findChild(QTabWidget)
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Placement Setup",
        "Cell Map",
        "Unit Panel",
    ]
    assert panel.findChild(QScrollArea, "WorkflowScroll") is not None


def test_unit_placer_preview_uses_wider_setup_width(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    splitter = panel.findChild(QSplitter)

    assert splitter is not None
    sizes = splitter.sizes()
    assert sum(sizes) * 0.22 <= sizes[0] <= sum(sizes) * 0.32


def test_unit_placer_refresh_shows_saved_placement_templates(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    assert panel.placement_template_list.count() == 0

    repository = panel.placement_template_repository
    assert repository is not None
    repository.save(
        PlacementTemplate(
            name="test",
            units=[PlacedUnit("Skeleton", 7, 0, 18, "max")],
        )
    )

    panel.refresh_placement_templates()

    assert panel.placement_template_list.count() == 1
    assert panel.placement_template_list.item(0).text() == "test (1 units)"
    assert panel.placement_template_list.iconSize().width() == 42
    assert panel.placement_template_list.item(0).sizeHint().height() == 56


def test_unit_placer_shows_calibration_controls(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    button_texts = {button.text() for button in panel.findChildren(QPushButton)}

    assert {
        "Select Unit Area",
        "Highlight Panel Area",
        "Save Panel",
        "Select Grid Cells",
        "Test Scan",
        "Move Units",
        "Stop",
    }.issubset(button_texts)
    assert "Calibrate Source Cells" not in button_texts
    assert "Calibrate Target Grid" not in button_texts
    assert "Refresh Windows" not in button_texts
    assert "Select Window" not in button_texts
    assert "Capture" not in button_texts
    assert panel.update_positions_checkbox.text() == "Update positions every second"
    assert panel.realtime_panel_checkbox.text() == "Realtime unit panel"
    assert panel.findChild(QLabel, "ReadinessIndicator") is panel.readiness_indicator


def test_unit_placer_action_buttons_respond_within_200ms(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    panel = _panel(tmp_path)
    button_texts = [
        "Refresh",
        "Select",
        "Delete",
        "Select Unit Area",
        "Highlight Panel Area",
        "Test Scan",
        "Save Panel",
        "Select Grid Cells",
        "Refresh Templates",
        "Move Units",
        "Stop",
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(panel, "_scan_panel_now", lambda *_args, **_kwargs: [])
    saved_cell_counts = []

    def slow_save(calibration: UnitPlacerCalibration) -> Path:
        saved_cell_counts.append(len(calibration.grid_cells))
        time.sleep(0.25)
        return tmp_path / "profiles" / "unit_placer_calibrations" / "default.json"

    monkeypatch.setattr(panel.calibration_repository, "save", slow_save)

    elapsed_by_button: dict[str, float] = {}
    for text in button_texts:
        if text == "Select Grid Cells":
            panel.calibration = UnitPlacerCalibration(
                profile_name="default",
                panel_scan_rect=Rect(10, 20, 280, 80),
                grid_cells=_complete_grid_cells(panel),
            )

        button = _button_by_text(panel, text)
        start = time.perf_counter()
        button.click()
        elapsed_by_button[text] = time.perf_counter() - start
        app.processEvents()
        if panel.selection_overlay is not None:
            panel.selection_overlay.close()
            app.processEvents()

    assert saved_cell_counts == []
    assert all(elapsed <= 0.2 for elapsed in elapsed_by_button.values()), elapsed_by_button


def test_realtime_readiness_indicator_turns_green_when_setup_is_complete(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    repository = panel.placement_template_repository
    assert repository is not None
    repository.save(PlacementTemplate(name="test", units=[PlacedUnit("Skeleton", 0, 0, 1, "any")]))

    panel.refresh_placement_templates()
    panel._save_panel_rect(Rect(10, 20, 280, 80))
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=_complete_grid_cells(panel),
    )
    panel._update_workflow_status()

    assert panel.readiness_indicator.property("ready") is True
    assert "Ready to use in realtime mode" in panel.readiness_indicator.toolTip()


def test_saved_panel_readiness_indicator_does_not_require_realtime_area(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    repository = panel.placement_template_repository
    assert repository is not None
    repository.save(PlacementTemplate(name="test", units=[PlacedUnit("Skeleton", 0, 0, 1, "any")]))
    saved = panel.unit_panel_repository.save_image(Image.new("RGB", (280, 80), "black"))

    panel.refresh_placement_templates()
    panel.refresh_unit_panels(saved.name)
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=None,
        grid_cells=_complete_grid_cells(panel),
    )
    panel.realtime_panel_checkbox.setChecked(False)
    panel._update_workflow_status()

    assert panel.readiness_indicator.property("ready") is True
    assert "Ready to use in saved-panel mode" in panel.readiness_indicator.toolTip()


def test_readiness_indicator_stays_red_until_all_grid_cells_are_selected(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    repository = panel.placement_template_repository
    assert repository is not None
    repository.save(PlacementTemplate(name="test", units=[PlacedUnit("Skeleton", 0, 0, 1, "any")]))

    panel.refresh_placement_templates()
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=[CalibratedCell(0, 0, 100, 200)],
    )
    panel._update_workflow_status()

    assert panel.readiness_indicator.property("ready") is False
    assert "1/22" in panel.next_step_label.text()
    assert "not fully calibrated" in panel.readiness_indicator.toolTip()


def test_cell_map_marks_only_calibrated_cells_as_selected(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    assert any(item.toolTip() == "Cell 1: not selected" for item in panel.cell_map.scene.items())

    panel.cell_map.set_calibrated_cells([CalibratedCell(0, 0, 100, 200)])

    assert any(item.toolTip() == "Cell 1: selected" for item in panel.cell_map.scene.items())
    assert any(item.toolTip() == "Cell 2: not selected" for item in panel.cell_map.scene.items())


def test_unit_panel_tab_lists_and_deletes_saved_panels(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    saved = panel.unit_panel_repository.save_image(Image.new("RGB", (280, 80), "black"))

    panel.refresh_unit_panels()

    assert panel.saved_unit_panel_list.count() == 1
    assert panel.saved_unit_panel_selector.count() == 1
    assert panel.saved_unit_panel_list.item(0).text().startswith(saved.name)

    panel.saved_unit_panel_list.setCurrentRow(0)
    panel.delete_selected_unit_panel()

    assert panel.saved_unit_panel_list.count() == 0
    assert panel.saved_unit_panel_selector.count() == 0
    assert panel.unit_panel_repository.list_panels() == []


def test_unit_placer_remembers_last_selected_placement_template(tmp_path: Path) -> None:
    settings = AppSettings(last_placement_template="beta")
    repository = PlacementTemplateRepository(tmp_path / "placement_grid_templates")
    repository.save(PlacementTemplate(name="alpha"))
    repository.save(PlacementTemplate(name="beta"))
    panel = UnitPlacerPanel(
        settings=settings,
        settings_service=SettingsService(tmp_path / "config" / "settings.toml"),
        profile_repository=ProfileRepository(tmp_path / "profiles"),
        window_controller=WindowController(),
        emergency_stop=EmergencyStop(),
        log=lambda _message: None,
        on_window_selected=lambda _window: None,
        set_automation_state=lambda _state: None,
        placement_template_repository=repository,
        unit_repository=UnitRepository(tmp_path / "data" / "units.json"),
    )

    assert panel.selected_placement_template is not None
    assert panel.selected_placement_template.name == "beta"


def test_canvas_clicks_save_panel_area_and_numbered_grid_cells(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    panel.current_screenshot = object()
    panel.set_panel_area()
    panel._canvas_rectangle_selected(10, 20, 100, 60)

    assert panel.calibration.panel_scan_rect is not None
    assert panel.calibration.panel_scan_rect.x == 10
    assert panel.calibration.panel_scan_rect.width == 100

    panel.select_grid_cells()
    panel._canvas_clicked(30, 40)
    assert panel.calibration.grid_cells[0].row == 0
    assert panel.calibration.grid_cells[0].x == 30
    assert "1/22 saved" in panel.next_step_label.text()

    panel._canvas_clicked(50, 60)
    assert panel.calibration.grid_cells[1].row == 0
    assert panel.calibration.grid_cells[1].col == 1
    assert panel.calibration.grid_cells[1].x == 50


def test_select_grid_cells_requires_confirmation_before_resetting_existing_cells(
    tmp_path: Path,
    monkeypatch,
) -> None:
    panel = _panel(tmp_path)
    existing_cells = [CalibratedCell(0, 0, 30, 40)]
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=existing_cells,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    panel.select_grid_cells()

    assert panel.calibration.grid_cells == existing_cells
    assert panel.selection_overlay is None
    assert "cancelled" in panel.module_log.output.toPlainText()


def test_select_grid_cells_resets_after_confirmation(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=[CalibratedCell(0, 0, 30, 40)],
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    panel.select_grid_cells()

    assert panel.calibration.grid_cells == []
    assert panel.selection_overlay is not None
    assert panel.selection_overlay.mode == "points"


def test_grid_cell_selection_defers_saves_until_finished(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    saved_cell_counts = []

    def fake_save(calibration):
        saved_cell_counts.append(len(calibration.grid_cells))

    monkeypatch.setattr(panel.calibration_repository, "save", fake_save)

    panel.select_grid_cells()
    panel._overlay_grid_cell_selected(30, 40)
    panel._overlay_grid_cell_selected(50, 60)

    assert saved_cell_counts == []

    panel._finish_overlay_calibration("Grid-cell selection finished")

    assert saved_cell_counts == [2]


def test_grid_cell_overlay_selects_final_cell_on_mouse_release(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app()
    panel = _panel(tmp_path)
    monkeypatch.setattr(panel, "_screen_bounds", lambda: WindowBounds(0, 0, 800, 600))
    saved_cell_counts = []

    def fake_save(calibration):
        saved_cell_counts.append(len(calibration.grid_cells))

    monkeypatch.setattr(panel.calibration_repository, "save", fake_save)
    panel.select_grid_cells()
    assert panel.selection_overlay is not None

    for index, logical_cell in enumerate(panel.numbered_grid_cells[:-1]):
        panel.calibration = UnitPlacerCalibration(
            profile_name=panel.calibration.profile_name,
            panel_scan_rect=panel.calibration.panel_scan_rect,
            grid_cells=[
                *panel.calibration.grid_cells,
                CalibratedCell(logical_cell.row, logical_cell.col, index, index),
            ],
            panel_source_cell_numbers=panel.calibration.panel_source_cell_numbers,
        )
    panel._update_calibration_summary()
    panel._update_workflow_status()

    overlay = panel.selection_overlay
    point = QPoint(300, 400)
    QTest.mousePress(
        overlay,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()

    assert len(panel.calibration.grid_cells) == len(panel.numbered_grid_cells) - 1
    assert overlay.isVisible()

    QTest.mouseRelease(
        overlay,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()

    assert len(panel.calibration.grid_cells) == len(panel.numbered_grid_cells)
    assert panel.calibration.grid_cells[-1] == CalibratedCell(10, 1, 300, 400)
    assert saved_cell_counts == [len(panel.numbered_grid_cells)]


def test_selection_overlays_do_not_require_game_window(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    panel.set_panel_area()

    assert panel.selection_overlay is not None
    assert panel.selection_overlay.mode == "rectangle"


def test_grid_cell_selection_overlay_shows_reference_grid(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    panel.select_grid_cells()

    assert panel.selection_overlay is not None
    assert panel.selection_overlay.reference_labels() == panel.cell_map_labels()
    assert panel.selection_overlay.reference_cells() == panel.cell_map_reference_cells()


def test_highlight_panel_area_does_not_require_game_window(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    panel._save_panel_rect(Rect(10, 20, 280, 80))

    panel.highlight_panel_area()

    assert hasattr(panel, "_panel_highlight_overlay")
    assert panel._panel_highlight_overlay.geometry().width() == 280
    assert panel._panel_highlight_overlay.geometry().height() == 80


def test_cell_map_tab_shows_numbered_grid(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    labels = panel.cell_map_labels()

    assert labels[:4] == ["1", "2", "3", "4"]
    assert [(cell.row, cell.col) for cell in panel.numbered_grid_cells[:4]] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
    assert len(labels) == 22
    assert panel.numbered_grid_cells[-1].row == 10
    assert panel.numbered_grid_cells[-1].col == 1


def test_unit_placer_reuses_calibrated_service(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    first = panel._calibrated_service()
    second = panel._calibrated_service()

    assert first is second


def test_calibrated_service_limits_recognition_to_selected_template_units(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    skeleton = UnitRecord(
        name="Skeleton",
        unit_id="skeleton",
        icon="assets/units/icons/skeleton.png",
        visual_3d="",
        faction="",
        faction_id="",
        faction_image="",
    )
    angel = UnitRecord(
        name="Angel",
        unit_id="angel",
        icon="assets/units/icons/angel.png",
        visual_3d="",
        faction="",
        faction_id="",
        faction_image="",
    )
    panel.unit_repository.save({"Skeleton": skeleton, "Angel": angel})
    panel.selected_placement_template = PlacementTemplate(
        name="test",
        units=[PlacedUnit("Skeleton", 0, 0, 1, "max")],
    )

    service = panel._calibrated_service()

    assert set(service.units) == {"Skeleton"}


def test_position_update_skips_when_background_scan_is_busy(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    started = []

    class FakeFuture:
        def done(self) -> bool:
            return False

        def add_done_callback(self, _callback) -> None:
            pass

    class FakeExecutor:
        def submit(self, *_args, **_kwargs):
            started.append("scan")
            return FakeFuture()

    monkeypatch.setattr(panel, "_scan_executor", FakeExecutor())
    panel._save_panel_rect(Rect(10, 20, 280, 80))

    panel.update_detected_positions()
    panel.update_detected_positions()

    assert started == ["scan"]


def test_position_update_captures_only_saved_panel_area(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    panel._save_panel_rect(Rect(10, 20, 280, 80))
    captured_bounds: list[WindowBounds] = []
    scan_rects: list[Rect | None] = []

    class FakeCapture:
        def capture_window(self, bounds: WindowBounds):
            captured_bounds.append(bounds)
            return object()

    class FakeService:
        def scan(self, _screenshot, calibration, log_detections=False):
            scan_rects.append(calibration.panel_scan_rect)
            return []

    monkeypatch.setattr(panel, "capture", FakeCapture())

    panel._capture_and_scan_positions(
        WindowBounds(100, 200, 800, 600),
        panel.calibration,
        FakeService(),
    )

    assert captured_bounds == [WindowBounds(110, 220, 280, 80)]
    assert scan_rects == [Rect(0, 0, 280, 80)]


def test_test_scan_refreshes_panel_preview_before_drawing_panel_cards(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    panel._save_panel_rect(Rect(10, 20, 280, 80))
    panel_image = Image.new("RGB", (280, 80), "black")

    class FakeCapture:
        def capture_window(self, bounds: WindowBounds):
            assert bounds == WindowBounds(10, 20, 280, 80)
            return panel_image

    class FakeService:
        def scan(self, source, calibration, log_detections=True):
            assert source is panel_image
            assert calibration.panel_scan_rect == Rect(0, 0, 280, 80)
            return []

    class ImmediateExecutor:
        def submit(self, fn, *args):
            future = Future()
            future.set_result(fn(*args))
            return future

    monkeypatch.setattr(panel, "capture", FakeCapture())
    monkeypatch.setattr(panel, "_screen_bounds", lambda: WindowBounds(0, 0, 1920, 1080))
    monkeypatch.setattr(panel, "_scan_executor", ImmediateExecutor())
    monkeypatch.setattr(panel, "_calibrated_service", lambda: FakeService())

    panel.test_scan()

    assert panel.current_screenshot is panel_image
    assert panel.canvas.pixmap_item is not None
    assert panel.canvas.overlay_rects == []


def test_scan_preview_maps_panel_slots_to_deployment_grid_cells(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    panel_image = Image.new("RGB", (280, 80), "black")
    icon_path = tmp_path / "skeleton.png"
    Image.new("RGBA", (64, 64), (240, 30, 30, 255)).save(icon_path)
    panel.unit_repository.save(
        {
            "Skeleton": UnitRecord(
                name="Skeleton",
                unit_id="skeleton",
                icon=str(icon_path),
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            )
        }
    )
    detections = [
        PanelUnitDetection(
            unit_name="Skeleton",
            quantity=index + 1,
            confidence=0.91,
            panel_index=index,
            card_rect=Rect(index * 40, 0, 40, 80),
        )
        for index in range(7)
    ]

    preview = panel._scan_preview_image(panel_image, detections)

    assert preview.width > panel_image.width
    assert preview.height > panel_image.height
    assert panel._scan_preview_cell_for_detection(detections[0]) is panel.numbered_grid_cells[0]
    assert panel._scan_preview_cell_for_detection(detections[6]) is panel.numbered_grid_cells[6]

    first_center = panel._scan_preview_cell_center(panel.numbered_grid_cells[0])
    seventh_center = panel._scan_preview_cell_center(panel.numbered_grid_cells[6])
    assert preview.getpixel(first_center) == (240, 30, 30)
    assert preview.getpixel(seventh_center) == (240, 30, 30)


def test_scan_preview_uses_calibrated_source_cell_mapping(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(4, 0, 100, 200),
            CalibratedCell(6, 1, 110, 220),
        ],
    )
    detections = [
        PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0),
        PanelUnitDetection("Skeleton", 1, 0.91, panel_index=1),
    ]

    assert panel._scan_preview_cell_for_detection(detections[0]) is panel.numbered_grid_cells[8]
    assert panel._scan_preview_cell_for_detection(detections[1]) is panel.numbered_grid_cells[13]


def test_scan_preview_uses_manual_panel_cell_numbers(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(cell.row, cell.col, index, index)
            for index, cell in enumerate(panel.numbered_grid_cells)
        ],
        panel_source_cell_numbers=[3, 5, 7, 11, 15, 17, 19],
    )

    assert (
        panel._scan_preview_cell_for_detection(PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0))
        is panel.numbered_grid_cells[2]
    )
    assert (
        panel._scan_preview_cell_for_detection(PanelUnitDetection("Skeleton", 1, 0.91, panel_index=3))
        is panel.numbered_grid_cells[10]
    )
    assert (
        panel._scan_preview_cell_for_detection(PanelUnitDetection("Skeleton", 1, 0.91, panel_index=5))
        is panel.numbered_grid_cells[16]
    )


def test_test_scan_skips_too_small_panel_area(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    panel._save_panel_rect(Rect(120, 54, 47, 51))

    class FakeExecutor:
        def submit(self, *_args, **_kwargs):
            raise AssertionError("scan should not start for a tiny panel area")

    monkeypatch.setattr(panel, "_scan_executor", FakeExecutor())

    panel.test_scan()

    logs = panel.module_log.output.toPlainText().splitlines()
    assert any("too small" in message for message in logs)
    assert any("Test scan skipped" in message for message in logs)


def test_scan_preview_marks_unknown_units_on_deployment_grid(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    panel_image = Image.new("RGB", (280, 80), "black")
    detection = PanelUnitDetection(
        unit_name="unknown",
        quantity=None,
        confidence=0.1,
        panel_index=0,
        card_rect=Rect(0, 0, 40, 80),
    )

    preview = panel._scan_preview_image(panel_image, [detection])
    center_x, center_y = panel._scan_preview_cell_center(panel.numbered_grid_cells[0])

    red_pixels = 0
    for y in range(center_y - 14, center_y + 15):
        for x in range(center_x - 14, center_x + 15):
            red, green, blue = preview.getpixel((x, y))
            if red > 180 and green < 90 and blue < 90:
                red_pixels += 1

    assert red_pixels > 20


def test_move_units_aborts_when_scan_has_unknown_units(tmp_path: Path, monkeypatch) -> None:
    panel = _panel(tmp_path)
    calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=[
            CalibratedCell(cell.row, cell.col, index, index)
            for index, cell in enumerate(panel.numbered_grid_cells)
        ],
    )
    template = PlacementTemplate(
        name="test",
        units=[PlacedUnit("Skeleton", 0, 0, 1, "any")],
    )

    class FakeCapture:
        def capture_window(self, _bounds: WindowBounds):
            return object()

    class FakeService:
        def scan(self, _image, _calibration, log_detections=False):
            return [PanelUnitDetection("unknown", 1, 0.12, panel_index=2)]

        def plan(self, *_args):
            raise AssertionError("Move Units must not plan after an unknown scan")

    monkeypatch.setattr(panel, "capture", FakeCapture())

    result = panel._run_automation(
        WindowBounds(0, 0, 1920, 1080),
        calibration,
        FakeService(),
        template,
        AutomationTiming(0, 0, "left"),
    )

    assert result["actions"] == []
    assert "unknown units on panel card(s) 3" in result["logs"][0]


def test_test_scan_remembers_successful_panel_detections(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    panel.calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(cell.row, cell.col, index, index)
            for index, cell in enumerate(panel.numbered_grid_cells)
        ],
        panel_source_cell_numbers=[3, 5, 7, 11, 15, 17, 19],
    )
    detections = [
        PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0),
        PanelUnitDetection("Skeleton", 58, 0.91, panel_index=6),
    ]

    panel._scan_future_kind = "test"
    panel._position_update_finished(Image.new("RGB", (280, 80), "black"), detections)

    assert panel.saved_panel_detections == detections
    assert "Saved successful panel scan" in panel.module_log.output.toPlainText()


def test_test_scan_does_not_replace_saved_scan_with_unknown_units(tmp_path: Path) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    saved = [PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0)]
    panel.saved_panel_detections = list(saved)

    panel._scan_future_kind = "test"
    panel._position_update_finished(
        Image.new("RGB", (280, 80), "black"),
        [PanelUnitDetection("unknown", None, 0.1, panel_index=0)],
    )

    assert panel.saved_panel_detections == saved


def test_move_units_uses_saved_scan_when_live_unit_area_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    panel = _panel(tmp_path)
    calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=[
            CalibratedCell(cell.row, cell.col, index, index)
            for index, cell in enumerate(panel.numbered_grid_cells)
        ],
        panel_source_cell_numbers=[3, 5, 7, 11, 15, 17, 19],
    )
    saved = [PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0)]
    template = PlacementTemplate(
        name="test",
        units=[PlacedUnit("Skeleton", 0, 0, 1, "any")],
    )
    planned_detections = []

    class FakeCapture:
        def capture_window(self, _bounds: WindowBounds):
            return object()

    class FakeService:
        def scan(self, _image, _calibration, log_detections=False):
            return [PanelUnitDetection("unknown", None, 0.12, panel_index=0)]

        def plan(self, detections, _template, _calibration):
            planned_detections.extend(detections)
            return MovePlan([], ["planned from saved scan"])

    monkeypatch.setattr(panel, "capture", FakeCapture())

    result = panel._run_automation(
        WindowBounds(0, 0, 1920, 1080),
        calibration,
        FakeService(),
        template,
        AutomationTiming(0, 0, "left"),
        saved,
    )

    assert planned_detections == saved
    assert "using saved successful panel scan" in "\n".join(result["logs"])


def test_run_automation_uses_selected_saved_panel_image_without_live_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from PIL import Image

    panel = _panel(tmp_path)
    saved_image_path = tmp_path / "saved-panel.png"
    Image.new("RGB", (280, 80), "black").save(saved_image_path)
    calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 280, 80),
        grid_cells=[
            CalibratedCell(cell.row, cell.col, index, index)
            for index, cell in enumerate(panel.numbered_grid_cells)
        ],
    )
    detections = [PanelUnitDetection("Skeleton", 1, 0.91, panel_index=0)]
    template = PlacementTemplate(
        name="test",
        units=[PlacedUnit("Skeleton", 0, 0, 1, "any")],
    )
    planned_detections = []

    class FakeCapture:
        def capture_window(self, _bounds: WindowBounds):
            raise AssertionError("saved panel mode must not capture live unit area")

    class FakeService:
        def scan_panel_image(self, panel_image, log_detections=False):
            assert panel_image.size == (280, 80)
            return detections

        def scan(self, *_args, **_kwargs):
            raise AssertionError("saved panel mode must scan the saved image directly")

        def plan(self, source_detections, _template, _calibration):
            planned_detections.extend(source_detections)
            return MovePlan([], ["planned from selected saved panel"])

    monkeypatch.setattr(panel, "capture", FakeCapture())

    result = panel._run_automation(
        WindowBounds(0, 0, 1920, 1080),
        calibration,
        FakeService(),
        template,
        AutomationTiming(0, 0, "left"),
        saved_panel_path=saved_image_path,
        saved_panel_name="saved-panel",
    )

    assert planned_detections == detections
    assert "Using saved unit panel: saved-panel" in "\n".join(result["logs"])


def test_move_units_saved_panel_mode_requires_selection(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    panel.realtime_panel_checkbox.setChecked(False)

    panel.move_units()

    logs = panel.module_log.output.toPlainText().splitlines()
    assert any("no saved unit panel selected" in message for message in logs)
