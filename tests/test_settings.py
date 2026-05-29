from pathlib import Path

from oldenera_qol.config.settings import AppSettings, SettingsService, validate_hotkeys


def test_settings_service_creates_default_file(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / "settings.toml")

    settings = service.load()

    assert settings.hotkeys["start_unit_placer"] == "ctrl+alt+f1"
    assert settings.locale == "en"
    assert (tmp_path / "settings.toml").exists()


def test_settings_service_round_trips_hotkey_changes(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / "settings.toml")
    settings = AppSettings()
    settings.hotkeys["start_unit_placer"] = "ctrl+shift+u"
    settings.last_unit_panel = "unit-panel-20260525-120000"
    settings.locale = "ru"

    service.save(settings)
    loaded = service.load()

    assert loaded.hotkeys["start_unit_placer"] == "ctrl+shift+u"
    assert loaded.last_unit_panel == "unit-panel-20260525-120000"
    assert loaded.locale == "ru"


def test_validate_hotkeys_rejects_duplicates() -> None:
    issues = validate_hotkeys({"start": "ctrl+alt+a", "stop": "CTRL + ALT + A"})

    assert issues
    assert "duplicates" in issues[0]
