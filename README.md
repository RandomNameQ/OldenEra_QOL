# OldenEra QOL 0.1

A modular Windows desktop assistant for Olden Era quality-of-life workflows.

The first module, **Unit Placer**, captures the screen, scans a selected top unit-card panel, reads squad quantities with Tesseract OCR, maps panel order onto a user-calibrated numbered battlefield grid, and performs drag-and-drop movement while logging uncertain cases.

Additional setup modules are included:

- **Placement Grid**: a draggable complete-cell deployment hex board with visible left-to-right cell numbers for arranging unit icons, swapping occupied cells, tagging units as max/any quantity, and saving named setup templates with unit icons.
- **Units**: an editable unit database imported from `E:\Project\OldenEraWiki`, keyed by English unit name.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m oldenera_qol
```

Install Tesseract OCR separately and set its path in the app settings if it is not on `PATH`.

## Project Layout

- `src/oldenera_qol/app`: PySide6 shell and screens
- `src/oldenera_qol/config`: TOML settings and hotkeys
- `src/oldenera_qol/hotkeys`: global hotkey manager
- `src/oldenera_qol/modules`: module interface and Unit Placer module
- `src/oldenera_qol/units`: imported unit database, editor models, and wiki importer
- `src/oldenera_qol/vision`: capture, template matching, OCR
- `src/oldenera_qol/automation`: drag execution helpers
- `src/oldenera_qol/profiles`: visual setup profiles

## Unit Data

The unit database lives at `data/units.json`. Each top-level object key is the English unit name. Each record stores:

- `unit_id`
- `icon`
- `visual_3d`
- `faction`
- `faction_id`
- `faction_image`

`visual_3d` starts empty and can be filled from the Units screen when you provide the 3D visual images.

When running from source, settings, profiles, and editable data stay in the project folders. When running the bundled `.exe`, the app seeds its defaults into `%APPDATA%\OldenEraQOL` and reads/writes user data there so updates do not overwrite saved settings or profiles.

## Unit Placer Flow

Unit Placer uses the app's numbered grid as the source of truth. The Cell Map tab and Placement Grid both show the same complete-cell deployment strip, numbered left-to-right across each row. The player clicks cells on the game screen in that order so the saved coordinates match the app's template data. The top unit panel is selected with **Select Unit Area** and scanned left-to-right to determine which units are present. **Save Panel** stores the cropped unit panel under `profiles/unit_panels/` so it can be reused when realtime capture is unavailable. Disable **Realtime unit panel** and select a saved panel to make Test Scan and Move Units scan that saved image instead of the live screen. **Select Grid Cells** displays the same numbered reference grid on the right side of the overlay while the user clicks. Placement templates use the same numbered grid cells as destinations.

## Tests

```powershell
pytest
```

## Build EXE

```powershell
.\build-exe.bat
```

The built executable is written to `dist\OldenEraQOL\OldenEraQOL.exe`.
