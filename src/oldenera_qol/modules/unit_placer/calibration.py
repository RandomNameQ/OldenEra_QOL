from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from oldenera_qol.vision.models import Rect


@dataclass(frozen=True, slots=True)
class CalibratedCell:
    row: int
    col: int
    x: int
    y: int

    @property
    def point(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True, slots=True)
class UnitPlacerCalibration:
    profile_name: str
    panel_scan_rect: Rect | None = None
    grid_cells: list[CalibratedCell] = field(default_factory=list)
    panel_source_cell_numbers: list[int] = field(default_factory=list)

    def cell_at(self, row: int, col: int) -> CalibratedCell | None:
        return next(
            (cell for cell in self.grid_cells if cell.row == row and cell.col == col),
            None,
        )

    def source_cell_for_panel_index(self, panel_index: int) -> CalibratedCell | None:
        if self.panel_source_cell_numbers:
            if not 0 <= panel_index < len(self.panel_source_cell_numbers):
                return None
            cell_number = self.panel_source_cell_numbers[panel_index]
            if 1 <= cell_number <= len(self.grid_cells):
                return self.grid_cells[cell_number - 1]
            return None
        if 0 <= panel_index < len(self.grid_cells):
            return self.grid_cells[panel_index]
        return None


class UnitPlacerCalibrationRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load(self, profile_name: str) -> UnitPlacerCalibration:
        path = self.path_for(profile_name)
        if not path.exists():
            return UnitPlacerCalibration(profile_name=profile_name)
        data = json.loads(path.read_text(encoding="utf-8"))
        panel_data = data.get("panel_scan_rect")
        return UnitPlacerCalibration(
            profile_name=str(data.get("profile_name") or profile_name),
            panel_scan_rect=Rect(**panel_data) if panel_data else None,
            grid_cells=_load_cells(data),
            panel_source_cell_numbers=[
                int(value)
                for value in data.get("panel_source_cell_numbers", [])
            ],
        )

    def save(self, calibration: UnitPlacerCalibration) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(calibration.profile_name)
        path.write_text(json.dumps(asdict(calibration), indent=2), encoding="utf-8")
        return path

    def path_for(self, profile_name: str) -> Path:
        safe_name = "".join(ch for ch in profile_name if ch.isalnum() or ch in ("-", "_"))
        return self.directory / f"{safe_name or 'default'}.json"


def _cells_from_data(items: list[dict]) -> list[CalibratedCell]:
    return [
        CalibratedCell(
            row=int(item["row"]),
            col=int(item["col"]),
            x=int(item["x"]),
            y=int(item["y"]),
        )
        for item in items
    ]


def _load_cells(data: dict) -> list[CalibratedCell]:
    if "grid_cells" in data:
        return _cells_from_data(data.get("grid_cells", []))
    return _cells_from_data(data.get("target_grid_cells", []))
