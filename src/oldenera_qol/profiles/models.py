from __future__ import annotations

from dataclasses import dataclass, field

QUANTITY_MATCH_MODES = ("exact", "min", "max", "any")


@dataclass(frozen=True, slots=True)
class QuantityRegion:
    x_offset: int
    y_offset: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class UnitTemplate:
    id: str
    name: str
    image_path: str
    match_threshold: float
    quantity_region: QuantityRegion


@dataclass(frozen=True, slots=True)
class DestinationSlot:
    id: str
    unit_template_id: str
    required_quantity: int
    target_x: int
    target_y: int
    quantity_mode: str = "exact"

    def normalized_quantity_mode(self) -> str:
        return self.quantity_mode if self.quantity_mode in QUANTITY_MATCH_MODES else "exact"

    def quantity_label(self) -> str:
        mode = self.normalized_quantity_mode()
        if mode == "any":
            return "any"
        if mode == "min":
            return f"min {self.required_quantity}"
        if mode == "max":
            return f"max {self.required_quantity}"
        return str(self.required_quantity)

    def matches_quantity(self, quantity: int | None) -> bool:
        mode = self.normalized_quantity_mode()
        if mode == "any":
            return quantity is not None
        if quantity is None:
            return False
        if mode == "min":
            return quantity >= self.required_quantity
        if mode == "max":
            return quantity <= self.required_quantity
        return quantity == self.required_quantity


@dataclass(frozen=True, slots=True)
class UnitProfile:
    profile_name: str
    window_title_hint: str = ""
    templates: list[UnitTemplate] = field(default_factory=list)
    slots: list[DestinationSlot] = field(default_factory=list)


def validate_profile(profile: UnitProfile) -> list[str]:
    issues: list[str] = []
    template_ids = {template.id for template in profile.templates}
    if not profile.profile_name.strip():
        issues.append("Profile name is required")
    for template in profile.templates:
        if not template.id.strip():
            issues.append("Template id is required")
        if not 0 < template.match_threshold <= 1:
            issues.append(f"Template {template.id} threshold must be between 0 and 1")
        if template.quantity_region.width <= 0 or template.quantity_region.height <= 0:
            issues.append(f"Template {template.id} quantity region must have positive size")
    for slot in profile.slots:
        if slot.unit_template_id not in template_ids:
            issues.append(f"Slot {slot.id} references missing template {slot.unit_template_id}")
        if slot.required_quantity <= 0:
            issues.append(f"Slot {slot.id} quantity must be positive")
        if slot.quantity_mode not in QUANTITY_MATCH_MODES:
            issues.append(f"Slot {slot.id} quantity mode must be exact, min, max, or any")
    return issues
