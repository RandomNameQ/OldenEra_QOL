from oldenera_qol.modules.placement_grid.models import PlacedUnit, PlacementTemplate
from oldenera_qol.modules.unit_placer.calibration import CalibratedCell, UnitPlacerCalibration
from oldenera_qol.modules.unit_placer.panel_scanner import PanelUnitDetection
from oldenera_qol.modules.unit_placer.planner import build_calibrated_move_plan


def test_calibrated_plan_matches_template_units_to_source_and_target_cells() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(0, 0, 10, 20),
            CalibratedCell(1, 0, 30, 40),
            CalibratedCell(3, 4, 300, 400),
            CalibratedCell(4, 4, 500, 600),
        ],
    )
    detections = [
        PanelUnitDetection("Skeleton", 31, 0.9, panel_index=0),
        PanelUnitDetection("Skeleton", 5, 0.9, panel_index=1),
    ]
    template = PlacementTemplate(
        name="attack",
        units=[
            PlacedUnit("Skeleton", 4, 4, 5),
            PlacedUnit("Skeleton", 3, 4, 31),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((30, 40), (500, 600), "Skeleton x5 -> row 5, col 5"),
        ((10, 20), (300, 400), "Skeleton x31 -> row 4, col 5"),
    ]
    assert not any("Quantity rules relaxed" in message for message in plan.log_messages)


def test_calibrated_plan_relaxes_quantity_rules_for_duplicate_panel_units() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(0, 0, 10, 20),
            CalibratedCell(0, 1, 30, 40),
            CalibratedCell(1, 0, 50, 60),
            CalibratedCell(1, 1, 70, 80),
            CalibratedCell(2, 0, 90, 100),
            CalibratedCell(2, 1, 110, 120),
        ],
        panel_source_cell_numbers=[1, 2, 3],
    )
    detections = [
        PanelUnitDetection("Skeleton", 1, 0.9, panel_index=0),
        PanelUnitDetection("Skeleton", 1, 0.9, panel_index=1),
        PanelUnitDetection("Skeleton", 58, 0.9, panel_index=2),
    ]
    template = PlacementTemplate(
        name="test",
        units=[
            PlacedUnit("Skeleton", 1, 1, 18),
            PlacedUnit("Skeleton", 2, 0, 18),
            PlacedUnit("Skeleton", 2, 1, 18, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((50, 60), (110, 120), "Skeleton x58 -> row 3, col 2"),
        ((10, 20), (70, 80), "Skeleton x1 -> row 2, col 2"),
        ((30, 40), (90, 100), "Skeleton x1 -> row 3, col 1"),
    ]
    assert any(
        "Quantity rules relaxed for Skeleton" in message
        for message in plan.log_messages
    )


def test_calibrated_plan_assigns_max_stack_before_any_slots() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(0, 0, 10, 20),
            CalibratedCell(0, 1, 30, 40),
            CalibratedCell(1, 0, 50, 60),
            CalibratedCell(1, 1, 70, 80),
            CalibratedCell(2, 0, 90, 100),
            CalibratedCell(2, 1, 110, 120),
        ],
        panel_source_cell_numbers=[1, 2, 3],
    )
    detections = [
        PanelUnitDetection("Skeleton", 5, 0.9, panel_index=0),
        PanelUnitDetection("Skeleton", 80, 0.9, panel_index=1),
        PanelUnitDetection("Skeleton", 12, 0.9, panel_index=2),
    ]
    template = PlacementTemplate(
        name="test",
        units=[
            PlacedUnit("Skeleton", 0, 1, 18, "any"),
            PlacedUnit("Skeleton", 1, 1, 18, "any"),
            PlacedUnit("Skeleton", 2, 1, 18, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((30, 40), (110, 120), "Skeleton x80 -> row 3, col 2"),
        ((10, 20), (30, 40), "Skeleton xany -> row 1, col 2"),
        ((50, 60), (70, 80), "Skeleton xany -> row 2, col 2"),
    ]


def test_calibrated_plan_reports_missing_calibration_and_units() -> None:
    calibration = UnitPlacerCalibration(profile_name="default")
    detections = [PanelUnitDetection("Skeleton", 31, 0.9, panel_index=0)]
    template = PlacementTemplate(name="attack", units=[PlacedUnit("Wight", 0, 0, 1)])

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert plan.actions == []
    assert any("Numbered grid calibration is missing" in message for message in plan.log_messages)
    assert any("Missing detected unit for Wight" in message for message in plan.log_messages)
