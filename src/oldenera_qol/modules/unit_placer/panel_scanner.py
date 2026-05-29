from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from oldenera_qol.units.models import PSEUDO_ANY_UNIT_NAME, UnitRecord, is_pseudo_any_unit_name
from oldenera_qol.vision.models import Rect
from oldenera_qol.vision.ocr import OcrResult, QuantityOcr, is_tesseract_unavailable_error


@dataclass(frozen=True, slots=True)
class PanelCard:
    index: int
    rect: Rect
    image: Image.Image


@dataclass(frozen=True, slots=True)
class PanelUnitDetection:
    unit_name: str
    quantity: int | None
    confidence: float
    panel_index: int
    quantity_confidence: float = 0.0
    quantity_text: str = ""
    card_rect: Rect | None = None
    match_candidates: tuple[tuple[str, float], ...] = ()


def split_panel_cards(image: Image.Image, expected_count: int = 0) -> list[PanelCard]:
    if expected_count > 0:
        return _uniform_cards(image, expected_count)

    columns = _active_columns(image)
    ranges = _column_ranges(columns)
    if _should_use_uniform_fallback(image, ranges):
        return _uniform_cards(image, _estimated_uniform_card_count(image))
    return [_card(index, image, Rect(start, 0, end - start + 1, image.height)) for index, (start, end) in enumerate(ranges)]


