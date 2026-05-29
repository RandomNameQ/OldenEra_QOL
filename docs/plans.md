# Localization Execution Plan

Source spec: `docs/superpowers/specs/2026-05-29-localization-system-design.md`

## Assumptions

- English remains the default locale and primary fallback.
- Existing placement templates, profiles, and scanner internals keep using canonical English unit names.
- Wiki data at `E:\Project\OldenEraWiki\data` is available during manual import, but tests use local fixtures.

## Milestone 1: Settings And Translator

Status: `[x]`

Goal: Persist the selected locale and provide a reusable translation loader with English fallback.

Tasks:
- Add locale metadata and normalization.
- Add bundled UI message files for every supported language.
- Add `locale` to settings load/save with default `en`.

Done when:
- Locale settings survive round trips.
- Missing messages fall back to English.

Validation:
- `pytest tests/test_settings.py tests/test_localization.py`

Stop-and-fix rule:
- If settings compatibility breaks for existing TOML files, fix that before moving on.

## Milestone 2: Localized Unit Data

Status: `[x]`

Goal: Merge localized unit and faction names from every supported wiki language without changing canonical keys.

Tasks:
- Extend `UnitRecord` for localized display names.
- Keep old `units.json` shapes readable.
- Update wiki importer to merge language folders by stable unit ID.

Done when:
- Repository output stays English-keyed.
- Importer fixtures merge English, Russian, and French translations.

Validation:
- `pytest tests/test_units.py`

Stop-and-fix rule:
- If old unit JSON cannot load, repair compatibility immediately.

## Milestone 3: UI Integration

Status: `[x]`

Goal: Surface the active locale in the app interface and display localized unit names where safe.

Tasks:
- Add language selector to settings.
- Localize main navigation, headers, overlay action labels, and high-traffic module labels.
- Store canonical unit names in item data when list text is localized.

Done when:
- Main window starts in English by default.
- Unit Library and Placement Grid show localized names but save canonical names.

Validation:
- `pytest tests/test_main_window.py tests/test_unit_placer_panel.py tests/test_placement_grid_panel.py`

Stop-and-fix rule:
- If UI display changes break canonical template/profile serialization, stop and fix before broadening labels.

## Milestone 4: Full Regression

Status: `[x]`

Goal: Verify localization does not regress automation, scanning, or existing tests.

Tasks:
- Run the full test suite.
- Fix failures caused by the localization change.
- Update docs if command behavior changes.

Done when:
- Full test suite passes or any external/environmental failures are documented.

Validation:
- `pytest`

Stop-and-fix rule:
- Do not mark complete with unexplained localization-related failures.
