from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


APP_DIR_NAME = "OldenEraQOL"
SEED_DIRECTORIES = ("config", "data", "profiles", "assets")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[2]


def user_data_root() -> Path:
    override = os.environ.get("OLDENERA_QOL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if not is_frozen():
        return resource_root()
    base = os.environ.get("APPDATA")
    if base:
        return (Path(base) / APP_DIR_NAME).resolve()
    return (Path.home() / "AppData" / "Roaming" / APP_DIR_NAME).resolve()


def initialize_user_data(source_root: Path | None = None, target_root: Path | None = None) -> Path:
    source = source_root or resource_root()
    target = target_root or user_data_root()
    target.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return target
    for directory in SEED_DIRECTORIES:
        _copy_missing(source / directory, target / directory)
    return target


def _copy_missing(source: Path, target: Path) -> None:
    if source.is_file():
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return
    if not source.is_dir():
        return
    for path in source.rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(source)
        destination = target / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