class PanelUnitScanner:
    def __init__(
        self,
        units: dict[str, UnitRecord],
        app_root: Path,
        ocr: QuantityOcr,
        match_threshold: float = 0.5,
        use_any_for_unmatched: bool = False,
    ) -> None:
        self.units = units
        self.app_root = app_root
        self.ocr = ocr
        self.match_threshold = match_threshold
        self.use_any_for_unmatched = use_any_for_unmatched
        self._icon_cache: list[tuple[str, Any, Any | None]] | None = None
        self._resized_icon_cache: dict[tuple[str, int, int], list[tuple[Any, Any | None]]] = {}
        self._last_scan_signature: tuple[tuple[int, int], str, int, bytes] | None = None
        self._last_scan_detections: list[PanelUnitDetection] | None = None

    def scan(
        self,
        screenshot: Image.Image,
        panel_rect: Rect,
        expected_count: int = 0,
    ) -> list[PanelUnitDetection]:
        panel_image = screenshot.crop(
            (
                panel_rect.x,
                panel_rect.y,
                panel_rect.x + panel_rect.width,
                panel_rect.y + panel_rect.height,
            )
        )
        return self.scan_panel_image(panel_image, expected_count)

    def scan_panel_image(
        self,
        panel_image: Image.Image,
        expected_count: int = 0,
    ) -> list[PanelUnitDetection]:
        signature = _image_signature(panel_image, expected_count)
        if signature == self._last_scan_signature and self._last_scan_detections is not None:
            return list(self._last_scan_detections)

        detections: list[PanelUnitDetection] = []
        for card in split_panel_cards(panel_image, expected_count):
            if self.use_any_for_unmatched and not self.units:
                match_result = (PSEUDO_ANY_UNIT_NAME, 0.0, ())
            else:
                match_result = self._match_unit(_unit_match_crop(card.image))
            if len(match_result) == 2:
                unit_name, unit_confidence = match_result
                match_candidates = ()
            else:
                unit_name, unit_confidence, match_candidates = match_result
            if unit_name == "unknown" and self.use_any_for_unmatched:
                unit_name = PSEUDO_ANY_UNIT_NAME
            quantity_crop = _quantity_crop(card.image)
            ocr_result = self._read_quantity(quantity_crop)
            detections.append(
                PanelUnitDetection(
                    unit_name=unit_name,
                    quantity=ocr_result.value,
                    confidence=unit_confidence,
                    panel_index=card.index,
                    quantity_confidence=ocr_result.confidence,
                    quantity_text=ocr_result.text,
                    card_rect=card.rect,
                    match_candidates=tuple(match_candidates),
                )
            )
        self._last_scan_signature = signature
        self._last_scan_detections = list(detections)
        return detections

    def _match_unit(self, image: Image.Image) -> tuple[str, float, tuple[tuple[str, float], ...]]:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:  # pragma: no cover - exercised in real environment
            raise RuntimeError("OpenCV and NumPy are required for panel unit matching") from exc

        source = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        best_name = "unknown"
        best_score = 0.0
        candidate_scores: dict[str, float] = {}
        for name, icon_template, icon_mask in self._unit_icon_templates():
            for icon, mask in self._resized_icon_variants(name, icon_template, icon_mask, source):
                if mask is not None:
                    if _template_coverage(mask, source) < 0.18:
                        continue
                    result = cv2.matchTemplate(source, icon, cv2.TM_SQDIFF_NORMED, mask=mask)
                    result = np.nan_to_num(result, nan=1.0, posinf=1.0, neginf=1.0)
                else:
                    result = cv2.matchTemplate(source, icon, cv2.TM_CCOEFF_NORMED)
                    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
                min_score, max_score, min_location, max_location = cv2.minMaxLoc(result)
                if mask is not None:
                    score = 1.0 - float(min_score)
                    location = min_location
                else:
                    score = float(max_score)
                    location = max_location
                score = _color_adjusted_match_score(source, icon, mask, location, score)
                candidate_scores[name] = max(candidate_scores.get(name, 0.0), score)
                if score > best_score:
                    best_name = name
                    best_score = score
        candidates = tuple(
            sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:5]
        )
        if best_score < self.match_threshold:
            return ("unknown", best_score, candidates)
        return (best_name, best_score, candidates)

    def _read_quantity(self, image: Image.Image) -> OcrResult:
        fallback = _read_quantity_by_cv(image)
        if fallback.value is not None:
            return fallback
        try:
            return self.ocr.read_quantity(image)
        except Exception as exc:
            if is_tesseract_unavailable_error(exc):
                return OcrResult(value=None, text=str(exc), confidence=0.0)
            raise

    def _unit_icon_templates(self) -> list[tuple[str, Any, Any | None]]:
        if self._icon_cache is not None:
            return self._icon_cache
        try:
            import cv2
            import numpy as np
        except ImportError as exc:  # pragma: no cover - exercised in real environment
            raise RuntimeError("OpenCV is required for panel unit matching") from exc

        icons: list[tuple[str, Any, Any | None]] = []
        for name, record in self.units.items():
            if is_pseudo_any_unit_name(name):
                continue
            icon_path = self.app_root / record.icon
            if not icon_path.exists():
                continue
            icon = cv2.imread(str(icon_path), cv2.IMREAD_UNCHANGED)
            if icon is not None:
                mask = None
                if len(icon.shape) == 3 and icon.shape[2] == 4:
                    alpha = icon[:, :, 3]
                    mask = np.where(alpha > 16, 255, 0).astype("uint8")
                    icon = icon[:, :, :3]
                    icon, mask = _crop_template_to_mask(icon, mask)
                icons.append((name, icon, mask))
        self._icon_cache = icons
        return icons

    def _resized_icon_variants(self, name: str, icon, mask, source):
        key = (name, int(source.shape[1]), int(source.shape[0]))
        cached = self._resized_icon_cache.get(key)
        if cached is not None:
            return cached
        variants = _resize_template_variants_to_fit(icon, mask, source)
        self._resized_icon_cache[key] = variants
        return variants


def _card(index: int, image: Image.Image, rect: Rect) -> PanelCard:
    return PanelCard(
        index=index,
        rect=rect,
        image=image.crop((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height)),
    )


