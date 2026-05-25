from __future__ import annotations

import json
from pathlib import Path

from oldenera_qol.units.models import UnitRecord


class UnitRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, UnitRecord]:
        if not self.path.exists():
            self.save({})
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            name: UnitRecord.from_json(name, record)
            for name, record in sorted(data.items(), key=lambda item: item[0].lower())
        }

    def save(self, units: dict[str, UnitRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            name: record.to_json()
            for name, record in sorted(units.items(), key=lambda item: item[0].lower())
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert(self, record: UnitRecord) -> None:
        units = self.load()
        units[record.name] = record
        self.save(units)

