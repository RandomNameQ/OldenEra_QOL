from __future__ import annotations

from math import cos, pi, sin, sqrt

from oldenera_qol.modules.placement_grid.models import GridCell


DEPLOYMENT_GRID_COORDS: tuple[tuple[int, int], ...] = tuple(
    (row, col)
    for row in range(11)
    for col in range(2)
)


def build_deployment_grid(radius: float) -> list[GridCell]:
    return _build_battlefield_deployment_grid(radius)


def build_hex_grid(
    rows: int,
    cols: int,
    radius: float,
    order: str = "row_major",
    include: tuple[tuple[int, int], ...] | None = None,
) -> list[GridCell]:
    cells: list[GridCell] = []
    included_locations = set(include) if include is not None else None
    width = sqrt(3) * radius
    vertical_step = 1.5 * radius
    for row in range(rows):
        x_offset = width / 2 if row % 2 else 0
        for col in range(cols):
            if included_locations is not None and (row, col) not in included_locations:
                continue
            cells.append(
                GridCell(
                    row=row,
                    col=col,
                    center_x=radius + x_offset + col * width,
                    center_y=radius + row * vertical_step,
                )
            )
    if order == "column_major":
        return sorted(cells, key=lambda cell: (cell.col, cell.row))
    if order != "row_major":
        raise ValueError("Grid order must be row_major or column_major")
    return cells


def _build_battlefield_deployment_grid(radius: float) -> list[GridCell]:
    cells: list[GridCell] = []
    width = sqrt(3) * radius
    vertical_step = 1.5 * radius
    for row, col in DEPLOYMENT_GRID_COORDS:
        # The in-game deployment lane starts with the top row shifted right,
        # then alternates left/right as it descends.
        x_offset = width / 2 if row % 2 == 0 else 0
        cells.append(
            GridCell(
                row=row,
                col=col,
                center_x=radius + x_offset + col * width,
                center_y=radius + row * vertical_step,
            )
        )
    return cells


def nearest_cell(cells: list[GridCell], x: float, y: float) -> GridCell:
    if not cells:
        raise ValueError("Cannot snap to an empty grid")
    return min(cells, key=lambda cell: (cell.center_x - x) ** 2 + (cell.center_y - y) ** 2)


def cell_at_point(
    cells: list[GridCell],
    x: float,
    y: float,
    radius: float,
) -> GridCell | None:
    if not cells:
        return None
    cell = nearest_cell(cells, x, y)
    return cell if point_in_hex(cell, x, y, radius) else None


def point_in_hex(cell: GridCell, x: float, y: float, radius: float) -> bool:
    points = [
        (
            cell.center_x + radius * cos(pi / 6 + index * pi / 3),
            cell.center_y + radius * sin(pi / 6 + index * pi / 3),
        )
        for index in range(6)
    ]
    inside = False
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
        if _point_on_segment(x, y, current_x, current_y, previous_x, previous_y):
            return True
        crosses_y = (current_y > y) != (previous_y > y)
        if crosses_y:
            slope_x = (previous_x - current_x) * (y - current_y) / (previous_y - current_y) + current_x
            if x < slope_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _point_on_segment(
    x: float,
    y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> bool:
    epsilon = 1e-7
    cross = (x - start_x) * (end_y - start_y) - (y - start_y) * (end_x - start_x)
    if abs(cross) > epsilon:
        return False
    return (
        min(start_x, end_x) - epsilon <= x <= max(start_x, end_x) + epsilon
        and min(start_y, end_y) - epsilon <= y <= max(start_y, end_y) + epsilon
    )
