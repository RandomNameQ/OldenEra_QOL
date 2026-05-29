from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QBrush, QCursor, QKeySequence, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


OverlayAction = tuple[str, Callable[[], None], str, str]

_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_VK_ESCAPE = 0x1B
_WH_KEYBOARD_LL = 13


class _KbdLlHookStruct(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _EscapeKeyBlocker:
    def __init__(self, on_escape: Callable[[], None]) -> None:
        self._on_escape = on_escape
        self._hook = None
        self._callback = None
        self._user32 = None

    def start(self) -> bool:
        if self._hook is not None:
            return True
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except AttributeError:
            return False
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._user32 = user32
        self._callback = callback_type(self._handle_event)
        module_handle = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL,
            self._callback,
            module_handle,
            0,
        )
        return bool(self._hook)

    def stop(self) -> None:
        if self._hook is None or self._user32 is None:
            self._hook = None
            self._callback = None
            return
        self._user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._callback = None

    def _handle_event(self, code: int, w_param, l_param) -> int:
        if code >= 0 and int(w_param) in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            event = ctypes.cast(l_param, ctypes.POINTER(_KbdLlHookStruct)).contents
            if int(event.vkCode) == _VK_ESCAPE:
                QTimer.singleShot(0, self._on_escape)
                return 1
        if self._user32 is None:
            return 0
        return self._user32.CallNextHookEx(self._hook, code, w_param, l_param)


