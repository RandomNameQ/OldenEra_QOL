from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsTextItem, QPushButton, QSpinBox

from oldenera_qol.modules.placement_grid.panel import PlacementGridPanel
from oldenera_qol.modules.placement_grid.repository import PlacementTemplateRepository
from oldenera_qol.units.repository import UnitRepository


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _panel(tmp_path: Path) -> PlacementGridPanel:
    app = _app()
    root = Path.cwd()
    panel = PlacementGridPanel(
        root,
        UnitRepository(root / "data" / "units.json"),
        PlacementTemplateRepository(tmp_path / "templates"),
        lambda _message: None,
    )
    panel.resize(1200, 800)
    panel.show()
    _flush_events(app)
    return panel


def _flush_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def test_grid_click_places_selected_unit_without_crashing(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)

    assert len(panel.placed_units) == 1
    assert (panel.placed_units[0].row, panel.placed_units[0].col) == (cell.row, cell.col)
    assert panel.unit_list.currentItem() is None


def test_grid_shift_click_places_unit_and_keeps_unit_selected(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    selected_name = panel.unit_list.currentItem().text()
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)

    assert len(panel.placed_units) == 1
    assert panel.unit_list.currentItem().text() == selected_name
    assert panel.placement_preview_item is not None


def test_dragging_placed_unit_moves_it_without_crashing(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    first = panel.cells[0]
    second = panel.cells[1]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        panel.grid_view.mapFromScene(first.center_x, first.center_y),
    )
    _flush_events(app)

    start = panel.grid_view.mapFromScene(first.center_x, first.center_y)
    end = panel.grid_view.mapFromScene(second.center_x, second.center_y)
    QTest.mousePress(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    QTest.mouseMove(panel.grid_view.viewport(), end, delay=20)
    QTest.mouseRelease(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    _flush_events(app)

    assert len(panel.placed_units) == 1
    assert (panel.placed_units[0].row, panel.placed_units[0].col) == (second.row, second.col)


def test_right_clicking_placed_unit_removes_it_from_grid(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)
    assert len(panel.placed_units) == 1

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)

    assert panel.placed_units == []
    assert panel.selected_cell is None
    assert panel.selected_label.text() == "Selected: none"


def test_numerical_quantity_control_is_not_shown(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    assert panel.findChildren(QSpinBox) == []
    assert panel.quantity_mode.findData("exact") == -1


def test_default_quantity_rule_is_max(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)

    labels = [
        item.toPlainText()
        for item in panel.scene.items()
        if isinstance(item, QGraphicsTextItem)
    ]
    assert "max" in labels
    assert panel.placed_units[0].quantity == 1
    assert panel.placed_units[0].quantity_mode == "max"


def test_word_quantity_mode_is_drawn_on_grid_unit_badge(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)

    labels = [
        item.toPlainText()
        for item in panel.scene.items()
        if isinstance(item, QGraphicsTextItem)
    ]
    assert "max" in labels
    assert "max 1" not in labels


def test_only_max_and_any_quantity_modes_are_available(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    assert panel.quantity_mode.findData("min") == -1
    assert panel.quantity_mode.findData("exact") == -1
    assert panel.quantity_mode.findData("max") >= 0
    assert panel.quantity_mode.findData("any") >= 0


def test_clicking_placed_unit_selects_it_for_quantity_update(tmp_path: Path) -> None:
    app = _app()
    panel = _panel(tmp_path)
    panel.unit_list.setCurrentRow(0)
    cell = panel.cells[0]

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)
    panel.selected_cell = None
    panel.selected_label.setText("Selected: none")
    panel.redraw()
    _flush_events(app)

    QTest.mouseClick(
        panel.grid_view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        panel.grid_view.mapFromScene(cell.center_x, cell.center_y),
    )
    _flush_events(app)
    panel.quantity_mode.setCurrentIndex(panel.quantity_mode.findData("any"))
    panel.update_selected_unit()

    assert panel.selected_cell == (cell.row, cell.col)
    assert len(panel.placed_units) == 1
    assert (panel.placed_units[0].row, panel.placed_units[0].col) == (cell.row, cell.col)
    assert panel.placed_units[0].quantity == 1
    assert panel.placed_units[0].quantity_mode == "any"


def test_template_controls_include_delete_and_unit_icon_picker(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    button_texts = {button.text() for button in panel.findChildren(QPushButton)}

    assert "Delete" in button_texts
    assert "Choose Icon" in button_texts
    assert "Choose Template Icon" not in button_texts
    assert "Choose Template Image" not in button_texts


def test_cell_numbers_are_drawn_on_grid(tmp_path: Path) -> None:
    panel = _panel(tmp_path)

    labels = [
        item.toPlainText()
        for item in panel.scene.items()
        if isinstance(item, QGraphicsTextItem)
    ]

    assert "1" in labels
    assert "2" in labels
    assert "22" in labels
    assert "23" not in labels
    assert [(cell.row, cell.col) for cell in panel.cells[:4]] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
