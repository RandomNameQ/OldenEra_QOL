from __future__ import annotations

from pathlib import Path

from PIL import Image

from oldenera_qol.modules.unit_placer.saved_panels import SavedUnitPanelRepository


def test_saved_unit_panel_repository_saves_lists_loads_and_deletes(tmp_path: Path) -> None:
    repository = SavedUnitPanelRepository(tmp_path / "unit_panels")
    image = Image.new("RGB", (280, 80), "black")

    panel = repository.save_image(image)

    assert panel.name.startswith("unit-panel-")
    assert repository.image_path(panel).exists()
    assert repository.list_panels() == [panel.name]

    loaded = repository.load(panel.name)
    assert loaded.name == panel.name
    assert loaded.image_path == panel.image_path
    assert loaded.created_at

    repository.delete(panel.name)

    assert repository.list_panels() == []
    assert not repository.path_for(panel.name).exists()
    assert not repository.image_path(panel).exists()


def test_saved_unit_panel_repository_sanitizes_and_uniquifies_names(tmp_path: Path) -> None:
    repository = SavedUnitPanelRepository(tmp_path / "unit_panels")
    image = Image.new("RGB", (20, 10), "black")

    first = repository.save_image(image, name="Panel: A/B")
    second = repository.save_image(image, name="Panel: A/B")

    assert first.name == "Panel AB"
    assert second.name == "Panel AB-2"
    assert repository.list_panels() == ["Panel AB", "Panel AB-2"]
