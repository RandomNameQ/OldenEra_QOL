from __future__ import annotations

import json
from pathlib import Path
import shutil

from oldenera_qol.localization import DEFAULT_LOCALE, supported_locales
from oldenera_qol.units.models import PSEUDO_ANY_UNIT_NAME, UnitRecord, is_pseudo_any_unit_name
from oldenera_qol.units.repository import UnitRepository


class WikiUnitImporter:
    def __init__(self, wiki_root: Path, app_root: Path) -> None:
        self.wiki_root = wiki_root
        self.app_root = app_root

    def import_units(self, repository: UnitRepository) -> dict[str, UnitRecord]:
        existing_units = repository.load()
        existing_by_id = {
            record.unit_id: record
            for record in existing_units.values()
            if record.unit_id
        }
        pseudo_units = {
            name: record
            for name, record in existing_units.items()
            if is_pseudo_any_unit_name(name)
        }
        records_by_id: dict[str, UnitRecord] = {}

        for locale in supported_locales():
            language_root = self.wiki_root / "data" / locale.wiki_language
            if not language_root.exists():
                continue
            unit_paths = sorted((language_root / "by-faction").glob("*/units/*.json"))
            for unit_path in unit_paths:
                fields = self._unit_fields(unit_path)
                if fields is None:
                    continue
                unit_id = fields["unit_id"]
                record = records_by_id.get(unit_id)
                if record is None:
                    existing = existing_by_id.get(unit_id)
                    canonical_name = (
                        fields["name"] if locale.code == DEFAULT_LOCALE else _name_from_id(unit_id)
                    )
                    canonical_faction = (
                        fields["faction"]
                        if locale.code == DEFAULT_LOCALE
                        else fields["faction_id"]
                    )
                    record = UnitRecord(
                        name=canonical_name,
                        unit_id=unit_id,
                        icon=fields["unit_icon"],
                        visual_3d=existing.visual_3d if existing is not None else "",
                        faction=canonical_faction,
                        faction_id=fields["faction_id"],
                        faction_image=fields["faction_icon"],
                    )
                    records_by_id[unit_id] = record
                elif locale.code == DEFAULT_LOCALE:
                    record = UnitRecord(
                        name=fields["name"],
                        unit_id=record.unit_id,
                        icon=fields["unit_icon"] or record.icon,
                        visual_3d=record.visual_3d,
                        faction=fields["faction"],
                        faction_id=fields["faction_id"] or record.faction_id,
                        faction_image=fields["faction_icon"] or record.faction_image,
                        localized_names=dict(record.localized_names),
                        localized_factions=dict(record.localized_factions),
                    )
                    records_by_id[unit_id] = record

                if fields["name"]:
                    record.localized_names[locale.code] = fields["name"]
                if fields["faction"]:
                    record.localized_factions[locale.code] = fields["faction"]

        units = {
            **pseudo_units,
            **{record.name: record for record in records_by_id.values()},
        }
        if PSEUDO_ANY_UNIT_NAME not in units and "any" in existing_by_id:
            units[PSEUDO_ANY_UNIT_NAME] = existing_by_id["any"]
        repository.save(units)
        return units

    def _unit_fields(self, unit_path: Path) -> dict[str, str] | None:
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
        return {
            "name": name,
            "unit_id": unit_id,
            "unit_icon": unit_icon,
            "faction": faction,
            "faction_id": faction_id,
            "faction_icon": faction_icon,
        }

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


def _name_from_id(unit_id: str) -> str:
    return " ".join(part.capitalize() for part in unit_id.split("_") if part) or unit_id
