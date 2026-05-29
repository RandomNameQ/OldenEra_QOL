# Localization Test Plan

## Unit Tests

- Settings default locale is `en`.
- Settings load/save preserves a selected locale.
- Translator returns selected-language messages.
- Translator falls back to English for missing messages.
- Locale normalization handles wiki source folder names and common language codes.
- Unit records load old JSON without localization dictionaries.
- Unit records serialize localized names and factions.

## Import Tests

- Wiki importer merges English, Russian, and French fixture files by `entity.id`.
- Canonical JSON keys remain English names.
- Missing localized values fall back without aborting import.
- Imported icons still copy from wiki assets.

## UI Smoke Tests

- Main window starts with English labels by default.
- Settings page exposes a language selector.
- Overlay actions are built from localized labels.
- Unit Library list items can display localized names while storing canonical names.

## Regression Gates

- Run focused tests after each milestone.
- Run `pytest` before completion.
- Treat profile/template serialization changes as release blockers unless explicitly intended.

## Out Of Scope

- OCR language detection.
- Browser or visual E2E testing for the PySide desktop app.
- Verifying every translated phrase linguistically.

