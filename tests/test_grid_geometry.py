from oldenera_qol.modules.placement_grid.geometry import (
    build_deployment_grid,
    build_hex_grid,
    cell_at_point,
    nearest_cell,
    point_in_hex,
)
from oldenera_qol.modules.placement_grid.layout import move_or_swap_unit, update_unit_at
from oldenera_qol.modules.placement_grid.models import PlacedUnit


def test_build_hex_grid_creates_complete_staggered_grid() -> None:
    cells = build_hex_grid(rows=3, cols=4, radius=20)

    assert len(cells) == 12
    assert cells[0].row == 0
    assert cells[0].col == 0
    assert cells[4].row == 1
    assert cells[4].center_x > cells[0].center_x


def test_build_hex_grid_can_number_top_to_bottom() -> None:
    cells = build_hex_grid(rows=3, cols=2, radius=20, order="column_major")

    assert [(cell.row, cell.col) for cell in cells] == [
        (0, 0),
        (1, 0),
        (2, 0),
        (0, 1),
        (1, 1),
        (2, 1),
    ]


def test_build_deployment_grid_uses_battlefield_staggered_shape() -> None:
    cells = build_deployment_grid(radius=20)

    assert len(cells) == 22
    assert [(cell.row, cell.col) for cell in cells[:4]] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
    assert cells[-1].row == 10
    assert cells[-1].col == 1
    assert max(cell.col for cell in cells) == 1
    assert cells[0].center_x > cells[2].center_x
    assert cells[4].center_x == cells[0].center_x


def test_nearest_cell_snaps_to_closest_hex_center() -> None:
    cells = build_hex_grid(rows=2, cols=2, radius=20)

    cell = nearest_cell(cells, cells[-1].center_x + 2, cells[-1].center_y - 3)

    assert cell == cells[-1]


def test_point_in_hex_accepts_centers_and_rejects_outside_points() -> None:
    cell = build_hex_grid(rows=1, cols=1, radius=20)[0]

    assert point_in_hex(cell, cell.center_x, cell.center_y, radius=20) is True
    assert point_in_hex(cell, cell.center_x, cell.center_y + 20, radius=20) is True
    assert point_in_hex(cell, cell.center_x + 50, cell.center_y, radius=20) is False


def test_cell_at_point_returns_none_outside_hexes() -> None:
    cells = build_hex_grid(rows=1, cols=1, radius=20)

    assert cell_at_point(cells, cells[0].center_x, cells[0].center_y, radius=20) == cells[0]
    assert cell_at_point(cells, cells[0].center_x + 50, cells[0].center_y, radius=20) is None


def test_move_or_swap_unit_swaps_occupied_cells() -> None:
    units = [
        PlacedUnit("Archer", 0, 0, 12),
        PlacedUnit("Griffin", 0, 1, 18),
    ]

    moved, swapped = move_or_swap_unit(units, 0, 0, 0, 1)

    assert swapped is True
    assert moved[0] == PlacedUnit("Archer", 0, 1, 12)
    assert moved[1] == PlacedUnit("Griffin", 0, 0, 18)


def test_update_unit_at_changes_quantity_and_mode() -> None:
    units = [PlacedUnit("Archer", 0, 0, 12)]

    updated = update_unit_at(units, 0, 0, 20, "max")

    assert updated[0].quantity == 20
    assert updated[0].quantity_mode == "max"
    assert updated[0].quantity_label() == "max"
    assert updated[0].matches_quantity(19) is True
    assert updated[0].matches_quantity(21) is False


def test_quantity_modes_support_max_and_any() -> None:
    assert PlacedUnit("Archer", 0, 0, 64, "max").matches_quantity(20) is True
    assert PlacedUnit("Archer", 0, 0, 64, "max").matches_quantity(65) is False
    assert PlacedUnit("Archer", 0, 0, 1, "any").matches_quantity(999) is True
    assert PlacedUnit("Archer", 0, 0, 1, "any").quantity_label() == "any"


def test_deprecated_min_quantity_mode_normalizes_to_exact() -> None:
    unit = PlacedUnit("Archer", 0, 0, 20, "min")

    assert unit.normalized_mode() == "exact"
    assert unit.quantity_label() == "20"
    assert unit.matches_quantity(20) is True
    assert unit.matches_quantity(21) is False
