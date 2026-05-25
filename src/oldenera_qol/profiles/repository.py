from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from oldenera_qol.profiles.models import (
    DestinationSlot,
    QuantityRegion,
    UnitProfile,
    UnitTemplate,
)


class ProfileRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, profile_name: str) -> Path:
        safe_name = "".join(ch for ch in profile_name if ch.isalnum() or ch in ("-", "_"))
        return self.directory / f"{safe_name or 'default'}.json"

    def save(self, profile: UnitProfile) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(profile.profile_name)
        path.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
        return path

    def load(self, profile_name: str) -> UnitProfile:
        path = self.path_for(profile_name)
        data = json.loads(path.read_text(encoding="utf-8"))
        return profile_from_dict(data)

    def list_profiles(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))


def profile_from_dict(data: dict) -> UnitProfile:
    templates = [
        UnitTemplate(
            id=item["id"],
            name=item["name"],
            image_path=item["image_path"],
            match_threshold=float(item["match_threshold"]),
            quantity_region=QuantityRegion(**item["quantity_region"]),
        )
        for item in data.get("templates", [])
    ]
    slots = [
            DestinationSlot(
                id=item["id"],
                unit_template_id=item["unit_template_id"],
                required_quantity=int(item["required_quantity"]),
                target_x=int(item["target_x"]),
                target_y=int(item["target_y"]),
                quantity_mode=str(item.get("quantity_mode", "exact")),
            )
        for item in data.get("slots", [])
    ]
    return UnitProfile(
        profile_name=data.get("profile_name", "default"),
        window_title_hint=data.get("window_title_hint", ""),
        templates=templates,
        slots=slots,
    )
