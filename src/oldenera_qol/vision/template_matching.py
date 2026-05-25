from __future__ import annotations

from pathlib import Path
from typing import Iterable

from oldenera_qol.vision.models import Rect, UnitDetection


def intersection_over_union(left: Rect, right: Rect) -> float:
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = left.area + right.area - intersection
    return 0.0 if union == 0 else intersection / union


def non_max_suppression(
    detections: Iterable[UnitDetection],
    overlap_threshold: float = 0.35,
) -> list[UnitDetection]:
    ordered = sorted(detections, key=lambda item: item.confidence, reverse=True)
    kept: list[UnitDetection] = []
    for detection in ordered:
        if all(
            intersection_over_union(detection.rect, existing.rect) <= overlap_threshold
            for existing in kept
        ):
            kept.append(detection)
    return sorted(kept, key=lambda item: (item.rect.y, item.rect.x))


def match_template(image, template_path: Path, template_id: str, threshold: float) -> list[UnitDetection]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in real environment
        raise RuntimeError("OpenCV and NumPy are required for template matching") from exc

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"Template image not found: {template_path}")

    source = np.array(image)
    if source.ndim == 3 and source.shape[2] == 4:
        source = cv2.cvtColor(source, cv2.COLOR_RGBA2BGR)
    elif source.ndim == 3:
        source = cv2.cvtColor(source, cv2.COLOR_RGB2BGR)

    result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    height, width = template.shape[:2]
    detections = [
        UnitDetection(
            template_id=template_id,
            rect=Rect(x=int(x), y=int(y), width=int(width), height=int(height)),
            confidence=float(result[y, x]),
        )
        for y, x in zip(*locations)
    ]
    return non_max_suppression(detections)

