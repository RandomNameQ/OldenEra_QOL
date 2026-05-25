# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()


def collect_tree(source, destination, excluded_parts=()):
    entries = []
    excluded = set(excluded_parts)
    for path in Path(source).rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if excluded.intersection(relative.parts):
            continue
        entries.append((str(path), str(Path(destination) / relative.parent)))
    return entries


datas = [
    (str(project_root / "config" / "settings.toml"), "config"),
    (str(project_root / "data" / "units.json"), "data"),
]
datas += collect_tree(project_root / "assets", "assets")
datas += collect_tree(
    project_root / "profiles",
    "profiles",
    excluded_parts=("unit_panels",),
)

a = Analysis(
    ["src/oldenera_qol/__main__.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "cv2",
        "mss",
        "pytesseract",
        "PIL",
        "pynput",
        "pydirectinput",
        "win32gui",
        "win32process",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OldenEraQOL",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OldenEraQOL",
)
