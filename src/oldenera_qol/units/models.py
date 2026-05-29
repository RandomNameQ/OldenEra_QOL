from __future__ import annotations

from dataclasses import dataclass, field

from oldenera_qol.localization import DEFAULT_LOCALE, normalize_locale

PSEUDO_ANY_UNIT_NAME = "ANY"


def is_pseudo_any_unit_name(unit_name: str) -> bool:
    return unit_name.strip().upper() == PSEUDO_ANY_UNIT_NAME


@dataclass(frozen=True, slots=True)
class UnitRecord:
    name: str
    unit_id: str
    icon: str
    visual_3d: str
    faction: str
    faction_id: str
    faction_image: str
    localized_names: dict[str, str] = field(default_factory=dict)
    localized_factions: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, str]:
        payload = {
            "unit_id": self.unit_id,
            "icon": self.icon,
            "visual_3d": self.visual_3d,
            "faction": self.faction,
            "faction_id": self.faction_id,
            "faction_image": self.faction_image,
        }
        if self.localized_names:
            payload["localized_names"] = dict(sorted(self.localized_names.items()))
        if self.localized_factions:
            payload["localized_factions"] = dict(sorted(self.localized_factions.items()))
        return payload

    def display_name(self, locale: str = DEFAULT_LOCALE) -> str:
        normalized = normalize_locale(locale)
        return (
            self.localized_names.get(normalized)
            or self.localized_names.get(DEFAULT_LOCALE)
            or self.name
        )

    def display_faction(self, locale: str = DEFAULT_LOCALE) -> str:
        normalized = normalize_locale(locale)
        return (
            self.localized_factions.get(normalized)
            or self.localized_factions.get(DEFAULT_LOCALE)
            or self.faction
        )

    @classmethod
    def from_json(cls, name: str, data: dict) -> UnitRecord:
        localized_names = _string_map(data.get("localized_names", {}))
        localized_factions = _string_map(data.get("localized_factions", {}))
        return cls(
            name=name,
            unit_id=str(data.get("unit_id", "")),
            icon=str(data.get("icon", "")),
            visual_3d=str(data.get("visual_3d", "")),
            faction=str(data.get("faction", "")),
            faction_id=str(data.get("faction_id", "")),
            faction_image=str(data.get("faction_image", "")),
            localized_names=localized_names,
            localized_factions=localized_factions,
        )


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        text = str(item).strip()
        if text:
            result[normalize_locale(str(key))] = text
    return result
