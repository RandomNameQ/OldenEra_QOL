from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from dataclasses import replace

from oldenera_qol.modules.placement_grid.models import PlacedUnit, PlacementTemplate
from oldenera_qol.modules.unit_placer.calibration import UnitPlacerCalibration
from oldenera_qol.modules.unit_placer.panel_scanner import PanelUnitDetection
from oldenera_qol.profiles.models import DestinationSlot, UnitProfile
from oldenera_qol.units.models import PSEUDO_ANY_UNIT_NAME, is_pseudo_any_unit_name
from oldenera_qol.vision.models import Rect, UnitDetection


@dataclass(frozen=True, slots=True)
class MoveAction:
    detection: UnitDetection | None
    slot: DestinationSlot | None
    source: tuple[int, int]
    target: tuple[int, int]
    label: str = ""


@dataclass(frozen=True, slots=True)
class MovePlan:
    actions: list[MoveAction]
    log_messages: list[str]


def build_move_plan(detections: list[UnitDetection], profile: UnitProfile) -> MovePlan:
    logs: list[str] = []
    actions: list[MoveAction] = []
    available = sorted(
        [detection for detection in detections if detection.quantity is not None],
        key=lambda item: (item.template_id, item.quantity or 0, item.rect.y, item.rect.x),
    )
    used_detection_indexes: set[int] = set()

    for slot in profile.slots:
        candidates = [
            (index, detection)
            for index, detection in enumerate(available)
            if index not in used_detection_indexes
            and detection.template_id == slot.unit_template_id
            and slot.matches_quantity(detection.quantity)
        ]
        if not candidates:
            logs.append(
                f"Missing unit for slot {slot.id}: "
                f"{slot.unit_template_id} x{slot.quantity_label()}"
            )
            continue

        index, detection = candidates[0]
        used_detection_indexes.add(index)
        actions.append(
            MoveAction(
                detection=detection,
                slot=slot,
                source=detection.rect.center,
                target=(slot.target_x, slot.target_y),
                label=f"{slot.unit_template_id} x{slot.quantity_label()}",
            )
        )
        logs.append(
            f"Planned {slot.unit_template_id} x{slot.quantity_label()} "
            f"from {detection.rect.center} to {(slot.target_x, slot.target_y)}"
        )

    for detection in detections:
        if detection.quantity is None:
            logs.append(
                f"Skipped {detection.template_id} at {detection.rect.center}: OCR returned no digits"
            )

    return MovePlan(actions=actions, log_messages=logs)


def build_calibrated_move_plan(
    detections: list[PanelUnitDetection],
    template: PlacementTemplate,
    calibration: UnitPlacerCalibration,
) -> MovePlan:
    logs: list[str] = []
    actions: list[MoveAction] = []
    if not calibration.grid_cells:
        logs.append("Numbered grid calibration is missing")

    ordered_detections = _resolve_template_candidate_detections(
        sorted(detections, key=lambda item: item.panel_index),
        template,
        logs,
    )
    relaxed_quantity_units = _units_with_relaxed_quantity_matching(
        ordered_detections,
        template,
    )
    for unit_name in sorted(relaxed_quantity_units):
        logs.append(
            f"Quantity rules relaxed for {unit_name}: using panel order because "
            "template quantities do not match enough detected stacks"
        )
    assignments, used_detection_indexes = _assign_calibrated_detections(
        ordered_detections,
        template,
        relaxed_quantity_units,
        logs,
    )
    for placed, index, detection in assignments:
        source_cell = calibration.source_cell_for_panel_index(detection.panel_index)
        target_cell = calibration.cell_at(placed.row, placed.col)
        if source_cell is None:
            logs.append(
                f"Missing numbered source cell for panel unit {detection.panel_index + 1}: "
                f"{detection.unit_name}"
            )
            continue
        if target_cell is None:
            logs.append(
                f"Missing numbered target cell for row {placed.row + 1}, col {placed.col + 1}: "
                f"{placed.unit_name}"
            )
            continue

        quantity_label = (
            "?" if detection.quantity is None else str(detection.quantity)
        )
        label_quantity = (
            quantity_label
            if placed.normalized_mode() == "max" or placed.unit_name in relaxed_quantity_units
            else placed.quantity_label()
        )
        label = f"{placed.unit_name} x{label_quantity} -> row {placed.row + 1}, col {placed.col + 1}"
        actions.append(
            MoveAction(
                detection=UnitDetection(
                    template_id=detection.unit_name,
                    rect=Rect(source_cell.x, source_cell.y, 1, 1),
                    confidence=detection.confidence,
                    quantity=detection.quantity,
                    quantity_confidence=detection.quantity_confidence,
                    quantity_text=detection.quantity_text,
                ),
                slot=None,
                source=source_cell.point,
                target=target_cell.point,
                label=label,
            )
        )
        logs.append(f"Planned {label}")

    actions = _swap_aware_action_order(actions, logs)

    for index, detection in enumerate(ordered_detections):
        if index in used_detection_indexes or detection.unit_name == "unknown":
            continue
        logs.append(
            f"Detected {detection.unit_name} on panel card {detection.panel_index + 1} "
            "was not moved: template has no remaining target"
        )

    return MovePlan(actions=actions, log_messages=logs)


