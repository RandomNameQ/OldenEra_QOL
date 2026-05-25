from __future__ import annotations

from dataclasses import replace

from oldenera_qol.modules.placement_grid.models import PlacedUnit


def move_or_swap_unit(
    units: list[PlacedUnit],
    source_row: int,
    source_col: int,
    target_row: int,
    target_col: int,
) -> tuple[list[PlacedUnit], bool]:
    source = _find_at(units, source_row, source_col)
    if source is None:
        return units, False
    if source_row == target_row and source_col == target_col:
        return units, False

    target = _find_at(units, target_row, target_col)
    moved = replace(source, row=target_row, col=target_col)
    result: list[PlacedUnit] = []
    for unit in units:
        if unit.row == source_row and unit.col == source_col:
            result.append(moved)
        elif target is not None and unit.row == target_row and unit.col == target_col:
            result.append(replace(unit, row=source_row, col=source_col))
        else:
            result.append(unit)
    return result, target is not None


def update_unit_at(
    units: list[PlacedUnit],
    row: int,
    col: int,
    quantity: int,
    quantity_mode: str,
) -> list[PlacedUnit]:
    return [
        replace(unit, quantity=quantity, quantity_mode=quantity_mode)
        if unit.row == row and unit.col == col
        else unit
        for unit in units
    ]


def _find_at(units: list[PlacedUnit], row: int, col: int) -> PlacedUnit | None:
    return next((unit for unit in units if unit.row == row and unit.col == col), None)