class FloatingActionOverlay(QWidget):
    def __init__(
        self,
        actions: list[OverlayAction],
        anchor_provider: Callable[[], QRect],
        icon_text: str = "OE",
    ) -> None:
        super().__init__()
        self._anchor_provider = anchor_provider
        self._expanded = False
        self.setObjectName("FloatingActionOverlay")
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.handle = QFrame()
        self.handle.setObjectName("OverlayHandle")
        self.handle.setFixedSize(36, 58)
        handle_layout = QVBoxLayout(self.handle)
        handle_layout.setContentsMargins(0, 0, 0, 0)
        handle_label = QLabel(icon_text)
        handle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle_label.setObjectName("OverlayHandleLabel")
        handle_layout.addWidget(handle_label)
        layout.addWidget(self.handle)

        self.panel = QFrame()
        self.panel.setObjectName("OverlayPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(7)
        title = QLabel("OldenEra QOL")
        title.setObjectName("OverlayTitle")
        panel_layout.addWidget(title)
        for text, callback, tooltip, role in actions:
            button = QPushButton(text)
            button.setToolTip(tooltip)
            button.setMinimumHeight(32)
            if role:
                button.setObjectName(role)
            button.clicked.connect(lambda _checked=False, action=callback: self._trigger_action(action))
            panel_layout.addWidget(button)
        layout.addWidget(self.panel)
        self.panel.setVisible(False)

        self.setStyleSheet(
            """
            QWidget#FloatingActionOverlay {
                background: transparent;
            }
            QFrame#OverlayHandle {
                background: #2f7cf6;
                border: 1px solid #75a7ff;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QLabel#OverlayHandleLabel {
                background: transparent;
                color: #ffffff;
                font-size: 12px;
                font-weight: 800;
            }
            QFrame#OverlayPanel {
                background: rgba(17, 19, 24, 238);
                border: 1px solid #303849;
                border-radius: 8px;
            }
            QLabel#OverlayTitle {
                background: transparent;
                color: #edf0f5;
                font-size: 13px;
                font-weight: 700;
                padding: 0 2px 2px 2px;
            }
            QFrame#OverlayPanel QPushButton {
                text-align: left;
                padding: 6px 9px;
            }
            QFrame#OverlayPanel QPushButton#SuccessButton {
                background: #1f8f4d;
                border-color: #26d65b;
                font-weight: 600;
            }
            QFrame#OverlayPanel QPushButton#SuccessButton:hover {
                background: #26a85b;
            }
            """
        )

        self._reposition_timer = QTimer(self)
        self._reposition_timer.setInterval(450)
        self._reposition_timer.timeout.connect(self.reposition)

    def start(self) -> None:
        self._reposition_timer.start()
        self.reposition()

    def enterEvent(self, event) -> None:
        self._set_expanded(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        QTimer.singleShot(120, self._collapse_if_mouse_left)
        super().leaveEvent(event)

    def reposition(self) -> None:
        anchor = self._anchor_provider()
        if anchor.isNull():
            self._set_expanded(False)
            self.hide()
            return
        self.adjustSize()
        x = anchor.left()
        y = anchor.top() + max(0, (anchor.height() - self.height()) // 2)
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        if screen is not None:
            screen_rect = screen.virtualGeometry()
            x = min(max(x, screen_rect.left()), screen_rect.right() - self.width() + 1)
            y = min(max(y, screen_rect.top()), screen_rect.bottom() - self.height() + 1)
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()

    def _set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.panel.setVisible(expanded)
        self.adjustSize()
        self.reposition()

    def _trigger_action(self, action: Callable[[], None]) -> None:
        self._set_expanded(False)
        action()

    def _collapse_if_mouse_left(self) -> None:
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self._set_expanded(False)


class LogPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        from PySide6.QtWidgets import QPlainTextEdit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

    def append(self, message: str) -> None:
        self.output.appendPlainText(message)


class HotkeyCaptureEdit(QLineEdit):
    captured = Signal(str)
    _CAPTURE_TEXT = "Press a key or shortcut..."
    _MODIFIER_KEYS = {
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    }

    def __init__(self, value: str = "") -> None:
        super().__init__(value)
        self._previous_value = value
        self._capturing = False
        self.setPlaceholderText("Click and press a key or shortcut")

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._start_capture()

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._restore_previous()
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._start_capture()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._restore_previous()
            self.clearFocus()
            event.accept()
            return
        if event.key() in self._MODIFIER_KEYS:
            event.accept()
            return
        sequence = QKeySequence(event.keyCombination()).toString().lower()
        if sequence:
            sequence = sequence.replace(", ", "+").replace("meta", "win")
            self.setText(sequence)
            self._previous_value = sequence
            self._capturing = False
            self.captured.emit(sequence)
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def _start_capture(self) -> None:
        if self._capturing:
            return
        self._previous_value = self.text()
        self._capturing = True
        self.setText(self._CAPTURE_TEXT)
        self.selectAll()

    def _restore_previous(self) -> None:
        self._capturing = False
        self.setText(self._previous_value)


class ScreenshotCanvas(QGraphicsView):
    clicked = Signal(int, int)
    rectangle_selected = Signal(int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.overlay_items: list[QGraphicsItem] = []
        self.overlay_rects: list[tuple] = []
        self.overlay_points: list[tuple[int, int]] = []
        self.overlay_lines: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self.overlay_labels: list[tuple[int, int, str, str]] = []
        self._press_position: tuple[int, int] | None = None
        self._zoom_level = 1.0
        self._initial_zoom = 1.0
        self.setMinimumHeight(460)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def set_image_path(self, image_path: str) -> None:
        pixmap = QPixmap(image_path)
        self.set_pixmap(pixmap)

    def set_pixmap(self, pixmap: QPixmap, initial_zoom: float | None = None) -> None:
        self.scene.clear()
        self.overlay_items = []
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(pixmap.rect())
        self._draw_overlays()
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = 1.0
        self.zoom(initial_zoom if initial_zoom is not None else self._initial_zoom)

    def zoom(self, factor: float) -> None:
        next_zoom = max(0.35, min(8.0, self._zoom_level * factor))
        factor_to_apply = next_zoom / self._zoom_level
        self._zoom_level = next_zoom
        self.scale(factor_to_apply, factor_to_apply)

    def wheelEvent(self, event) -> None:
        if self.pixmap_item is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        self.zoom(1.18 if delta > 0 else 1 / 1.18)
        event.accept()

    def set_overlays(
        self,
        rects: list[tuple] | None = None,
        points: list[tuple[int, int]] | None = None,
        lines: list[tuple[tuple[int, int], tuple[int, int]]] | None = None,
        labels: list[tuple[int, int, str, str]] | None = None,
    ) -> None:
        self.overlay_rects = list(rects or [])
        self.overlay_points = list(points or [])
        self.overlay_lines = list(lines or [])
        self.overlay_labels = list(labels or [])
        if self.pixmap_item is not None:
            self._redraw_overlays()

    def _draw_overlays(self) -> None:
        point_pen = QPen(QColor(255, 215, 72), 3)
        line_pen = QPen(QColor(91, 173, 255), 2)
        for overlay_rect in self.overlay_rects:
            if len(overlay_rect) == 5:
                x, y, width, height, color = overlay_rect
            else:
                x, y, width, height = overlay_rect
                color = "#26d65b"
            rect_pen = QPen(QColor(color), 3)
            self.overlay_items.append(self.scene.addRect(x, y, width, height, rect_pen))
        for x, y in self.overlay_points:
            self.overlay_items.append(self.scene.addEllipse(x - 5, y - 5, 10, 10, point_pen))
        for source, target in self.overlay_lines:
            self.overlay_items.append(self.scene.addLine(source[0], source[1], target[0], target[1], line_pen))
        for x, y, label, color in self.overlay_labels:
            text = self.scene.addText(label)
            text.setDefaultTextColor(QColor(color))
            text.setPos(x, y)
            rect = text.boundingRect().translated(text.pos())
            background = self.scene.addRect(
                rect.adjusted(-4, -2, 4, 2),
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor(17, 19, 24, 220)),
            )
            background.setZValue(8)
            text.setZValue(9)
            self.overlay_items.extend([background, text])

    def _redraw_overlays(self) -> None:
        for item in self.overlay_items:
            self.scene.removeItem(item)
        self.overlay_items = []
        self._draw_overlays()

    def clear_overlays(self) -> None:
        self.set_overlays()

    def mousePressEvent(self, event) -> None:
        if self.pixmap_item is not None:
            position = self.mapToScene(event.position().toPoint())
            self._press_position = (int(position.x()), int(position.y()))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.pixmap_item is not None and self._press_position is not None:
            position = self.mapToScene(event.position().toPoint())
            end = (int(position.x()), int(position.y()))
            start = self._press_position
            self._press_position = None
            if abs(end[0] - start[0]) > 3 and abs(end[1] - start[1]) > 3:
                left = min(start[0], end[0])
                top = min(start[1], end[1])
                self.rectangle_selected.emit(left, top, abs(end[0] - start[0]), abs(end[1] - start[1]))
            else:
                self.clicked.emit(*end)
        super().mouseReleaseEvent(event)


class SelectionOverlay(QWidget):
    rectangle_selected = Signal(int, int, int, int)
    point_selected = Signal(int, int)
    finished = Signal()

    def __init__(
        self,
        mode: str,
        instruction: str,
        existing_points: list[tuple[int, int]] | None = None,
        existing_rect: tuple[int, int, int, int] | None = None,
        reference_labels: list[str] | None = None,
        reference_cells: list[tuple[int, int, str]] | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.instruction = instruction
        self.points = list(existing_points or [])
        self.saved_rect = existing_rect
        self._reference_labels = list(reference_labels or [])
        self._reference_cells = list(reference_cells or [])
        self.start: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.pending_point: tuple[int, int] | None = None
        self._escape_blocker = _EscapeKeyBlocker(self._cancel_selection)
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def reference_labels(self) -> list[str]:
        return list(self._reference_labels)

    def reference_cells(self) -> list[tuple[int, int, str]]:
        return list(self._reference_cells)

    def mousePressEvent(self, event) -> None:
        point = (int(event.position().x()), int(event.position().y()))
        if event.button() == Qt.MouseButton.RightButton:
            self.finished.emit()
            self.close()
            return
        if self.mode == "rectangle":
            self.start = point
            self.current = point
            self.update()
        elif self.mode == "points" and event.button() == Qt.MouseButton.LeftButton:
            self.pending_point = point
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.mode == "rectangle" and self.start is not None:
            self.current = (int(event.position().x()), int(event.position().y()))
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.mode == "rectangle" and self.start is not None:
            end = (int(event.position().x()), int(event.position().y()))
            left = min(self.start[0], end[0])
            top = min(self.start[1], end[1])
            width = abs(end[0] - self.start[0])
            height = abs(end[1] - self.start[1])
            if width > 3 and height > 3:
                self.rectangle_selected.emit(left, top, width, height)
                self.close()
            self.start = None
            self.current = None
            self.update()
        elif (
            self.mode == "points"
            and event.button() == Qt.MouseButton.LeftButton
            and self.pending_point is not None
        ):
            point = (int(event.position().x()), int(event.position().y()))
            self.pending_point = None
            self.points.append(point)
            self.point_selected.emit(*point)
            self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cancel_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        self._escape_blocker.start()
        super().showEvent(event)

    def closeEvent(self, event) -> None:
        self._escape_blocker.stop()
        super().closeEvent(event)

    def _cancel_selection(self) -> None:
        self.finished.emit()
        self.close()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 70))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(38, 214, 91), 3))
        painter.drawRect(self.rect().adjusted(2, 2, -3, -3))
        painter.fillRect(QRect(16, 16, min(620, self.width() - 32), 54), QColor(17, 19, 24, 220))
        painter.setPen(QPen(QColor(237, 240, 245), 1))
        painter.drawText(28, 48, self.instruction)

        if self.saved_rect is not None:
            painter.setPen(QPen(QColor(38, 214, 91), 3))
            painter.drawRect(QRect(*self.saved_rect))
        if self.start is not None and self.current is not None:
            left = min(self.start[0], self.current[0])
            top = min(self.start[1], self.current[1])
            width = abs(self.current[0] - self.start[0])
            height = abs(self.current[1] - self.start[1])
            painter.setPen(QPen(QColor(255, 215, 72), 3))
            painter.drawRect(QRect(left, top, width, height))
        for index, point in enumerate(self.points, start=1):
            painter.setPen(QPen(QColor(255, 215, 72), 3))
            painter.drawEllipse(point[0] - 7, point[1] - 7, 14, 14)
            painter.drawText(point[0] + 10, point[1] - 10, str(index))
        if self._reference_cells or self._reference_labels:
            self._draw_reference_grid(painter)

    def _draw_reference_grid(self, painter: QPainter) -> None:
        panel_width = 210
        left = max(16, self.width() - panel_width - 18)
        top = 88
        painter.fillRect(
            QRect(left, top, panel_width, min(570, self.height() - top - 18)),
            QColor(17, 19, 24, 220),
        )
        painter.setPen(QPen(QColor(237, 240, 245), 1))
        painter.drawText(left + 14, top + 28, "Cell order")
        radius = 16
        width = 28
        vertical_step = 24
        grid_left = left + 30
        grid_top = top + 52
        reference_cells = self._reference_cells or [
            (index // 2, index % 2, label)
            for index, label in enumerate(self._reference_labels)
        ]
        for row, col, label in reference_cells:
            center_x = grid_left + col * 52 + (14 if row % 2 else 0)
            center_y = grid_top + row * vertical_step
            points = [
                QPointF(
                    center_x + radius * 0.86 * _cos_60(point_index),
                    center_y + radius * _sin_60(point_index),
                )
                for point_index in range(6)
            ]
            painter.setPen(QPen(QColor(89, 167, 255), 1))
            painter.drawPolygon(QPolygonF(points))
            painter.drawText(
                QRect(int(center_x - width / 2), int(center_y - 8), width, 16),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )


def _cos_60(index: int) -> float:
    values = [0.866, 0.0, -0.866, -0.866, 0.0, 0.866]
    return values[index]


def _sin_60(index: int) -> float:
    values = [0.5, 1.0, 0.5, -0.5, -1.0, -0.5]
    return values[index]


def make_header(title: str, subtitle: str = "") -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 12)
    title_label = QLabel(title)
    title_label.setObjectName("Title")
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("Subtitle")
        layout.addWidget(subtitle_label)
    return container


def labelled_row(label: str, widget: QWidget, button: QPushButton | None = None) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(label), 0)
    layout.addWidget(widget, 1)
    if button is not None:
        layout.addWidget(button)
    return container


def nav_button(text: str, callback: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.setMinimumHeight(40)
    button.clicked.connect(callback)
    return button