def _swap_aware_action_order(
    actions: list[MoveAction],
    logs: list[str],
) -> list[MoveAction]:
    current_sources = {index: action.source for index, action in enumerate(actions)}
    occupied_by_source = {
        action.source: index
        for index, action in enumerate(actions)
    }
    ordered: list[MoveAction] = []

    for index, action in enumerate(actions):
        current_source = current_sources[index]
        if current_source == action.target:
            continue

        displaced_index = occupied_by_source.get(action.target)
        if occupied_by_source.get(current_source) == index:
            occupied_by_source.pop(current_source)
        if displaced_index is not None and displaced_index != index:
            current_sources[displaced_index] = current_source
            occupied_by_source[current_source] = displaced_index
        current_sources[index] = action.target
        occupied_by_source[action.target] = index
        ordered.append(replace(action, source=current_source))

    return ordered


def _resolve_template_candidate_detections(
    detections: list[PanelUnitDetection],
    template: PlacementTemplate,
    logs: list[str],
) -> list[PanelUnitDetection]:
    expected_counts = Counter(
        unit.unit_name
        for unit in template.units
        if unit.unit_name and not is_pseudo_any_unit_name(unit.unit_name)
    )
    if not expected_counts:
        return detections
    if any(is_pseudo_any_unit_name(unit.unit_name) for unit in template.units):
        return _resolve_named_detections_for_any_template(detections, expected_counts, logs)

    resolved = list(detections)
    detected_counts = Counter(
        detection.unit_name
        for detection in resolved
        if detection.unit_name != "unknown"
    )
    missing_units = [
        unit_name
        for unit_name, expected_count in expected_counts.items()
        for _index in range(max(0, expected_count - detected_counts.get(unit_name, 0)))
    ]

    for missing_unit in missing_units:
        candidates: list[tuple[float, float, int, PanelUnitDetection]] = []
        for index, detection in enumerate(resolved):
            if detection.unit_name == missing_unit or detection.unit_name == "unknown":
                continue
            if detected_counts[detection.unit_name] <= expected_counts.get(detection.unit_name, 0):
                continue
            candidate_score = _candidate_score(detection, missing_unit)
            if candidate_score is None:
                continue
            score_gap = detection.confidence - candidate_score
            if candidate_score < 0.45 or score_gap > 0.14:
                continue
            candidates.append((candidate_score, -score_gap, -index, detection))

        if not candidates:
            continue

        candidate_score, _negative_gap, negative_index, detection = max(candidates)
        index = -negative_index
        previous_unit = detection.unit_name
        resolved[index] = replace(
            detection,
            unit_name=missing_unit,
            confidence=candidate_score,
        )
        detected_counts[previous_unit] -= 1
        detected_counts[missing_unit] += 1
        logs.append(
            f"Resolved panel card {detection.panel_index + 1} as {missing_unit} "
            f"from candidates; primary was {previous_unit}"
        )

    return resolved


def _resolve_named_detections_for_any_template(
    detections: list[PanelUnitDetection],
    expected_counts: Counter[str],
    logs: list[str],
) -> list[PanelUnitDetection]:
    selected: dict[int, tuple[str, float]] = {}
    used_indexes: set[int] = set()
    for unit_name, expected_count in expected_counts.items():
        for _index in range(expected_count):
            candidates: list[tuple[float, int, int, PanelUnitDetection]] = []
            for detection_index, detection in enumerate(detections):
                if detection_index in used_indexes:
                    continue
                score = _candidate_score(detection, unit_name)
                if score is None and detection.unit_name == unit_name:
                    score = detection.confidence
                if score is None or score < 0.45:
                    continue
                quantity = detection.quantity if detection.quantity is not None else -1
                candidates.append((score, quantity, -detection_index, detection))
            if not candidates:
                continue
            score, _quantity, negative_index, detection = max(candidates)
            detection_index = -negative_index
            selected[detection_index] = (unit_name, score)
            used_indexes.add(detection_index)
            if detection.unit_name != unit_name:
                logs.append(
                    f"Resolved panel card {detection.panel_index + 1} as {unit_name} "
                    f"from candidates; primary was {detection.unit_name}"
                )

    resolved: list[PanelUnitDetection] = []
    for index, detection in enumerate(detections):
        selected_unit = selected.get(index)
        if selected_unit is not None:
            unit_name, score = selected_unit
            resolved.append(
                replace(
                    detection,
                    unit_name=unit_name,
                    confidence=score,
                )
            )
            continue
        if detection.unit_name in expected_counts or detection.unit_name == "unknown":
            resolved.append(
                replace(
                    detection,
                    unit_name=PSEUDO_ANY_UNIT_NAME,
                    confidence=0.0,
                )
            )
            continue
        resolved.append(detection)
    return resolved


