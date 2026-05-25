from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnitRecord:
    name: str
    unit_id: str
    icon: str
    visual_3d: str
    faction: str
    faction_id: str
    faction_image: str

    def to_json(self) -> dict[str, str]:
        return {
            "unit_id": self.unit_id,
            "icon": self.icon,
            "visual_3d": self.visual_3d,
            "faction": self.faction,
            "faction_id": self.faction_id,
            "faction_image": self.faction_image,
        }

    @classmethod
    def from_json(cls, name: str, data: dict) -> UnitRecord:
        return cls(
            name=name,
            unit_id=str(data.get("unit_id", "")),
            icon=str(data.get("icon", "")),
            visual_3d=str(data.get("visual_3d", "")),
            faction=str(data.get("faction", "")),
            faction_id=str(data.get("faction_id", "")),
            faction_image=str(data.get("faction_image", "")),
        )

