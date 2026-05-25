import json
from pathlib import Path

from oldenera_qol.units.importer import WikiUnitImporter
from oldenera_qol.units.models import UnitRecord
from oldenera_qol.units.repository import UnitRepository


def test_unit_repository_uses_unit_name_as_json_object_key(tmp_path: Path) -> None:
    repository = UnitRepository(tmp_path / "units.json")
    repository.save(
        {
            "Archer": UnitRecord(
                name="Archer",
                unit_id="archer",
                icon="assets/units/icons/archer.png",
                visual_3d="",
                faction="Temple",
                faction_id="human",
                faction_image="assets/factions/icons/human_icon.png",
            )
        }
    )

    raw = json.loads((tmp_path / "units.json").read_text(encoding="utf-8"))
    loaded = repository.load()

    assert "Archer" in raw
    assert loaded["Archer"].icon.endswith("archer.png")


def test_wiki_importer_copies_unit_and_faction_icons(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    app = tmp_path / "app"
    unit_icon = wiki / "assets/explorer/Russian/unit/icons/units/hex_portraits/archer.png"
    faction_icon = wiki / "assets/explorer/Russian/faction/icons/fractions/human_icon.png"
    unit_icon.parent.mkdir(parents=True)
    faction_icon.parent.mkdir(parents=True)
    unit_icon.write_bytes(b"unit")
    faction_icon.write_bytes(b"faction")
    unit_json = wiki / "data/English/by-faction/human/units/archer.json"
    unit_json.parent.mkdir(parents=True)
    unit_json.write_text(
        json.dumps(
            {
                "id": "archer",
                "entity": {
                    "id": "archer",
                    "localizedName": "Archer",
                    "factionId": "human",
                    "factionDisplay": "Temple",
                },
                "related": {
                    "images": [
                        {
                            "kind": "icon",
                            "localPath": "assets/explorer/Russian/unit/icons/units/hex_portraits/archer.png",
                        },
                        {
                            "kind": "factionIcon",
                            "localPath": "assets/explorer/Russian/faction/icons/fractions/human_icon.png",
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    repository = UnitRepository(app / "data/units.json")

    units = WikiUnitImporter(wiki, app).import_units(repository)

    assert units["Archer"].faction == "Temple"
    assert (app / units["Archer"].icon).read_bytes() == b"unit"
    assert (app / units["Archer"].faction_image).read_bytes() == b"faction"
    assert units["Archer"].visual_3d == ""

