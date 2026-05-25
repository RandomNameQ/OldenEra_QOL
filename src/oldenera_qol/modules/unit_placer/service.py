from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Callable

from oldenera_qol.modules.placement_grid.models import PlacementTemplate
from oldenera_qol.modules.unit_placer.calibration import UnitPlacerCalibration
from oldenera_qol.modules.unit_placer.panel_scanner import PanelUnitDetection, PanelUnitScanner
from oldenera_qol.modules.unit_placer.planner import MovePlan, build_move_plan
from oldenera_qol.modules.unit_placer.planner import build_calibrated_move_plan
from oldenera_qol.profiles.models import UnitProfile
from oldenera_qol.units.models import UnitRecord
from oldenera_qol.vision.models import Rect, UnitDetection
from oldenera_qol.vision.ocr import QuantityOcr
from oldenera_qol.vision.template_matching import match_template

LogSink = Callable[[str], None]
PANEL_SLOT_COUNT = 7


class UnitPlacerService:
    def __init__(
        self,
        profile: UnitProfile,
        ocr: QuantityOcr,
        log: LogSink | None = None,
    ) -> None:
        self.profile = profile
        self.ocr = ocr
        self.log = log or (lambda message: None)

    def detect(self, screenshot) -> list[UnitDetection]:
        detections: list[UnitDetection] = []
        for template in self.profile.templates:
            matches = match_template(
                screenshot,
                Path(template.image_path),
                template.id,
                template.match_threshold,
            )
            for match in matches:
                region = template.quantity_region
                crop_box = (
                    match.rect.x + region.x_offset,
                    match.rect.y + region.y_offset,
                    match.rect.x + region.x_offset + region.width,
                    match.rect.y + region.y_offset + region.height,
                )
                quantity_crop = screenshot.crop(crop_box)
                ocr_result = self.ocr.read_quantity(quantity_crop)
                detections.append(
                    UnitDetection(
                        template_id=match.template_id,
                        rect=Rect(
                            x=match.rect.x,
                            y=match.rect.y,
                            width=match.rect.width,
                            height=match.rect.height,
                        ),
                        confidence=match.confidence,
                        quantity=ocr_result.value,
                        quantity_confidence=ocr_result.confidence,
                        quantity_text=ocr_result.text,
                    )
                )
                if ocr_result.value is None:
                    self.log(f"OCR returned no digits for {template.id} at {match.rect.center}")
        return detections

    def plan(self, detections: list[UnitDetection]) -> MovePlan:
        return build_move_plan(detections, self.profile)


class CalibratedUnitPlacerService:
    def __init__(
        self,
        units: dict[str, UnitRecord],
        app_root: Path,
        ocr: QuantityOcr,
        log: LogSink | None = None,
    ) -> None:
        self.units = units
        self.app_root = app_root
        self.ocr = ocr
        self.log = log or (lambda message: None)
        self.scanner = PanelUnitScanner(
            units=self.units,
            app_root=self.app_root,
            ocr=self.ocr,
        )
        self._scan_lock = Lock()

    def scan(
        self,
        screenshot,
        calibration: UnitPlacerCalibration,
        log_detections: bool = True,
    ) -> list[PanelUnitDetection]:
        if calibration.panel_scan_rect is None:
            if log_detections:
                self.log("Panel scan area is not calibrated")
            return []
        with self._scan_lock:
            detections = self.scanner.scan(
                screenshot=screenshot,
                panel_rect=calibration.panel_scan_rect,
                expected_count=PANEL_SLOT_COUNT,
            )
        return self._log_scan_detections(detections, log_detections)

    def scan_panel_image(
        self,
        panel_image,
        log_detections: bool = True,
    ) -> list[PanelUnitDetection]:
        with self._scan_lock:
            detections = self.scanner.scan_panel_image(panel_image, expected_count=PANEL_SLOT_COUNT)
        return self._log_scan_detections(detections, log_detections)

    def _log_scan_detections(
        self,
        detections: list[PanelUnitDetection],
        log_detections: bool,
    ) -> list[PanelUnitDetection]:
        if not log_detections:
            return detections
        for detection in detections:
            if detection.unit_name == "unknown":
                ocr_detail = (
                    f"; OCR: {detection.quantity_text}"
                    if detection.quantity is None and detection.quantity_text
                    else ""
                )
                self.log(
                    f"Panel card {detection.panel_index + 1}: unknown unit "
                    f"(confidence {detection.confidence:.2f}){ocr_detail}"
                    f"{_candidate_log_suffix(detection)}"
                )
            elif detection.quantity is None:
                detail = f": {detection.quantity_text}" if detection.quantity_text else ""
                self.log(
                    f"Panel card {detection.panel_index + 1}: {detection.unit_name}; "
                    f"OCR returned no digits{detail}{_candidate_log_suffix(detection)}"
                )
            else:
                self.log(
                    f"Panel card {detection.panel_index + 1}: "
                    f"{detection.unit_name} x{detection.quantity}"
                    f"{_candidate_log_suffix(detection)}"
                )
        return detections

    def plan(
        self,
        detections: list[PanelUnitDetection],
        template: PlacementTemplate,
        calibration: UnitPlacerCalibration,
    ) -> MovePlan:
        return build_calibrated_move_plan(detections, template, calibration)


def _candidate_log_suffix(detection: PanelUnitDetection) -> str:
    if not detection.match_candidates:
        return ""
    candidates = ", ".join(
        f"{name} {score:.2f}" for name, score in detection.match_candidates[:3]
    )
    return f"; candidates: {candidates}"
