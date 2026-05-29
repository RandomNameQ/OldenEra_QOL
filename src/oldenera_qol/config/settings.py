from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from oldenera_qol.localization import DEFAULT_LOCALE, normalize_locale


DEFAULT_HOTKEYS = {
    "start_unit_placer": "ctrl+alt+f1",
    "stop_all": "ctrl+alt+esc",
    "capture_window": "ctrl+alt+w",
}


@dataclass(slots=True)
class AutomationSettings:
    move_duration_seconds: float = 0.18
    pause_between_moves_seconds: float = 0.12
    drag_button: str = "left"


@dataclass(slots=True)
class AppSettings:
    theme: str = "dark"
    locale: str = DEFAULT_LOCALE
    tesseract_cmd: str = ""
    active_profile: str = "default"
    last_placement_template: str = ""
    last_unit_panel: str = ""
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    automation: AutomationSettings = field(default_factory=AutomationSettings)


def validate_hotkeys(hotkeys: dict[str, str]) -> list[str]:
    issues: list[str] = []
    normalized: dict[str, str] = {}
    for action, value in hotkeys.items():
        key = normalize_hotkey(value)
        if not key:
            issues.append(f"{action} has an empty hotkey")
            continue
        if key in normalized:
            issues.append(f"{action} duplicates {normalized[key]} ({key})")
        normalized[key] = action
    return issues


def normalize_hotkey(value: str) -> str:
    return "+".join(part.strip().lower() for part in value.split("+") if part.strip())


class SettingsService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        if not self.path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        with self.path.open("rb") as handle:
            data = tomllib.load(handle)

        automation = data.get("automation", {})
        return AppSettings(
            theme=str(data.get("theme", "dark")),
            locale=normalize_locale(str(data.get("locale", DEFAULT_LOCALE))),
            tesseract_cmd=str(data.get("tesseract_cmd", "")),
            active_profile=str(data.get("active_profile", "default")),
            last_placement_template=str(data.get("last_placement_template", "")),
            last_unit_panel=str(data.get("last_unit_panel", "")),
            hotkeys={**DEFAULT_HOTKEYS, **data.get("hotkeys", {})},
            automation=AutomationSettings(
                move_duration_seconds=float(automation.get("move_duration_seconds", 0.18)),
                pause_between_moves_seconds=float(
                    automation.get("pause_between_moves_seconds", 0.12)
                ),
                drag_button=str(automation.get("drag_button", "left")),
            ),
        )

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = [
            f'theme = "{settings.theme}"',
            f'locale = "{normalize_locale(settings.locale)}"',
            f'tesseract_cmd = "{settings.tesseract_cmd}"',
            f'active_profile = "{settings.active_profile}"',
            f'last_placement_template = "{settings.last_placement_template}"',
            f'last_unit_panel = "{settings.last_unit_panel}"',
            "",
            "[hotkeys]",
        ]
        for action, value in settings.hotkeys.items():
            content.append(f'{action} = "{value}"')
        content.extend(
            [
                "",
                "[automation]",
                f"move_duration_seconds = {settings.automation.move_duration_seconds}",
                f"pause_between_moves_seconds = {settings.automation.pause_between_moves_seconds}",
                f'drag_button = "{settings.automation.drag_button}"',
                "",
            ]
        )
        self.path.write_text("\n".join(content), encoding="utf-8")
