from oldenera_qol.modules.unit_placer.calibration import (
    CalibratedCell,
    UnitPlacerCalibration,
    UnitPlacerCalibrationRepository,
)
from oldenera_qol.vision.models import Rect


def test_calibration_repository_round_trips_window_relative_cells(tmp_path) -> None:
    repository = UnitPlacerCalibrationRepository(tmp_path)
    calibration = UnitPlacerCalibration(
        profile_name="default",
        panel_scan_rect=Rect(10, 20, 300, 80),
        panel_source_cell_numbers=[3, 5, 7],
        grid_cells=[
            CalibratedCell(row=0, col=0, x=100, y=200),
            CalibratedCell(row=2, col=3, x=400, y=500),
        ],
    )

    repository.save(calibration)
    loaded = repository.load("default")

    assert loaded == calibration


def test_empty_calibration_has_no_numbered_cells(tmp_path) -> None:
    repository = UnitPlacerCalibrationRepository(tmp_path)

    calibration = repository.load("missing")

    assert calibration.profile_name == "missing"
    assert calibration.grid_cells == []
    assert calibration.panel_scan_rect is None


def test_calibration_repository_loads_legacy_target_cells_as_numbered_grid(tmp_path) -> None:
    path = tmp_path / "default.json"
    path.write_text(
        '{"profile_name":"default","source_grid_cells":[{"row":0,"col":0,"x":1,"y":2}],'
        '"target_grid_cells":[{"row":3,"col":4,"x":30,"y":40}]}',
        encoding="utf-8",
    )
    repository = UnitPlacerCalibrationRepository(tmp_path)

    calibration = repository.load("default")

    assert calibration.grid_cells == [CalibratedCell(row=3, col=4, x=30, y=40)]


def test_source_cell_for_panel_index_uses_manual_cell_numbers() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row=0, col=0, x=0, y=0),
            CalibratedCell(row=0, col=1, x=1, y=1),
            CalibratedCell(row=1, col=0, x=2, y=2),
            CalibratedCell(row=1, col=1, x=3, y=3),
            CalibratedCell(row=2, col=0, x=4, y=4),
        ],
        panel_source_cell_numbers=[3, 5],
    )

    assert calibration.source_cell_for_panel_index(0) == CalibratedCell(1, 0, 2, 2)
    assert calibration.source_cell_for_panel_index(1) == CalibratedCell(2, 0, 4, 4)


def test_source_cell_for_panel_index_does_not_guess_when_manual_mapping_is_partial() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row=0, col=0, x=0, y=0),
            CalibratedCell(row=0, col=1, x=1, y=1),
        ],
        panel_source_cell_numbers=[2],
    )

    assert calibration.source_cell_for_panel_index(1) is None


def test_source_cell_for_panel_index_falls_back_to_panel_order() -> None:
    calibration = UnitPlacerCalibration(
        profile_name="default",
        grid_cells=[
            CalibratedCell(row=0, col=0, x=0, y=0),
            CalibratedCell(row=0, col=1, x=1, y=1),
        ],
    )

    assert calibration.source_cell_for_panel_index(1) == CalibratedCell(0, 1, 1, 1)
