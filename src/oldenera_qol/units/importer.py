from __future__ import annotations

import json
from pathlib import Path
import shutil

from oldenera_qol.units.models import UnitRecord
from oldenera_qol.units.repository import UnitRepository


class WikiUnitImporter:
    def __init__(self, wiki_root: Path, app_root: Path) -> None:
        self.wiki_root = wiki_root
        self.app_root = app_root

    def import_units(self, repository: UnitRepository) -> dict[str, UnitRecord]:
        units: dict[str, UnitRecord] = {}
        unit_paths = sorted(
            (self.wiki_root / "data" / "English" / "by-faction").glob("*/units/*.json")
        )
        for unit_path in unit_paths:
            record = self._record_from_unit_file(unit_path)
            if record is not None:
                units[record.name] = record
        repository.save(units)
        return units

    def _record_from_unit_file(self, unit_path: Path) -> UnitRecord | None:
        data = json.loads(unit_path.read_text(encoding="utf-8"))
        entity = data.get("entity", {})
        name = str(entity.get("localizedName") or entity.get("name") or data.get("name") or "").strip()
        if not name:
            return None
        unit_id = str(entity.get("id") or data.get("id") or unit_path.stem)
        faction_id = str(entity.get("factionId") or data.get("factionId") or "")
        faction = str(entity.get("factionDisplay") or faction_id)
        unit_icon = self._copy_related_image(data, "icon", "assets/units/icons")
        faction_icon = self._copy_related_image(data, "factionIcon", "assets/factions/icons")
        if not faction_icon:
            faction_icon = self._copy_faction_icon(faction_id)
        return UnitRecord(
            name=name,
            unit_id=unit_id,
            icon=unit_icon,
            visual_3d="",
            faction=faction,
            faction_id=faction_id,
            faction_image=faction_icon,
        )

    def _copy_related_image(self, data: dict, kind: str, destination: str) -> str:
        for image in data.get("related", {}).get("images", []):
            if image.get("kind") != kind:
                continue
            local_path = self.wiki_root / str(image.get("localPath", ""))
            if local_path.exists():
                return self._copy_asset(local_path, destination)
        return ""

    def _copy_faction_icon(self, faction_id: str) -> str:
        faction_path = self.wiki_root / "data" / "English" / "by-faction" / faction_id / "_faction.json"
        if not faction_path.exists():
            return ""
        data = json.loads(faction_path.read_text(encoding="utf-8"))
        for image in data.get("related", {}).get("images", []):
            local_path = self.wiki_root / str(image.get("localPath", ""))
            if local_path.exists():
                return self._copy_asset(local_path, "assets/factions/icons")
        return ""

    def _copy_asset(self, source: Path, destination: str) -> str:
        target_dir = self.app_root / destination
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return str(target.relative_to(self.app_root)).replace("\\", "/")