def _candidate_score(detection: PanelUnitDetection, unit_name: str) -> float | None:
    for candidate_name, score in detection.match_candidates:
        if candidate_name == unit_name:
            return score
    return None


def _assign_calibrated_detections(
    ordered_detections: list[PanelUnitDetection],
    template: PlacementTemplate,
    relaxed_quantity_units: set[str],
    logs: list[str],
) -> tuple[list[tuple[PlacedUnit, int, PanelUnitDetection]], set[int]]:
    assignments: list[tuple[PlacedUnit, int, PanelUnitDetection]] = []
    used_detection_indexes: set[int] = set()
    for placed in _prioritized_calibrated_placements(template.units):
        candidates = _candidate_detections(
            ordered_detections,
            used_detection_indexes,
            placed,
            relaxed_quantity=placed.unit_name in relaxed_quantity_units,
        )
        if not candidates:
            logs.append(f"Missing detected unit for {placed.unit_name} x{placed.quantity_label()}")
            continue
        index, detection = candidates[0]
        used_detection_indexes.add(index)
        assignments.append((placed, index, detection))
    return assignments, used_detection_indexes


def _prioritized_calibrated_placements(units: list[PlacedUnit]) -> list[PlacedUnit]:
    ordered = sorted(
        enumerate(units),
        key=lambda item: (
            _placement_priority(item[1]),
            item[0],
        ),
    )
    return [unit for _index, unit in ordered]


def _placement_priority(unit: PlacedUnit) -> tuple[int, int]:
    mode_priority = _quantity_priority(unit)
    if is_pseudo_any_unit_name(unit.unit_name):
        if unit.normalized_mode() == "max":
            return (1, mode_priority)
        return (3, mode_priority)
    return (0, mode_priority)


def _quantity_priority(unit: PlacedUnit) -> int:
    mode = unit.normalized_mode()
    if mode == "max":
        return 0
    if mode == "exact":
        return 1
    return 2


def _candidate_detections(
    ordered_detections: list[PanelUnitDetection],
    used_detection_indexes: set[int],
    placed: PlacedUnit,
    relaxed_quantity: bool,
) -> list[tuple[int, PanelUnitDetection]]:
    if is_pseudo_any_unit_name(placed.unit_name):
        candidates = [
            (index, detection)
            for index, detection in enumerate(ordered_detections)
            if index not in used_detection_indexes
            and detection.unit_name != "unknown"
            and (
                placed.normalized_mode() == "max"
                or relaxed_quantity
                or placed.matches_quantity(detection.quantity)
            )
        ]
        if placed.normalized_mode() != "max":
            return candidates
        return _sort_max_stack_candidates(candidates)

    candidates = [
        (index, detection)
        for index, detection in enumerate(ordered_detections)
        if index not in used_detection_indexes
        and detection.unit_name == placed.unit_name
        and (
            placed.normalized_mode() == "max"
            or relaxed_quantity
            or placed.matches_quantity(detection.quantity)
        )
    ]
    if placed.normalized_mode() != "max":
        return candidates
    return _sort_max_stack_candidates(candidates)


def _sort_max_stack_candidates(
    candidates: list[tuple[int, PanelUnitDetection]],
) -> list[tuple[int, PanelUnitDetection]]:
    return sorted(
        candidates,
        key=lambda item: (
            item[1].quantity is not None,
            item[1].quantity or -1,
            -item[1].panel_index,
        ),
        reverse=True,
    )



def _units_with_relaxed_quantity_matching(
    ordered_detections: list[PanelUnitDetection],
    template: PlacementTemplate,
) -> set[str]:
    unit_names = {
        placed.unit_name
        for placed in template.units
        if not is_pseudo_any_unit_name(placed.unit_name)
    }
    relaxed: set[str] = set()
    for unit_name in unit_names:
        placements = [placed for placed in template.units if placed.unit_name == unit_name]
        detections = [
            detection for detection in ordered_detections if detection.unit_name == unit_name
        ]
        if len(detections) < len(placements):
            continue
        used: set[int] = set()
        all_quantity_rules_match = True
        for placed in placements:
            match_index = next(
                (
                    index
                    for index, detection in enumerate(detections)
                    if index not in used and placed.matches_quantity(detection.quantity)
                ),
                None,
            )
            if match_index is None:
                all_quantity_rules_match = False
                break
            used.add(match_index)
        if not all_quantity_rules_match:
            relaxed.add(unit_name)
    return relaxed
