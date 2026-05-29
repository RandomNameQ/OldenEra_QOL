from __future__ import annotations

from collections.abc import Callable
from math import cos, pi, sin
from pathlib import Path

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPen, QBrush, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from oldenera_qol.app.widgets import make_header
from oldenera_qol.localization import DEFAULT_LOCALE, Translator
from oldenera_qol.modules.placement_grid.geometry import build_deployment_grid, cell_at_point, nearest_cell
from oldenera_qol.modules.placement_grid.layout import move_or_swap_unit, update_unit_at
from oldenera_qol.modules.placement_grid.models import GridCell, PlacedUnit, PlacementTemplate
from oldenera_qol.modules.placement_grid.repository import PlacementTemplateRepository
from oldenera_qol.units.models import PSEUDO_ANY_UNIT_NAME, UnitRecord
from oldenera_qol.units.repository import UnitRepository


class DraggableUnitItem(QGraphicsPixmapItem):
    def __init__(
        self,
        placed: PlacedUnit,
        cells: list[GridCell],
        on_selected,
        on_moved,
        pixmap: QPixmap,
    ) -> None:
        super().__init__(pixmap)
        self.placed = placed
        self.cells = cells
        self.on_selected = on_selected
        self.on_moved = on_moved
        self._dragging = False
        self._press_scene_pos: QPointF | None = None
        self.quantity_badge: QGraphicsEllipseItem | None = None
        self.quantity_badge_text: QGraphicsTextItem | None = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._add_quantity_badge()
        self.drag_ring = self._add_selection_ring()
        self.drag_ring.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.on_selected(self.placed)
        self._dragging = False
        self._press_scene_pos = event.scenePos()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press_scene_pos is None:
            event.accept()
            return
        delta = event.scenePos() - self._press_scene_pos
        if not self._dragging and abs(delta.x()) + abs(delta.y()) < 4:
            event.accept()
            return
        if not self._dragging:
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setOpacity(0.72)
            self.setZValue(50)
            self.drag_ring.show()
        self.setPos(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if not self._dragging:
            self._press_scene_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setOpacity(1.0)
        self.drag_ring.hide()
        cell = nearest_cell(self.cells, self.pos().x(), self.pos().y())
        self.setPos(cell.center_x, cell.center_y)
        placed = self.placed
        on_moved = self.on_moved
        self._dragging = False
        self._press_scene_pos = None
        QTimer.singleShot(0, lambda: on_moved(placed, cell))
        event.accept()

    def _add_quantity_badge(self) -> None:
        label = self._quantity_badge_label()
        if not label:
            return
        badge_width = max(34, len(label) * 8 + 12)
        self.quantity_badge = QGraphicsEllipseItem(-badge_width / 2, 7, badge_width, 20, self)
        self.quantity_badge.setPen(QPen(QColor("#10131a"), 2))
        self.quantity_badge.setBrush(QBrush(QColor("#10131a")))
        self.quantity_badge.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.quantity_badge.setZValue(1)

        self.quantity_badge_text = QGraphicsTextItem(label, self)
        self.quantity_badge_text.setDefaultTextColor(QColor("#ffffff"))
        self.quantity_badge_text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.quantity_badge_text.setPos(-badge_width / 2 + 7, 2)
        self.quantity_badge_text.setZValue(2)

    def _quantity_badge_label(self) -> str:
        mode = self.placed.normalized_mode()
        return "" if mode == "exact" else mode

    def _add_selection_ring(self) -> QGraphicsEllipseItem:
        ring = QGraphicsEllipseItem(-34, -34, 68, 68, self)
        ring.setPen(QPen(QColor("#59a7ff"), 3))
        ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        ring.setZValue(-1)
        return ring


class HexGridView(QGraphicsView):
    def __init__(self, panel: PlacementGridPanel) -> None:
        super().__init__()
        self.panel = panel
        self.dragged_item: DraggableUnitItem | None = None
        self.drag_start_scene_pos: QPointF | None = None
        self.drag_active = False
        self.setMinimumHeight(360)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_to_scene()

    def fit_to_scene(self) -> None:
        if self.scene() is not None and not self.scene().itemsBoundingRect().isEmpty():
            self.fitInView(
                self.scene().itemsBoundingRect().adjusted(-24, -24, 24, 24),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            draggable_item = self._draggable_item_at(event.position().toPoint())
            if draggable_item is not None:
                placed = draggable_item.placed
                QTimer.singleShot(
                    0,
                    lambda: self.panel.remove_placed_unit(placed.row, placed.col),
                )
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            draggable_item = self._draggable_item_at(event.position().toPoint())
            if draggable_item is not None:
                self.panel.clear_hovered_cell()
                draggable_item.on_selected(draggable_item.placed)
                self.dragged_item = draggable_item
                self.drag_start_scene_pos = self.mapToScene(event.position().toPoint())
                self.drag_active = False
                event.accept()
                return
            scene_pos = self.mapToScene(event.position().toPoint())
            keep_unit_selected = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self.panel.can_place_selected_unit(scene_pos.x(), scene_pos.y()):
                x = scene_pos.x()
                y = scene_pos.y()
                QTimer.singleShot(
                    0,
                    lambda: self.panel.place_selected_unit(x, y, keep_unit_selected),
                )
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.dragged_item is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.drag_start_scene_pos is not None:
                delta = scene_pos - self.drag_start_scene_pos
                if not self.drag_active and abs(delta.x()) + abs(delta.y()) < 4:
                    event.accept()
                    return
            if not self.drag_active:
                self.drag_active = True
                self.dragged_item.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.dragged_item.setOpacity(0.72)
                self.dragged_item.setZValue(50)
                self.dragged_item.drag_ring.show()
            self.dragged_item.setPos(scene_pos)
            event.accept()
            return
        if self._draggable_item_at(event.position().toPoint()) is None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.panel.update_hovered_cell(scene_pos.x(), scene_pos.y())
        else:
            self.panel.clear_hovered_cell()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.dragged_item is not None:
            item = self.dragged_item
            was_dragged = self.drag_active
            self.dragged_item = None
            self.drag_start_scene_pos = None
            self.drag_active = False
            item.setCursor(Qt.CursorShape.OpenHandCursor)
            item.setOpacity(1.0)
            item.drag_ring.hide()
            if was_dragged:
                cell = nearest_cell(item.cells, item.pos().x(), item.pos().y())
                item.setPos(cell.center_x, cell.center_y)
                placed = item.placed
                QTimer.singleShot(0, lambda: self.panel._unit_moved(placed, cell))
            else:
                self.panel.redraw()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self.dragged_item is None:
            self.panel.clear_hovered_cell()
        super().leaveEvent(event)

    @staticmethod
    def _draggable_item(item: QGraphicsItem | None) -> DraggableUnitItem | None:
        while item is not None:
            if isinstance(item, DraggableUnitItem):
                return item
            item = item.parentItem()
        return None

    def _draggable_item_at(self, position) -> DraggableUnitItem | None:
        for item in self.items(position):
            draggable_item = self._draggable_item(item)
            if draggable_item is not None:
                return draggable_item
        return None


class TemplateIconDialog(QDialog):
    def __init__(
        self,
        units: dict[str, UnitRecord],
        app_root: Path,
        icon_for_path: Callable[[Path], QIcon],
        parent: QWidget | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose template icon")
        self.units = units
        self.app_root = app_root
        self.icon_for_path = icon_for_path
        self.locale = locale
        self.selected_icon_path = ""
        self._pending_icon_rows: list[int] = []
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search units")
        self.unit_list = QListWidget()
        self.unit_list.setMinimumSize(360, 420)
        self.unit_list.setUniformItemSizes(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.unit_list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        self.search.textChanged.connect(self._refresh)
        self.unit_list.itemDoubleClicked.connect(lambda _item: self.accept())
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._refresh()

    def accept(self) -> None:
        current = self.unit_list.currentItem()
        if current is None:
            return
        self.selected_icon_path = str(current.data(Qt.ItemDataRole.UserRole) or "")
        super().accept()

    def _refresh(self) -> None:
        selected_name = self.unit_list.currentItem().text() if self.unit_list.currentItem() else ""
        search_text = self.search.text().strip().lower()
        self.unit_list.clear()
        self._pending_icon_rows = []
        row_to_select = 0
        for name, record in sorted(
            self.units.items(),
            key=lambda item: item[1].display_name(self.locale).lower(),
        ):
            display_name = record.display_name(self.locale)
            if search_text and search_text not in name.lower() and search_text not in display_name.lower():
                continue
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, record.icon)
            if display_name != name:
                item.setToolTip(name)
            self.unit_list.addItem(item)
            self._pending_icon_rows.append(self.unit_list.count() - 1)
            if display_name == selected_name or name == selected_name:
                row_to_select = self.unit_list.count() - 1
        if self.unit_list.count() > 0:
            self.unit_list.setCurrentRow(row_to_select)
        QTimer.singleShot(0, self._load_next_icon_batch)

    def _load_next_icon_batch(self) -> None:
        for _index in range(min(24, len(self._pending_icon_rows))):
            row = self._pending_icon_rows.pop(0)
            item = self.unit_list.item(row)
            if item is None:
                continue
            icon_path = self._absolute_path(str(item.data(Qt.ItemDataRole.UserRole) or ""))
            if icon_path.exists():
                item.setIcon(self.icon_for_path(icon_path))
        if self._pending_icon_rows:
            QTimer.singleShot(1, self._load_next_icon_batch)

    def _absolute_path(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.app_root / candidate


class PlacementGridPanel(QWidget):
    id = "placement_grid"
    name = "Placement Grid"

    def __init__(
        self,
        app_root: Path,
        unit_repository: UnitRepository,
        template_repository: PlacementTemplateRepository,
        log,
        on_templates_changed: Callable[[], None] | None = None,
        translator: Translator | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        super().__init__()
        self.app_root = app_root
        self.unit_repository = unit_repository
        self.template_repository = template_repository
        self.log = log
        self.on_templates_changed = on_templates_changed
        self.translator = translator
        self.locale = locale
        self.units: dict[str, UnitRecord] = {}
        self.cells = build_deployment_grid(radius=36)
        self.placed_units: list[PlacedUnit] = []
        self.current_template_name = "default"
        self.current_template_image = ""
        self.selected_cell: tuple[int, int] | None = None
        self.highlighted_cells: set[tuple[int, int]] = set()
        self.hovered_cell: tuple[int, int] | None = None
        self.hex_items: dict[tuple[int, int], QGraphicsPolygonItem] = {}
        self.placement_preview_item: QGraphicsPixmapItem | None = None
        self.placement_preview_unit_name: str | None = None
        self._unit_pixmap_cache: dict[str, QPixmap] = {}
        self._icon_cache: dict[str, QIcon] = {}

        self.scene = QGraphicsScene(self)
        self.grid_view = HexGridView(self)
        self.grid_view.setScene(self.scene)
        self.template_list = QListWidget()
        self.template_list.setUniformItemSizes(True)
        self.template_preview = QLabel()
        self.template_preview.setMinimumSize(120, 90)
        self.template_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_list = QListWidget()
        self.unit_list.setUniformItemSizes(True)
        self.unit_search = QLineEdit()
        self.unit_search.setPlaceholderText(self.tr("placementGrid.searchUnits"))
        self.unit_preview = QLabel()
        self.unit_preview.setMinimumSize(120, 90)
        self.unit_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quantity_mode = QComboBox()
        self.quantity_mode.addItem("Max", "max")
        self.quantity_mode.addItem("Any", "any")
        self.selected_label = QLabel(self.tr("placementGrid.selectedNone"))

        self._build_layout()
        self.reload_units()
        self.reload_templates()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            make_header(
                self.tr("placementGrid.title"),
                self.tr("placementGrid.subtitle"),
            )
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(self.tr("placementGrid.quantityRule")))
        toolbar.addWidget(self.quantity_mode)

        update_button = QPushButton(self.tr("placementGrid.updateSelected"))
        update_button.clicked.connect(self.update_selected_unit)
        refresh_button = QPushButton(self.tr("placementGrid.refreshUnits"))
        refresh_button.clicked.connect(self.reload_units)
        clear_button = QPushButton(self.tr("placementGrid.clearGrid"))
        clear_button.clicked.connect(self.clear_grid)
        toolbar.addWidget(update_button)
        toolbar.addWidget(clear_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self.selected_label)

        body = QHBoxLayout()
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel(self.tr("placementGrid.placementTemplates")))
        self.template_list.setMinimumHeight(184)
        self.template_list.setMaximumHeight(184)
        left_panel.addWidget(self.template_list)
        template_buttons = QHBoxLayout()
        for text, handler in [
            ("New", self.new_template),
            ("Save", self.save_current_template),
            ("Rename", self.rename_current_template),
            ("Delete", self.delete_current_template),
        ]:
            button = QPushButton(self._template_button_label(text))
            button.clicked.connect(handler)
            template_buttons.addWidget(button)
        left_panel.addLayout(template_buttons)
        image_button = QPushButton(self.tr("placementGrid.chooseIcon"))
        image_button.clicked.connect(self.choose_template_icon)
        left_panel.addWidget(image_button)
        left_panel.addWidget(self.template_preview)
        left_panel.addWidget(QLabel(self.tr("placementGrid.units")))
        self.unit_list.setMinimumWidth(240)
        self.unit_list.setMinimumHeight(280)
        left_panel.addWidget(refresh_button)
        left_panel.addWidget(self.unit_search)
        left_panel.addWidget(self.unit_list, 1)
        left_panel.addWidget(self.unit_preview)
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        body.addWidget(left_widget)
        body.addWidget(self.grid_view, 1)
        layout.addLayout(body, 1)
        self.template_list.currentItemChanged.connect(self._template_selection_changed)
        self.unit_list.currentItemChanged.connect(self._unit_selection_changed)
        self.unit_search.textChanged.connect(self._refresh_unit_list)

    def reload_units(self) -> None:
        self.units = self.unit_repository.load()
        self._unit_pixmap_cache = {}
        self._icon_cache = {}
        self._refresh_unit_list()

    def _refresh_unit_list(self) -> None:
        search_text = self.unit_search.text().strip().lower()
        self.unit_list.clear()
        for name, record in sorted(
            self.units.items(),
            key=lambda item: (
                item[0].strip().upper() != PSEUDO_ANY_UNIT_NAME,
                item[0].lower(),
            ),
        ):
            display_name = record.display_name(self.locale)
            if search_text and search_text not in name.lower() and search_text not in display_name.lower():
                continue
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if display_name != name:
                item.setToolTip(name)
            icon_path = self._absolute_path(record.icon)
            if icon_path.exists():
                item.setIcon(self._icon_for_path(icon_path))
            self.unit_list.addItem(item)

    def reload_templates(self) -> None:
        self.template_list.blockSignals(True)
        self.template_list.clear()
        template_names = self.template_repository.list_templates()
        if not template_names:
            self.template_repository.save(PlacementTemplate(name=self.current_template_name))
            template_names = self.template_repository.list_templates()
        for name in template_names:
            template = self.template_repository.load(name)
            item = QListWidgetItem(name)
            image_path = self._absolute_path(template.image_path)
            if image_path.exists():
                item.setIcon(QIcon(str(image_path)))
            self.template_list.addItem(item)
        self.template_list.blockSignals(False)
        if self.current_template_name not in template_names:
            self.current_template_name = template_names[0]
        for row in range(self.template_list.count()):
            if self.template_list.item(row).text() == self.current_template_name:
                self.template_list.setCurrentRow(row)
                break
        self.load_template(self.current_template_name)

    def load_template(self, template_name: str) -> None:
        template = self.template_repository.load(template_name)
        self.current_template_name = template.name
        self.current_template_image = template.image_path
        self.placed_units = list(template.units)
        self.selected_cell = None
        self.highlighted_cells = set()
        self.hovered_cell = None
        self.clear_placement_preview()
        self._sync_selected_controls()
        self._update_template_preview()
        self.redraw()
        self.grid_view.fit_to_scene()

    def save_current_template(self) -> None:
        self.template_repository.save(
            PlacementTemplate(
                name=self.current_template_name,
                image_path=self.current_template_image,
                units=self.placed_units,
            )
        )
        self.reload_templates()
        self._notify_templates_changed()
        self.log(f"Saved placement template: {self.current_template_name}")

    def new_template(self) -> None:
        name, accepted = QInputDialog.getText(self, "New placement template", "Template name")
        if not accepted or not name.strip():
            return
        self.current_template_name = name.strip()
        self.current_template_image = ""
        self.placed_units = []
        self.selected_cell = None
        self.hovered_cell = None
        self.clear_placement_preview()
        self.template_repository.save(PlacementTemplate(name=self.current_template_name))
        self.reload_templates()
        self._notify_templates_changed()

    def rename_current_template(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Rename placement template",
            "Template name",
            text=self.current_template_name,
        )
        if not accepted or not name.strip():
            return
        renamed = self.template_repository.rename(self.current_template_name, name.strip())
        self.current_template_name = renamed.name
        self.current_template_image = renamed.image_path
        self.placed_units = list(renamed.units)
        self.reload_templates()
        self._notify_templates_changed()

    def delete_current_template(self) -> None:
        if not self.current_template_name:
            return
        if (
            QMessageBox.question(
                self,
                "Delete placement template",
                f"Delete template '{self.current_template_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.template_repository.delete(self.current_template_name)
        template_names = self.template_repository.list_templates()
        if not template_names:
            self.current_template_name = "default"
            self.current_template_image = ""
            self.placed_units = []
            self.template_repository.save(PlacementTemplate(name=self.current_template_name))
        else:
            self.current_template_name = template_names[0]
        self.selected_cell = None
        self.hovered_cell = None
        self.clear_placement_preview()
        self.reload_templates()
        self._notify_templates_changed()
        self.log("Deleted placement template")

    def choose_template_icon(self) -> None:
        dialog = TemplateIconDialog(
            self.units,
            self.app_root,
            self._icon_for_path,
            self,
            locale=self.locale,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_icon_path:
            return
        self.current_template_image = self._relative_path(dialog.selected_icon_path)
        self.save_current_template()
        self._update_template_preview()

    def redraw(self) -> None:
        old_scene = self.scene
        self.scene = QGraphicsScene(self)
        self.grid_view.setScene(self.scene)
        old_scene.deleteLater()
        self.hex_items = {}
        self.placement_preview_item = None
        self.placement_preview_unit_name = None
        self._draw_hexes()
        for unit in self.placed_units:
            self._draw_unit(unit)
        if self.hovered_cell is not None:
            cell = self._cell_at(*self.hovered_cell)
            if cell is not None:
                self._set_placement_preview(cell)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.grid_view.fit_to_scene()

    def place_selected_unit(self, x: float, y: float, keep_unit_selected: bool = False) -> bool:
        current = self.unit_list.currentItem()
        if current is None:
            return False
        unit_name = self._item_unit_name(current)
        cell = cell_at_point(self.cells, x, y, 36)
        if cell is None:
            return False
        unit = PlacedUnit(
            unit_name,
            cell.row,
            cell.col,
            self._current_quantity_value(),
            self._current_quantity_mode(),
        )
        self.placed_units = [
            existing
            for existing in self.placed_units
            if not (existing.row == cell.row and existing.col == cell.col)
        ]
        self.placed_units.append(unit)
        self.selected_cell = (cell.row, cell.col)
        self._save_and_redraw()
        self._select_unit(unit)
        if keep_unit_selected:
            self._set_placement_preview(cell)
        else:
            self.unit_list.setCurrentRow(-1)
            self.clear_placement_preview()
        return True

    def can_place_selected_unit(self, x: float, y: float) -> bool:
        return self.unit_list.currentItem() is not None and cell_at_point(self.cells, x, y, 36) is not None

    def remove_placed_unit(self, row: int, col: int) -> bool:
        unit = self._unit_at(row, col)
        if unit is None:
            return False
        self.placed_units = [
            placed
            for placed in self.placed_units
            if not (placed.row == row and placed.col == col)
        ]
        if self.selected_cell == (row, col):
            self.selected_cell = None
            self.selected_label.setText(self.tr("placementGrid.selectedNone"))
        self.highlighted_cells.discard((row, col))
        self._save_and_redraw()
        self._sync_selected_controls()
        return True

    def update_hovered_cell(self, x: float, y: float) -> None:
        cell = cell_at_point(self.cells, x, y, 36)
        if cell is None:
            self.clear_hovered_cell()
            return
        self._set_hovered_cell((cell.row, cell.col))
        self._set_placement_preview(cell)

    def clear_hovered_cell(self) -> None:
        previous_hover = self.hovered_cell
        self.hovered_cell = None
        if previous_hover is not None:
            item = self.hex_items.get(previous_hover)
            cell = self._cell_at(*previous_hover)
            if item is not None and cell is not None:
                item.setBrush(QBrush(self._hex_brush_color(cell)))
        self.clear_placement_preview()

    def _set_hovered_cell(self, hovered_cell: tuple[int, int]) -> None:
        if self.hovered_cell == hovered_cell:
            return
        previous_hover = self.hovered_cell
        self.hovered_cell = hovered_cell
        if previous_hover is not None:
            previous_item = self.hex_items.get(previous_hover)
            previous_cell = self._cell_at(*previous_hover)
            if previous_item is not None and previous_cell is not None:
                previous_item.setBrush(QBrush(self._hex_brush_color(previous_cell)))
        current_item = self.hex_items.get(hovered_cell)
        current_cell = self._cell_at(*hovered_cell)
        if current_item is not None and current_cell is not None:
            current_item.setBrush(QBrush(self._hex_brush_color(current_cell)))

    def clear_placement_preview(self) -> None:
        self.placement_preview_unit_name = None
        if self.placement_preview_item is not None:
            self.scene.removeItem(self.placement_preview_item)
            self.placement_preview_item = None

    def update_selected_unit(self) -> None:
        if self.selected_cell is None:
            return
        row, col = self.selected_cell
        self.placed_units = update_unit_at(
            self.placed_units,
            row,
            col,
            self._current_quantity_value(),
            self._current_quantity_mode(),
        )
        self._save_and_redraw()
        self._sync_selected_controls()

    def clear_grid(self) -> None:
        self.placed_units = []
        self.selected_cell = None
        self.highlighted_cells = set()
        self.selected_label.setText(self.tr("placementGrid.selectedNone"))
        self._save_and_redraw()

    def _template_selection_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        if current.text() != self.current_template_name:
            self.load_template(current.text())

    def _unit_selection_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self.unit_preview.clear()
            self.clear_placement_preview()
            return
        record = self.units.get(self._item_unit_name(current))
        if record is None:
            self.unit_preview.clear()
            self.clear_placement_preview()
            return
        pixmap = QPixmap(str(self._absolute_path(record.icon)))
        if not pixmap.isNull():
            self.unit_preview.setPixmap(
                pixmap.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        if self.hovered_cell is not None:
            cell = self._cell_at(*self.hovered_cell)
            if cell is not None:
                self._set_placement_preview(cell)

    def _draw_hexes(self) -> None:
        for index, cell in enumerate(self.cells, start=1):
            is_highlighted = (cell.row, cell.col) in self.highlighted_cells
            is_selected = self.selected_cell == (cell.row, cell.col)
            polygon = QPolygonF([QPointF(*point) for point in self._hex_points(cell, 36)])
            item = self.scene.addPolygon(
                polygon,
                QPen(self._hex_pen_color(is_highlighted, is_selected), 4 if is_highlighted or is_selected else 2),
                QBrush(self._hex_brush_color(cell)),
            )
            item.setToolTip(self.tr("placementGrid.cell", index=index))
            item.setZValue(0)
            self.hex_items[(cell.row, cell.col)] = item
            label = self.scene.addText(str(index))
            label.setDefaultTextColor(QColor("#eef3f6"))
            label.setToolTip(self.tr("placementGrid.cell", index=index))
            label.setPos(cell.center_x - label.boundingRect().width() / 2, cell.center_y - 35)
            label.setZValue(2)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _draw_unit(self, placed: PlacedUnit) -> None:
        record = self.units.get(placed.unit_name)
        cell = self._cell_at(placed.row, placed.col)
        if record is None or cell is None:
            return

        item = DraggableUnitItem(
            placed=placed,
            cells=self.cells,
            on_selected=self._select_unit,
            on_moved=self._unit_moved,
            pixmap=self._unit_pixmap(record),
        )
        item.setPos(cell.center_x, cell.center_y)
        item.setZValue(5)
        self.scene.addItem(item)

    def _set_placement_preview(self, cell: GridCell) -> None:
        current = self.unit_list.currentItem()
        if current is None:
            self.clear_placement_preview()
            return
        unit_name = self._item_unit_name(current)
        record = self.units.get(unit_name)
        if record is None:
            self.clear_placement_preview()
            return
        if (
            self.placement_preview_item is None
            or self.placement_preview_unit_name != unit_name
        ):
            if self.placement_preview_item is not None:
                self.scene.removeItem(self.placement_preview_item)
            pixmap = self._unit_pixmap(record)
            self.placement_preview_item = QGraphicsPixmapItem(pixmap)
            self.placement_preview_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
            self.placement_preview_item.setOpacity(0.58)
            self.placement_preview_item.setZValue(4)
            self.placement_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(self.placement_preview_item)
            self.placement_preview_unit_name = unit_name
        self.placement_preview_item.setPos(cell.center_x, cell.center_y)

    def _unit_moved(self, placed: PlacedUnit, cell: GridCell) -> None:
        self.placed_units, swapped = move_or_swap_unit(
            self.placed_units,
            placed.row,
            placed.col,
            cell.row,
            cell.col,
        )
        self.selected_cell = (cell.row, cell.col)
        if swapped:
            self.highlighted_cells = {(placed.row, placed.col), (cell.row, cell.col)}
            self.log(
                f"Swapped {placed.unit_name} with unit at row {cell.row + 1}, col {cell.col + 1}"
            )
            QTimer.singleShot(1200, self._clear_swap_highlight)
        else:
            self.highlighted_cells = set()
        self._save_and_redraw()
        self._sync_selected_controls()

    def _select_unit(self, placed: PlacedUnit) -> None:
        self.selected_cell = (placed.row, placed.col)
        self._set_quantity_mode(placed.normalized_mode())
        self.selected_label.setText(
            self.tr(
                "placementGrid.selectedUnit",
                unit=self._display_unit_name(placed.unit_name),
                row=placed.row + 1,
                col=placed.col + 1,
            )
        )

    def _sync_selected_controls(self) -> None:
        if self.selected_cell is None:
            self.selected_label.setText(self.tr("placementGrid.selectedNone"))
            return
        unit = self._unit_at(*self.selected_cell)
        if unit is None:
            self.selected_cell = None
            self.selected_label.setText(self.tr("placementGrid.selectedNone"))
            return
        self._set_quantity_mode(unit.normalized_mode())
        self.selected_label.setText(
            self.tr(
                "placementGrid.selectedUnit",
                unit=self._display_unit_name(unit.unit_name),
                row=unit.row + 1,
                col=unit.col + 1,
            )
        )

    def _clear_swap_highlight(self) -> None:
        self.highlighted_cells = set()
        self.redraw()

    def _save_and_redraw(self) -> None:
        self.template_repository.save(
            PlacementTemplate(
                name=self.current_template_name,
                image_path=self.current_template_image,
                units=self.placed_units,
            )
        )
        self.redraw()
        self.grid_view.fit_to_scene()
        self._notify_templates_changed()

    def _notify_templates_changed(self) -> None:
        if self.on_templates_changed is not None:
            self.on_templates_changed()

    def _unit_at(self, row: int, col: int) -> PlacedUnit | None:
        return next(
            (unit for unit in self.placed_units if unit.row == row and unit.col == col),
            None,
        )

    def _cell_at(self, row: int, col: int) -> GridCell | None:
        return next((cell for cell in self.cells if cell.row == row and cell.col == col), None)

    def _unit_pixmap(self, record: UnitRecord) -> QPixmap:
        path = self._absolute_path(record.icon)
        cache_key = str(path)
        cached = self._unit_pixmap_cache.get(cache_key)
        if cached is not None:
            return cached
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap(64, 64)
        if pixmap.isNull():
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#202633"))
        scaled = pixmap.scaled(
            58,
            58,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._unit_pixmap_cache[cache_key] = scaled
        return scaled

    def _icon_for_path(self, path: Path) -> QIcon:
        cache_key = str(path)
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached
        icon = QIcon(cache_key)
        self._icon_cache[cache_key] = icon
        return icon

    def _absolute_path(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.app_root / candidate

    def _relative_path(self, path: str) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            return path.replace("\\", "/")
        try:
            return str(candidate.relative_to(self.app_root)).replace("\\", "/")
        except ValueError:
            return str(candidate)

    def _current_quantity_mode(self) -> str:
        return str(self.quantity_mode.currentData() or "max")

    def _current_quantity_value(self) -> int:
        return 1

    def _set_quantity_mode(self, mode: str) -> None:
        index = self.quantity_mode.findData(mode)
        self.quantity_mode.setCurrentIndex(index if index >= 0 else 0)

    def _item_unit_name(self, item: QListWidgetItem) -> str:
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text())

    def _display_unit_name(self, unit_name: str) -> str:
        record = self.units.get(unit_name)
        return record.display_name(self.locale) if record is not None else unit_name

    def _template_button_label(self, text: str) -> str:
        keys = {
            "New": "placementGrid.new",
            "Save": "placementGrid.save",
            "Rename": "placementGrid.rename",
            "Delete": "placementGrid.delete",
        }
        return self.tr(keys[text])

    def tr(self, key: str, **values: object) -> str:
        if self.translator is not None:
            return self.translator.t(key, **values)
        fallback = {
            "placementGrid.title": "Placement Grid",
            "placementGrid.subtitle": "Select a unit, click a hex to place it, then drag icons to move or swap them.",
            "placementGrid.quantityRule": "Quantity rule",
            "placementGrid.updateSelected": "Update Selected",
            "placementGrid.refreshUnits": "Refresh Units",
            "placementGrid.clearGrid": "Clear Grid",
            "placementGrid.selectedNone": "Selected: none",
            "placementGrid.selectedUnit": "Selected: {unit} at row {row}, col {col}",
            "placementGrid.placementTemplates": "Placement templates",
            "placementGrid.new": "New",
            "placementGrid.save": "Save",
            "placementGrid.rename": "Rename",
            "placementGrid.delete": "Delete",
            "placementGrid.chooseIcon": "Choose Icon",
            "placementGrid.units": "Units",
            "placementGrid.searchUnits": "Search units by name",
            "placementGrid.cell": "Cell {index}",
        }.get(key, key)
        return fallback.format(**values) if values else fallback

    def _update_template_preview(self) -> None:
        image_path = self._absolute_path(self.current_template_image)
        if not image_path.exists():
            self.template_preview.setPixmap(QPixmap())
            self.template_preview.hide()
            return
        self.template_preview.show()
        pixmap = QPixmap(str(image_path))
        self.template_preview.setPixmap(
            pixmap.scaled(
                120,
                90,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _hex_brush_color(self, cell: GridCell) -> QColor:
        location = (cell.row, cell.col)
        if location in self.highlighted_cells:
            return QColor("#766733")
        if self.hovered_cell == location:
            return QColor("#3f5625")
        return QColor("#4f6d2f")

    @staticmethod
    def _hex_pen_color(is_highlighted: bool, is_selected: bool) -> QColor:
        if is_highlighted:
            return QColor("#f2c14e")
        if is_selected:
            return QColor("#59a7ff")
        return QColor("#2f3a24")

    @staticmethod
    def _hex_points(cell: GridCell, radius: float) -> list[tuple[float, float]]:
        return [
            (
                cell.center_x + radius * cos(pi / 6 + index * pi / 3),
                cell.center_y + radius * sin(pi / 6 + index * pi / 3),
            )
            for index in range(6)
        ]