def _uniform_cards(image: Image.Image, expected_count: int) -> list[PanelCard]:
    width, height = image.size
    card_width = max(1, width // expected_count)
    cards: list[PanelCard] = []
    for index in range(expected_count):
        x = index * card_width
        right = width if index == expected_count - 1 else min(width, x + card_width)
        cards.append(_card(index, image, Rect(x, 0, right - x, height)))
    return cards


def _active_columns(image: Image.Image) -> list[int]:
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is not None:
        pixels = np.asarray(image.convert("L"))
        spread = pixels.max(axis=0) - pixels.min(axis=0)
        brightness = pixels.mean(axis=0)
        return [
            int(index)
            for index in np.where((spread > 10) | (brightness > 12))[0]
        ]

    gray = image.convert("L")
    pixels = gray.load()
    active: list[int] = []
    for x in range(gray.width):
        values = [pixels[x, y] for y in range(gray.height)]
        if max(values) - min(values) > 10 or sum(values) / len(values) > 12:
            active.append(x)
    return active


def _column_ranges(columns: list[int]) -> list[tuple[int, int]]:
    if not columns:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = columns[0]
    for column in columns[1:]:
        if column > previous + 2:
            ranges.append((start, previous))
            start = column
        previous = column
    ranges.append((start, previous))
    return [item for item in ranges if item[1] - item[0] >= 6]


def _should_use_uniform_fallback(image: Image.Image, ranges: list[tuple[int, int]]) -> bool:
    if not ranges:
        return False
    if image.width / max(1, image.height) < 2.5:
        return False
    if len(ranges) > 1:
        return False
    start, end = ranges[0]
    return (end - start + 1) >= int(image.width * 0.85)


def _estimated_uniform_card_count(image: Image.Image) -> int:
    estimated_card_width = max(1, int(image.height * 0.8))
    return max(2, min(12, round(image.width / estimated_card_width)))


def _quantity_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    return image.crop((0, int(height * 0.70), width, height))


def _unit_match_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    return image.crop(
        (
            int(width * 0.08),
            int(height * 0.08),
            int(width * 0.92),
            int(height * 0.82),
        )
    )


def _image_signature(image: Image.Image, expected_count: int) -> tuple[tuple[int, int], str, int, bytes]:
    normalized = image.convert("RGB")
    digest = blake2b(normalized.tobytes(), digest_size=8).digest()
    return normalized.size, normalized.mode, expected_count, digest


def _crop_template_to_mask(template, mask):
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in real environment
        raise RuntimeError("NumPy is required for panel unit matching") from exc

    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return template, mask
    left = max(0, int(xs.min()) - 2)
    right = min(template.shape[1], int(xs.max()) + 3)
    top = max(0, int(ys.min()) - 2)
    bottom = min(template.shape[0], int(ys.max()) + 3)
    return template[top:bottom, left:right], mask[top:bottom, left:right]


def _color_adjusted_match_score(source, icon, mask, location, score: float) -> float:
    if mask is None:
        return score
    try:
        import numpy as np
    except ImportError:
        return score

    x, y = location
    height, width = icon.shape[:2]
    patch = source[y : y + height, x : x + width]
    if patch.shape[:2] != mask.shape:
        return score
    foreground = mask > 0
    if not foreground.any():
        return score
    patch_mean = patch[foreground].mean(axis=0)
    icon_mean = icon[foreground].mean(axis=0)
    color_distance = np.linalg.norm((patch_mean - icon_mean) / 255.0)
    return max(0.0, score - 0.20 * float(color_distance))


def _template_coverage(mask, source) -> float:
    try:
        import numpy as np
    except ImportError:
        return 0.0

    return float(np.count_nonzero(mask)) / float(source.shape[0] * source.shape[1])


def _resize_template_variants_to_fit(template, mask, source):
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - exercised in real environment
        raise RuntimeError("OpenCV is required for panel unit matching") from exc

    max_width = max(1, source.shape[1] - 2)
    max_height = max(1, source.shape[0] - 2)
    height, width = template.shape[:2]
    max_scale = min(max_width / width, max_height / height, 1.0)
    variants = []
    seen_sizes: set[tuple[int, int]] = set()
    for relative_scale in (1.0, 0.92, 0.84, 0.76, 0.68):
        scale = max_scale * relative_scale
        target_size = (max(4, int(width * scale)), max(4, int(height * scale)))
        if target_size in seen_sizes:
            continue
        seen_sizes.add(target_size)
        resized = cv2.resize(template, target_size, interpolation=cv2.INTER_AREA)
        resized_mask = None
        if mask is not None:
            resized_mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
        variants.append((resized, resized_mask))
    return variants


def _read_quantity_by_cv(image: Image.Image) -> OcrResult:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return OcrResult(value=None, text="", confidence=0.0)

    rgb = np.array(image.convert("RGB"))
    source = np.array(image.convert("L"))
    threshold = np.where(
        (rgb[:, :, 0] > 165)
        & (rgb[:, :, 1] > 165)
        & (rgb[:, :, 2] > 165),
        255,
        0,
    ).astype("uint8")
    threshold = _filter_digit_components(threshold)
    if float(np.count_nonzero(threshold)) / float(threshold.size) > 0.2:
        return OcrResult(value=None, text="", confidence=0.0)
    points = cv2.findNonZero(threshold)
    if points is None:
        return OcrResult(value=None, text="", confidence=0.0)
    x, y, width, height = cv2.boundingRect(points)
    if width < 2 or height < 5:
        return OcrResult(value=None, text="", confidence=0.0)
    roi = threshold[y : y + height, x : x + width]
    gray_roi = source[y : y + height, x : x + width]
    segmented_value, segmented_confidence = _match_segmented_digits(roi)
    gray_value, gray_confidence = _match_quantity_templates_gray(gray_roi)
    if segmented_value is not None:
        if (
            segmented_value >= 10
            and height <= 9
            and gray_value is not None
            and gray_value >= 10
            and gray_confidence >= 0.70
        ):
            return OcrResult(
                value=gray_value,
                text=str(gray_value),
                confidence=gray_confidence,
            )
        if segmented_value >= 10 and segmented_confidence >= 0.70:
            return OcrResult(
                value=segmented_value,
                text=str(segmented_value),
                confidence=segmented_confidence,
            )
        if segmented_confidence >= 0.78:
            return OcrResult(
                value=segmented_value,
                text=str(segmented_value),
                confidence=segmented_confidence,
            )
    if gray_value is not None and gray_confidence >= 0.68:
        return OcrResult(value=gray_value, text=str(gray_value), confidence=gray_confidence)
    value, confidence = _match_quantity_templates(roi)
    if value is None or confidence < 0.72:
        return OcrResult(value=None, text="", confidence=confidence)
    return OcrResult(value=value, text=str(value), confidence=confidence)


def _filter_digit_components(threshold):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return threshold

    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        threshold,
        8,
    )
    filtered = np.zeros_like(threshold)
    for component_index in range(1, component_count):
        _x, y, _width, height, area = stats[component_index]
        if y <= 1:
            continue
        if area >= 5 and height >= 5:
            filtered[labels == component_index] = 255
    return filtered


