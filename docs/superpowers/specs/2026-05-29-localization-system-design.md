# Localization System Design

Date: 2026-05-29

## Goal

Add localization for the OldenEra QOL desktop app so both the program interface and imported game data can be displayed in every language available from `E:\Project\OldenEraWiki`, while English remains the default language and current saved profiles/templates remain compatible.

## Supported Languages

The app will support the same content languages currently present in the wiki data folders:

- English (`en`)
- Russian (`ru`)
- French (`fr`)
- German (`de`)
- Spanish (`es`)
- Czech (`cs`)
- Hungarian (`hu`)
- Japanese (`ja`)
- Korean (`ko`)
- Polish (`pl`)
- Turkish (`tr`)
- Ukrainian (`uk`)
- Chinese Simplified (`zh-cn`)
- Chinese Traditional (`zh-tw`)

English is the default and primary fallback. If a translated value is missing in the selected language, the app displays the English value. If English is also unavailable, it falls back to the stable internal key or existing raw value.

## Architecture

Add a new `oldenera_qol.localization` package with three responsibilities:

1. Define supported locale metadata, fallback order, and normalization from language code or wiki source folder name.
2. Load UI message JSON files from `data/locales/<locale>.json`.
3. Provide a small translator object with helpers for plain keys and formatted messages.

The main window owns the active translator and passes it into panels that need localized labels. Settings persist the selected locale in `config/settings.toml` as `locale = "en"`.

The existing unit repository remains canonical and English-keyed. Internal workflows continue to use existing unit names and `unit_id` values for matching, placement templates, scans, and saved profile data.

## Data Model

Extend `UnitRecord` with localized display fields:

- `localized_names: dict[str, str]`
- `localized_factions: dict[str, str]`

The existing fields remain:

- `name`: canonical English display name used as the JSON object key
- `unit_id`
- `icon`
- `visual_3d`
- `faction`: canonical English faction display name
- `faction_id`
- `faction_image`

Add methods such as `display_name(locale)` and `display_faction(locale)` so UI code does not read the dictionaries directly.

`data/units.json` stays one file. Each record stores translations inline, for example:

```json
{
  "Angel": {
    "unit_id": "angel",
    "icon": "assets/units/icons/angel.png",
    "visual_3d": "",
    "faction": "Temple",
    "faction_id": "human",
    "faction_image": "assets/factions/icons/human_icon.png",
    "localized_names": {
      "en": "Angel",
      "ru": "Ангел",
      "fr": "Ange"
    },
    "localized_factions": {
      "en": "Temple",
      "ru": "Храм",
      "fr": "Temple"
    }
  }
}
```

Older `units.json` files without translation dictionaries remain readable; missing dictionaries are treated as empty and English display falls back to `name` / `faction`.

## Wiki Import

Update `WikiUnitImporter` to scan all supported language folders under `E:\Project\OldenEraWiki\data`.

The importer builds records by stable `entity.id` / file stem, not by localized name. English remains the canonical source for top-level keys, icons, faction IDs, and faction icons. For each language, the importer reads:

- `entity.localizedName`, `entity.name`, or top-level `name` for the unit display name.
- `entity.factionDisplay` or localized faction file name for the faction display name.

If English is missing for a unit but another language has it, the importer may include it under a generated canonical key from the unit ID. That fallback should be logged in the Units panel so missing English source data is visible.

The pseudo `ANY` record is preserved and gains localized display values only where explicitly defined by QOL UI messages; it is not imported from the wiki.

## UI Localization

All user-facing program interface strings should move behind translation keys. This includes:

- Main navigation and page headers.
- Settings labels and language selector.
- Unit Library labels, buttons, logs, and field names.
- Placement Grid labels, buttons, summaries, tooltips, and confirmation dialogs.
- Unit Placer labels, tabs, buttons, summaries, tooltips, readiness text, and logs produced by UI orchestration.
- Overlay action labels and tooltips.

Domain/runtime values such as file names, profile names, template names, hotkey action IDs, and exception text remain unchanged except where they are embedded into localized message templates.

The app should rebuild or refresh visible labels after the language setting changes. A restart is acceptable only if a full dynamic refresh would make the implementation fragile; the settings screen must clearly apply the selected locale for future UI construction either way.

## Unit Display Behavior

Lists and summaries display localized unit/faction names when available:

- Unit Library list and detail panel.
- Placement Grid unit list and selected-unit label.
- Placement template summaries.
- Unit Placer scan previews and detection summaries.

Internal lookups continue to use canonical names. When a UI list item displays a localized name, the item stores the canonical name or unit ID in item data so selection and save operations update the correct record.

Templates and profiles continue to serialize canonical unit names. No migration is required for existing saved data.

## Error Handling

Missing UI message keys return the key in development/test contexts and fall back to English in normal use.

Malformed locale JSON should not prevent the app from launching. The translator logs or exposes a readable error and uses English messages.

Importer errors for one language or one unit should not abort the whole import unless the English canonical import cannot be read at all. Partial import warnings should appear in the Unit data log.

## Testing

Add focused tests for:

- Settings load/save preserves `locale` and defaults to `en`.
- Translator returns selected-language messages and English fallback.
- Unit records deserialize old and new JSON shapes.
- Wiki importer merges translations from at least English, Russian, and French fixture files using stable unit IDs.
- Unit repository still writes JSON keyed by English canonical names.
- UI smoke tests verify the main window starts with English by default and exposes a language selector.

Existing tests for placement templates, scanner planning, and `ANY` should continue to pass without changing serialized profile/template formats.

## Non-Goals

- Translating OCR output or changing the visual matching engine.
- Localizing saved file names, profile IDs, template IDs, or hotkey action IDs.
- Splitting unit data into one file per language.
- Adding online translation services. All localized game data comes from the wiki source, and UI strings are bundled with the app.

