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


def test_calibrated_plan_any_max_uses_largest_stacks_before_any_slots() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(8)
        ],
    )
    detections = [
        PanelUnitDetection("Skeleton", 10, 0.9, panel_index=0),
        PanelUnitDetection("Wight", 80, 0.9, panel_index=1),
        PanelUnitDetection("Archer", 30, 0.9, panel_index=2),
        PanelUnitDetection("Dragon", 70, 0.9, panel_index=3),
    ]
    template = PlacementTemplate(
        name="any-max",
        units=[
            PlacedUnit("ANY", 4, 0, 1, "any"),
            PlacedUnit("ANY", 5, 0, 1, "max"),
            PlacedUnit("ANY", 6, 0, 1, "any"),
            PlacedUnit("ANY", 7, 0, 1, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((10, 10), (50, 50), "ANY x80 -> row 6, col 1"),
        ((30, 30), (70, 70), "ANY x70 -> row 8, col 1"),
        ((0, 0), (40, 40), "ANY xany -> row 5, col 1"),
        ((20, 20), (60, 60), "ANY xany -> row 7, col 1"),
    ]


def test_calibrated_plan_any_max_works_with_generic_any_detections() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(8)
        ],
    )
    detections = [
        PanelUnitDetection("ANY", 313, 0.0, panel_index=0),
        PanelUnitDetection("ANY", 54, 0.0, panel_index=1),
        PanelUnitDetection("ANY", 60, 0.0, panel_index=2),
        PanelUnitDetection("ANY", 36, 0.0, panel_index=3),
    ]
    template = PlacementTemplate(
        name="generic-any-max",
        units=[
            PlacedUnit("ANY", 4, 0, 1, "any"),
            PlacedUnit("ANY", 5, 0, 1, "max"),
            PlacedUnit("ANY", 6, 0, 1, "any"),
            PlacedUnit("ANY", 7, 0, 1, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((0, 0), (50, 50), "ANY x313 -> row 6, col 1"),
        ((20, 20), (70, 70), "ANY x60 -> row 8, col 1"),
        ((10, 10), (40, 40), "ANY xany -> row 5, col 1"),
        ((30, 30), (60, 60), "ANY xany -> row 7, col 1"),
    ]


def test_calibrated_plan_named_slot_reserves_named_unit_before_any_max() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(5)
        ],
    )
    detections = [
        PanelUnitDetection("Archer", 90, 0.9, panel_index=0),
        PanelUnitDetection("Archer", 10, 0.9, panel_index=1),
        PanelUnitDetection("Wight", 50, 0.9, panel_index=2),
    ]
    template = PlacementTemplate(
        name="any-max-before-named-any",
        units=[
            PlacedUnit("Archer", 3, 0, 1, "any"),
            PlacedUnit("ANY", 4, 0, 1, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((0, 0), (30, 30), "Archer xany -> row 4, col 1"),
        ((20, 20), (40, 40), "ANY x50 -> row 5, col 1"),
    ]


def test_calibrated_plan_any_template_keeps_best_named_match_for_named_slot() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(8)
        ],
    )
    detections = [
        PanelUnitDetection(
            "Mage",
            313,
            0.51,
            panel_index=0,
            match_candidates=(("Mage", 0.51),),
        ),
        PanelUnitDetection(
            "ANY",
            54,
            0.0,
            panel_index=1,
            match_candidates=(("Mage", 0.88),),
        ),
        PanelUnitDetection("ANY", 60, 0.0, panel_index=2),
        PanelUnitDetection("ANY", 36, 0.0, panel_index=3),
    ]
    template = PlacementTemplate(
        name="mixed-any",
        units=[
            PlacedUnit("ANY", 4, 0, 1, "any"),
            PlacedUnit("ANY", 5, 0, 1, "max"),
            PlacedUnit("Mage", 6, 0, 1, "max"),
            PlacedUnit("ANY", 7, 0, 1, "max"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((10, 10), (60, 60), "Mage x54 -> row 7, col 1"),
        ((0, 0), (50, 50), "ANY x313 -> row 6, col 1"),
        ((20, 20), (70, 70), "ANY x60 -> row 8, col 1"),
        ((30, 30), (40, 40), "ANY xany -> row 5, col 1"),
    ]
    assert any("Resolved panel card 2 as Mage" in message for message in plan.log_messages)


def test_calibrated_plan_moves_any_max_first_and_updates_displaced_sources() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, col, row * 100 + col * 10, row * 100 + col * 10)
            for row in range(11)
            for col in range(2)
        ],
        panel_source_cell_numbers=[3, 5, 7, 11, 15, 17, 19],
    )
    detections = [
        PanelUnitDetection("ANY", 60, 0.0, panel_index=0),
        PanelUnitDetection("ANY", 314, 0.0, panel_index=1),
        PanelUnitDetection("ANY", 313, 0.0, panel_index=2),
        PanelUnitDetection("ANY", 17, 0.0, panel_index=3),
        PanelUnitDetection("ANY", 36, 0.0, panel_index=4),
        PanelUnitDetection("ANY", 4, 0.0, panel_index=5),
        PanelUnitDetection("Aureate Dancer", 54, 0.9, panel_index=6),
    ]
    template = PlacementTemplate(
        name="any-test",
        units=[
            PlacedUnit("Aureate Dancer", 9, 0, 1, "max"),
            PlacedUnit("ANY", 8, 0, 1, "max"),
            PlacedUnit("ANY", 10, 0, 1, "max"),
            PlacedUnit("ANY", 10, 1, 1, "any"),
            PlacedUnit("ANY", 9, 1, 1, "any"),
            PlacedUnit("ANY", 8, 1, 1, "any"),
            PlacedUnit("ANY", 7, 1, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.detection.quantity, action.target) for action in plan.actions[:2]] == [
        (314, (800, 800)),
        (313, (1000, 1000)),
    ]
    displaced = next(action for action in plan.actions if action.detection.quantity == 4)
    assert (displaced.source, displaced.target) == ((200, 200), (710, 710))


def test_calibrated_plan_resolves_surplus_primary_match_to_missing_template_candidate() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, (row + 1) * 10, (row + 1) * 10)
            for row in range(7)
        ],
    )
    detections = [
        PanelUnitDetection(
            "Medusa",
            313,
            0.62,
            panel_index=2,
            match_candidates=(
                ("Medusa", 0.62),
                ("Infernal Troglodyte", 0.55),
            ),
        ),
        PanelUnitDetection(
            "Medusa",
            36,
            0.69,
            panel_index=4,
            match_candidates=(
                ("Medusa", 0.69),
                ("Infernal Troglodyte", 0.48),
            ),
        ),
    ]
    template = PlacementTemplate(
        name="test",
        units=[
            PlacedUnit("Medusa", 6, 0, 1, "max"),
            PlacedUnit("Infernal Troglodyte", 5, 0, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((50, 50), (70, 70), "Medusa x36 -> row 7, col 1"),
        ((30, 30), (60, 60), "Infernal Troglodyte xany -> row 6, col 1"),
    ]
    assert any(
        "Resolved panel card 3 as Infernal Troglodyte" in message
        for message in plan.log_messages
    )


def test_calibrated_plan_candidate_resolution_is_not_unit_specific() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, (row + 1) * 10, (row + 1) * 10)
            for row in range(4)
        ],
    )
    detections = [
        PanelUnitDetection(
            "Archer",
            22,
            0.61,
            panel_index=0,
            match_candidates=(("Archer", 0.61), ("Wight", 0.54)),
        ),
        PanelUnitDetection(
            "Archer",
            9,
            0.68,
            panel_index=1,
            match_candidates=(("Archer", 0.68), ("Wight", 0.43)),
        ),
    ]
    template = PlacementTemplate(
        name="generic",
        units=[
            PlacedUnit("Archer", 2, 0, 1, "max"),
            PlacedUnit("Wight", 3, 0, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((20, 20), (30, 30), "Archer x9 -> row 3, col 1"),
        ((10, 10), (40, 40), "Wight xany -> row 4, col 1"),
    ]


def test_calibrated_plan_moves_blocking_units_first() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(9)
        ],
    )
    detections = [
        PanelUnitDetection("X", 1, 0.9, panel_index=3),
        PanelUnitDetection("Y", 1, 0.9, panel_index=7),
    ]
    template = PlacementTemplate(
        name="chain",
        units=[
            PlacedUnit("X", 7, 0, 1, "any"),
            PlacedUnit("Y", 8, 0, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((30, 30), (70, 70), "X xany -> row 8, col 1"),
        ((30, 30), (80, 80), "Y xany -> row 9, col 1"),
    ]


def test_calibrated_plan_collapses_swap_cycles_to_non_reversing_moves() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row, 0, row * 10, row * 10)
            for row in range(3)
        ],
    )
    detections = [
        PanelUnitDetection("X", 1, 0.9, panel_index=0),
        PanelUnitDetection("Y", 1, 0.9, panel_index=1),
        PanelUnitDetection("Z", 1, 0.9, panel_index=2),
    ]
    template = PlacementTemplate(
        name="cycle",
        units=[
            PlacedUnit("X", 1, 0, 1, "any"),
            PlacedUnit("Y", 2, 0, 1, "any"),
            PlacedUnit("Z", 0, 0, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((0, 0), (10, 10), "X xany -> row 2, col 1"),
        ((0, 0), (20, 20), "Y xany -> row 3, col 1"),
    ]


def test_calibrated_plan_moves_regular_units_before_pseudo_any_units() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(0, 0, 10, 20),
            CalibratedCell(0, 1, 30, 40),
            CalibratedCell(0, 2, 50, 60),
            CalibratedCell(0, 3, 70, 80),
            CalibratedCell(1, 0, 100, 200),
            CalibratedCell(1, 1, 110, 210),
            CalibratedCell(2, 0, 120, 220),
            CalibratedCell(2, 1, 130, 230),
        ],
        panel_source_cell_numbers=[1, 2, 3, 4],
    )
    detections = [
        PanelUnitDetection("Skeleton", 10, 0.9, panel_index=0),
        PanelUnitDetection("Wight", 20, 0.9, panel_index=1),
        PanelUnitDetection("Archer", 30, 0.9, panel_index=2),
        PanelUnitDetection("Griffin", 40, 0.9, panel_index=3),
    ]
    template = PlacementTemplate(
        name="test",
        units=[
            PlacedUnit("ANY", 1, 0, 1, "any"),
            PlacedUnit("Skeleton", 1, 1, 1, "any"),
            PlacedUnit("ANY", 2, 0, 1, "any"),
            PlacedUnit("Wight", 2, 1, 1, "any"),
        ],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((10, 20), (110, 210), "Skeleton xany -> row 2, col 2"),
        ((30, 40), (130, 230), "Wight xany -> row 3, col 2"),
        ((50, 60), (100, 200), "ANY xany -> row 2, col 1"),
        ((70, 80), (120, 220), "ANY xany -> row 3, col 1"),
    ]


