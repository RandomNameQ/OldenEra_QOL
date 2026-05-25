from oldenera_qol.vision.capture import WindowBounds
from oldenera_qol.vision.models import Rect, UnitDetection
from oldenera_qol.vision.template_matching import intersection_over_union, non_max_suppression


def test_window_bounds_converts_relative_and_screen_coordinates() -> None:
    bounds = WindowBounds(left=100, top=200, width=800, height=600)

    assert bounds.relative_to_screen((10, 20)) == (110, 220)
    assert bounds.screen_to_relative((150, 275)) == (50, 75)


def test_non_max_suppression_keeps_highest_confidence_overlap() -> None:
    detections = [
        UnitDetection("archer", Rect(10, 10, 30, 30), 0.70),
        UnitDetection("archer", Rect(12, 12, 30, 30), 0.95),
        UnitDetection("archer", Rect(100, 100, 30, 30), 0.80),
    ]

    kept = non_max_suppression(detections, overlap_threshold=0.30)

    assert len(kept) == 2
    assert kept[0].confidence == 0.95
    assert kept[1].confidence == 0.80


def test_intersection_over_union_handles_disjoint_rects() -> None:
    assert intersection_over_union(Rect(0, 0, 10, 10), Rect(20, 20, 10, 10)) == 0.0


def test_screenshot_canvas_overlay_updates_keep_existing_pixmap() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    from oldenera_qol.app.widgets import ScreenshotCanvas

    app = QApplication.instance() or QApplication([])
    canvas = ScreenshotCanvas()
    pixmap = QPixmap(20, 20)
    canvas.set_pixmap(pixmap)
    original_item = canvas.pixmap_item

    canvas.set_overlays(
        rects=[(1, 1, 10, 10)],
        labels=[(2, 2, "1: unknown (0.12)", "#ff6b6b")],
    )
    app.processEvents()

    assert canvas.pixmap_item is original_item
    assert canvas.overlay_labels == [(2, 2, "1: unknown (0.12)", "#ff6b6b")]
    assert len(canvas.overlay_items) == 3
