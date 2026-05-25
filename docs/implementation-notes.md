# Implementation Notes

## User Journeys

- As a player, I can select the unit-card panel with a rectangle so the app can scan panel order and stack quantities.
- As a player, I can view the app's left-to-right numbered deployment cells on the selection overlay and repeat that order on the game screen so coordinates stay synchronized.
- As a player, I can run Unit Placer automatically from scanned panel units to numbered placement-template destinations and see why uncertain units were skipped.
- As a player, I can save a unit-card panel image and reuse it later when the game does not expose the realtime unit panel.
- As a player, I can edit global hotkeys inside the app and keep them persisted in `config/settings.toml`.
- As a player, I can import all English wiki units into an editable local unit JSON file.
- As a player, I can arrange imported unit icons on a complete-cell numbered deployment grid, swap occupied cells by dragging, and mark units as max/any quantity.
- As a player, I can save repeated grid conditions as named placement templates, rename them, attach a preview image, and load them from Placement Grid or Unit Placer.

## Tesseract

The app uses `pytesseract`. If Tesseract is not available on `PATH`, set the executable path in Settings.

## Unit Data

Unit data is stored in `data/units.json` as an object keyed by English unit name. The importer reads `E:\Project\OldenEraWiki\data\English\by-faction\*\units\*.json`, copies unit/faction icons into local `assets/` folders, and leaves `visual_3d` empty for later template images.

Placement templates support quantity matching:

- `exact`: detected quantity must equal the configured value.
- `min`: detected quantity must be greater than or equal to the configured value.
- `max`: detected quantity must be less than or equal to the configured value.
- `any`: detected quantity may be any readable number.

Placement templates are stored in `profiles/placement_grid_templates/*.json`. Each template contains a name, optional image path, and its placed units. Unit Placer consumes those template cells through the calibrated numbered grid rather than through separate destination-slot records.

## Unit Placer Design

Unit Placer has one coordinate model for the battlefield: `UnitPlacerCalibration.grid_cells`. Each entry is saved in the order shown by the app's numbered grid. The Cell Map tab and Placement Grid draw the same complete-cell deployment strip. Numbering runs left-to-right across each row, so the user can mirror the app's order while selecting cells on the game screen.

The active runtime flow is:

1. Use **Select Unit Area** to draw a rectangle around the top unit-card panel.
2. Use **Select Grid Cells** to click game cells in the app's numbered order; the overlay shows the reference grid on the right side while selecting.
3. Choose a Placement Grid template.
4. Test Scan or Run.

Panel scanning determines unit names and quantities from the top panel left-to-right. The planner uses panel index as the numbered source-cell index, then finds destination coordinates by matching each placed template unit's row and column against the same calibrated numbered grid. If a source or destination cell was not calibrated, the run logs the missing numbered cell and skips that move.

Saved unit panels are stored separately in `profiles/unit_panels/` as a cropped image plus JSON metadata. Unit Placer can scan either the live unit area or a selected saved panel image. Saved-panel mode keeps the same planner and drag execution path; it only changes where panel detections come from.

## Packaging

Build with:

```powershell
pyinstaller oldenera_qol.spec
```

The EXE bundle includes the default config and assets directory. A local Tesseract install is still recommended unless a future release bundles it explicitly.
