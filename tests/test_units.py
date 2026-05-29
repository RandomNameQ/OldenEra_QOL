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
    assert loaded["Archer"].display_name("ru") == "Archer"


def test_unit_repository_round_trips_localized_unit_fields(tmp_path: Path) -> None:
    repository = UnitRepository(tmp_path / "units.json")
    repository.save(
        {
            "Angel": UnitRecord(
                name="Angel",
                unit_id="angel",
                icon="assets/units/icons/angel.png",
                visual_3d="",
                faction="Temple",
                faction_id="human",
                faction_image="assets/factions/icons/human_icon.png",
                localized_names={"en": "Angel", "ru": "Ангел", "fr": "Ange"},
                localized_factions={"en": "Temple", "ru": "Храм", "fr": "Temple"},
            )
        }
    )

    raw = json.loads((tmp_path / "units.json").read_text(encoding="utf-8"))
    loaded = repository.load()["Angel"]

    assert raw["Angel"]["localized_names"]["ru"] == "Ангел"
    assert loaded.display_name("fr") == "Ange"
    assert loaded.display_faction("ru") == "Храм"


def test_default_unit_data_includes_any_pseudo_unit() -> None:
    root = Path.cwd()
    units = UnitRepository(root / "data" / "units.json").load()

    assert units["ANY"].unit_id == "any"
    assert (root / units["ANY"].icon).exists()


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


def test_wiki_importer_merges_localized_unit_names_by_unit_id(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    app = tmp_path / "app"
    unit_icon = wiki / "assets/explorer/Russian/unit/icons/units/hex_portraits/angel.png"
    faction_icon = wiki / "assets/explorer/Russian/faction/icons/fractions/human_icon.png"
    unit_icon.parent.mkdir(parents=True)
    faction_icon.parent.mkdir(parents=True)
    unit_icon.write_bytes(b"unit")
    faction_icon.write_bytes(b"faction")

    def write_unit(language: str, name: str, faction: str) -> None:
        unit_json = wiki / f"data/{language}/by-faction/human/units/angel.json"
        unit_json.parent.mkdir(parents=True, exist_ok=True)
        unit_json.write_text(
            json.dumps(
                {
                    "id": "angel",
                    "entity": {
                        "id": "angel",
                        "localizedName": name,
                        "factionId": "human",
                        "factionDisplay": faction,
                    },
                    "related": {
                        "images": [
                            {
                                "kind": "icon",
                                "localPath": "assets/explorer/Russian/unit/icons/units/hex_portraits/angel.png",
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

    write_unit("English", "Angel", "Temple")
    write_unit("Russian", "Ангел", "Храм")
    write_unit("French", "Ange", "Temple")
    repository = UnitRepository(app / "data/units.json")

    units = WikiUnitImporter(wiki, app).import_units(repository)

    assert list(units) == ["Angel"]
    assert units["Angel"].display_name("ru") == "Ангел"
    assert units["Angel"].display_name("fr") == "Ange"
    assert units["Angel"].display_faction("ru") == "Храм"