def test_calibrated_plan_pseudo_any_ignores_unknown_units() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(0, 0, 10, 20),
            CalibratedCell(0, 1, 30, 40),
            CalibratedCell(1, 0, 100, 200),
        ],
        panel_source_cell_numbers=[1, 2],
    )
    detections = [
        PanelUnitDetection("unknown", 99, 0.2, panel_index=0),
        PanelUnitDetection("Archer", 30, 0.9, panel_index=1),
    ]
    template = PlacementTemplate(
        name="test",
        units=[PlacedUnit("ANY", 1, 0, 1, "any")],
    )

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert [(action.source, action.target, action.label) for action in plan.actions] == [
        ((30, 40), (100, 200), "ANY xany -> row 2, col 1"),
    ]


def test_calibrated_plan_reports_missing_calibration_and_units() -> None:
    calibration = UnitPlacerCalibration(profile_name="default")
    detections = [PanelUnitDetection("Skeleton", 31, 0.9, panel_index=0)]
    template = PlacementTemplate(name="attack", units=[PlacedUnit("Wight", 0, 0, 1)])

    plan = build_calibrated_move_plan(detections, template, calibration)

    assert plan.actions == []
    assert any("Numbered grid calibration is missing" in message for message in plan.log_messages)
    assert any("Missing detected unit for Wight" in message for message in plan.log_messages)