def _match_quantity_templates_gray(roi) -> tuple[int | None, float]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, 0.0

    roi_aspect = roi.shape[1] / max(1, roi.shape[0])
    best_value = None
    best_score = 0.0
    for value, template, template_aspect in _quantity_gray_templates(max(10, int(roi.shape[0]))):
        if abs(template_aspect - roi_aspect) > max(0.35, roi_aspect * 0.7):
            continue
        resized = cv2.resize(
            template,
            (max(1, roi.shape[1]), max(1, roi.shape[0])),
            interpolation=cv2.INTER_AREA,
        )
        score = 1.0 - float(
            np.mean(
                np.abs(
                    roi.astype("float32") / 255.0
                    - resized.astype("float32") / 255.0
                )
            )
        )
        if score > best_score:
            best_value = value
            best_score = score
    return best_value, best_score


def _match_quantity_templates(roi) -> tuple[int | None, float]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, 0.0

    segmented_value, segmented_confidence = _match_segmented_digits(roi)
    if segmented_value is not None and segmented_confidence >= 0.55:
        return segmented_value, segmented_confidence

    best_value = None
    best_score = 0.0
    roi_aspect = roi.shape[1] / max(1, roi.shape[0])
    for value, template, template_aspect in _quantity_templates(max(10, int(roi.shape[0]))):
        if abs(template_aspect - roi_aspect) > max(0.25, roi_aspect * 0.65):
            continue
        resized = cv2.resize(
            template,
            (max(1, roi.shape[1]), max(1, roi.shape[0])),
            interpolation=cv2.INTER_AREA,
        )
        roi_float = roi.astype("float32") / 255.0
        template_float = resized.astype("float32") / 255.0
        score = 1.0 - float(np.mean(np.abs(roi_float - template_float)))
        if score > best_score or abs(score - best_score) < 0.000001:
            best_value = value
            best_score = score
    return best_value, best_score


def _match_segmented_digits(roi) -> tuple[int | None, float]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, 0.0

    binary = roi > 0
    column_counts = binary.sum(axis=0)
    groups: list[tuple[int, int]] = []
    start = None
    for index, count in enumerate(column_counts):
        if count > 0 and start is None:
            start = index
        elif count == 0 and start is not None:
            groups.append((start, index))
            start = None
    if start is not None:
        groups.append((start, len(column_counts)))
    groups = [(left, right) for left, right in groups if right - left >= 2]
    if not 1 <= len(groups) <= 3:
        return None, 0.0

    digits: list[str] = []
    confidences: list[float] = []
    for left, right in groups:
        digit_roi = roi[:, left:right]
        points = cv2.findNonZero(digit_roi)
        if points is None:
            return None, 0.0
        x, y, width, height = cv2.boundingRect(points)
        digit_roi = digit_roi[y : y + height, x : x + width]
        digit, confidence = _match_single_digit(digit_roi)
        if digit is None:
            return None, 0.0
        digits.append(str(digit))
        confidences.append(confidence)
    return int("".join(digits)), float(np.mean(confidences))


