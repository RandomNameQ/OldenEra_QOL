from __future__ import annotations

from dataclasses import dataclass, field

QUANTITY_MODES = ("exact", "max", "any")


@dataclass(frozen=True, slots=True)
class GridCell:
    row: int
    col: int
    center_x: float
    center_y: float


@dataclass(frozen=True, slots=True)
class PlacedUnit:
    unit_name: str
    row: int
    col: int
    quantity: int = 1
    quantity_mode: str = "exact"

    def normalized_mode(self) -> str:
        return self.quantity_mode if self.quantity_mode in QUANTITY_MODES else "exact"

    def quantity_label(self) -> str:
        mode = self.normalized_mode()
        if mode == "any":
            return "any"
        if mode == "max":
            return "max"
        return str(self.quantity)

    def matches_quantity(self, detected_quantity: int | None) -> bool:
        mode = self.normalized_mode()
        if mode == "any":
            return detected_quantity is not None
        if detected_quantity is None:
            return False
        if mode == "max":
            return detected_quantity <= self.quantity
        return detected_quantity == self.quantity


@dataclass(frozen=True, slots=True)
class PlacementTemplate:
    name: str
    units: list[PlacedUnit] = field(default_factory=list)
    image_path: str = ""
