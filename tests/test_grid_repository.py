from oldenera_qol.modules.placement_grid.models import PlacedUnit, PlacementTemplate
from oldenera_qol.modules.placement_grid.repository import (
    GridLayoutRepository,
    PlacementTemplateRepository,
)


def test_grid_layout_repository_round_trips_quantity_mode(tmp_path) -> None:
    repository = GridLayoutRepository(tmp_path / "grid.json")

    repository.save([PlacedUnit("Archer", 1, 2, 32, "max")])
    loaded = repository.load()

    assert loaded == [PlacedUnit("Archer", 1, 2, 32, "max")]


def test_grid_layout_repository_loads_legacy_exact_quantity(tmp_path) -> None:
    path = tmp_path / "grid.json"
    path.write_text(
        '{"units":[{"unit_name":"Archer","row":1,"col":2,"quantity":32}]}',
        encoding="utf-8",
    )

    loaded = GridLayoutRepository(path).load()

    assert loaded == [PlacedUnit("Archer", 1, 2, 32, "exact")]


def test_placement_template_repository_saves_lists_and_loads_templates(tmp_path) -> None:
    repository = PlacementTemplateRepository(tmp_path / "templates")
    template = PlacementTemplate(
        name="Castle fight",
        image_path="assets/templates/castle.png",
        units=[PlacedUnit("Archer", 1, 2, 32, "max")],
    )

    repository.save(template)

    assert repository.list_templates() == ["Castle fight"]
    assert repository.load("Castle fight") == template


def test_placement_template_repository_renames_template(tmp_path) -> None:
    repository = PlacementTemplateRepository(tmp_path / "templates")
    repository.save(PlacementTemplate(name="Old", units=[PlacedUnit("Archer", 1, 2)]))

    renamed = repository.rename("Old", "New")

    assert renamed.name == "New"
    assert repository.list_templates() == ["New"]
    assert repository.load("New").units == [PlacedUnit("Archer", 1, 2)]


def test_placement_template_repository_deletes_template(tmp_path) -> None:
    repository = PlacementTemplateRepository(tmp_path / "templates")
    repository.save(PlacementTemplate(name="Old", units=[PlacedUnit("Archer", 1, 2)]))

    repository.delete("Old")

    assert repository.list_templates() == []