def _match_single_digit(roi) -> tuple[int | None, float]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, 0.0

    roi_aspect = roi.shape[1] / max(1, roi.shape[0])
    best_digit = None
    best_score = 0.0
    for digit, template, template_aspect in _digit_templates(max(10, int(roi.shape[0]))):
        if abs(template_aspect - roi_aspect) > max(0.35, roi_aspect * 0.8):
            continue
        resized = cv2.resize(
            template,
            (max(1, roi.shape[1]), max(1, roi.shape[0])),
            interpolation=cv2.INTER_AREA,
        )
        score = 1.0 - float(
            np.mean(
                np.abs(
                    roi.astype("float32") / 255.0
                    - resized.astype("float32") / 255.0
                )
            )
        )
        if score > best_score:
            best_digit = digit
            best_score = score
    return best_digit, best_score


@lru_cache(maxsize=16)
def _quantity_templates(height: int):
    templates = []
    font = _quantity_font(height)
    for value in range(1, 100):
        text = str(value)
        bbox_image = Image.new("L", (80, 40), 0)
        draw = ImageDraw.Draw(bbox_image)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = max(1, bbox[2] - bbox[0] + 4)
        image = Image.new("L", (width, height + 6), 0)
        draw = ImageDraw.Draw(image)
        draw.text((2 - bbox[0], 2 - bbox[1]), text, fill=255, font=font)
        template = _tight_binary_image(image)
        templates.append((value, template, template.shape[1] / max(1, template.shape[0])))
    return tuple(templates)


@lru_cache(maxsize=16)
def _quantity_gray_templates(height: int):
    templates = []
    font = _quantity_font(height)
    for value in range(1, 100):
        text = str(value)
        bbox_image = Image.new("L", (80, 40), 0)
        draw = ImageDraw.Draw(bbox_image)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = max(1, bbox[2] - bbox[0] + 4)
        image = Image.new("L", (width, height + 6), 0)
        draw = ImageDraw.Draw(image)
        draw.text((2 - bbox[0], 2 - bbox[1]), text, fill=255, font=font)
        template = _tight_gray_image(image)
        templates.append((value, template, template.shape[1] / max(1, template.shape[0])))
    return tuple(templates)


@lru_cache(maxsize=16)
def _digit_templates(height: int):
    templates = []
    font = _quantity_font(height)
    for value in range(10):
        text = str(value)
        bbox_image = Image.new("L", (40, 40), 0)
        draw = ImageDraw.Draw(bbox_image)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = max(1, bbox[2] - bbox[0] + 4)
        image = Image.new("L", (width, height + 6), 0)
        draw = ImageDraw.Draw(image)
        draw.text((2 - bbox[0], 2 - bbox[1]), text, fill=255, font=font)
        template = _tight_binary_image(image)
        templates.append((value, template, template.shape[1] / max(1, template.shape[0])))
    return tuple(templates)


def _quantity_font(height: int):
    for font_name in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(font_name, max(8, int(height * 1.15)))
        except OSError:
            continue
    return ImageFont.load_default()


def _tight_binary_image(image: Image.Image):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in real environment
        raise RuntimeError("OpenCV and NumPy are required for quantity matching") from exc

    array = np.array(image)
    _, binary = cv2.threshold(array, 127, 255, cv2.THRESH_BINARY)
    points = cv2.findNonZero(binary)
    if points is None:
        return binary
    x, y, width, height = cv2.boundingRect(points)
    return binary[y : y + height, x : x + width]


def _tight_gray_image(image: Image.Image):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in real environment
        raise RuntimeError("OpenCV and NumPy are required for quantity matching") from exc

    array = np.array(image)
    _, binary = cv2.threshold(array, 15, 255, cv2.THRESH_BINARY)
    points = cv2.findNonZero(binary)
    if points is None:
        return array
    x, y, width, height = cv2.boundingRect(points)
    return array[y : y + height, x : x + width]
