from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from oldenera_qol.modules.placement_grid.models import PlacedUnit, PlacementTemplate


class GridLayoutRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[PlacedUnit]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [
            PlacedUnit(
                unit_name=item["unit_name"],
                row=int(item["row"]),
                col=int(item["col"]),
                quantity=int(item.get("quantity", 1)),
                quantity_mode=str(item.get("quantity_mode", "exact")),
            )
            for item in data.get("units", [])
        ]

    def save(self, units: list[PlacedUnit]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"units": [asdict(unit) for unit in units]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class PlacementTemplateRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list_templates(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def load(self, name: str) -> PlacementTemplate:
        path = self.path_for(name)
        if not path.exists():
            template = PlacementTemplate(name=name)
            self.save(template)
            return template
        data = json.loads(path.read_text(encoding="utf-8"))
        return PlacementTemplate(
            name=str(data.get("name") or name),
            image_path=str(data.get("image_path", "")),
            units=[
                PlacedUnit(
                    unit_name=item["unit_name"],
                    row=int(item["row"]),
                    col=int(item["col"]),
                    quantity=int(item.get("quantity", 1)),
                    quantity_mode=str(item.get("quantity_mode", "exact")),
                )
                for item in data.get("units", [])
            ],
        )

    def save(self, template: PlacementTemplate) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(template.name)
        payload = {
            "name": template.name,
            "image_path": template.image_path,
            "units": [asdict(unit) for unit in template.units],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def rename(self, old_name: str, new_name: str) -> PlacementTemplate:
        template = self.load(old_name)
        renamed = PlacementTemplate(
            name=new_name,
            image_path=template.image_path,
            units=template.units,
        )
        old_path = self.path_for(old_name)
        self.save(renamed)
        if old_path.exists() and old_path != self.path_for(new_name):
            old_path.unlink()
        return renamed

    def delete(self, name: str) -> None:
        path = self.path_for(name)
        if path.exists():
            path.unlink()

    def path_for(self, name: str) -> Path:
        safe_name = "".join(
            ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_", " ")
        ).strip()
        return self.directory / f"{safe_name or 'default'}.json"
