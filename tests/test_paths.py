from pathlib import Path
import sys

from oldenera_qol.paths import initialize_user_data, resource_root, user_data_root


def test_initialize_user_data_copies_seed_files_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    target = tmp_path / "user"
    (source / "config").mkdir(parents=True)
    (source / "data").mkdir()
    (source / "profiles").mkdir()
    (source / "assets" / "units").mkdir(parents=True)
    (source / "config" / "settings.toml").write_text("theme = \"dark\"", encoding="utf-8")
    (source / "data" / "units.json").write_text("{}", encoding="utf-8")
    (source / "profiles" / "default.json").write_text("default", encoding="utf-8")
    (source / "assets" / "units" / "unit.png").write_bytes(b"seed")
    (target / "config").mkdir(parents=True)
    (target / "config" / "settings.toml").write_text("theme = \"custom\"", encoding="utf-8")

    initialized = initialize_user_data(source, target)

    assert initialized == target
    assert (target / "config" / "settings.toml").read_text(encoding="utf-8") == "theme = \"custom\""
    assert (target / "data" / "units.json").read_text(encoding="utf-8") == "{}"
    assert (target / "profiles" / "default.json").read_text(encoding="utf-8") == "default"
    assert (target / "assets" / "units" / "unit.png").read_bytes() == b"seed"


def test_frozen_paths_use_bundle_and_appdata(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    appdata = tmp_path / "AppData"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))

    assert resource_root() == bundle.resolve()
    assert user_data_root() == (appdata / "OldenEraQOL").resolve()
