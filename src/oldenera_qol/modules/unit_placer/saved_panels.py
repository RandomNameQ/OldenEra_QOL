from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path

from PIL import Image


@dataclass(frozen=True, slots=True)
class SavedUnitPanel:
    name: str
    image_path: str
    created_at: str
    scan_summary: list[dict] = field(default_factory=list)


class SavedUnitPanelRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.images_directory = directory / "images"

    def list_panels(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def load(self, name: str) -> SavedUnitPanel:
        path = self.path_for(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        return SavedUnitPanel(
            name=str(data.get("name") or name),
            image_path=str(data.get("image_path", "")),
            created_at=str(data.get("created_at", "")),
            scan_summary=list(data.get("scan_summary", [])),
        )

    def save_image(
        self,
        image: Image.Image,
        name: str | None = None,
        scan_summary: list[dict] | None = None,
    ) -> SavedUnitPanel:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.images_directory.mkdir(parents=True, exist_ok=True)
        panel_name = self._unique_name(name or self._timestamp_name())
        image_path = self.images_directory / f"{panel_name}.png"
        image.save(image_path)
        panel = SavedUnitPanel(
            name=panel_name,
            image_path=str(image_path.relative_to(self.directory)),
            created_at=datetime.now().isoformat(timespec="seconds"),
            scan_summary=list(scan_summary or []),
        )
        self.save(panel)
        return panel

    def save(self, panel: SavedUnitPanel) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(panel.name)
        path.write_text(json.dumps(asdict(panel), indent=2), encoding="utf-8")
        return path

    def delete(self, name: str) -> None:
        path = self.path_for(name)
        image_path = None
        if path.exists():
            try:
                image_path = self.image_path(self.load(name))
            except (OSError, json.JSONDecodeError, ValueError):
                image_path = None
            path.unlink()
        if image_path is not None and image_path.exists():
            image_path.unlink()

    def path_for(self, name: str) -> Path:
        return self.directory / f"{self._safe_name(name) or 'unit-panel'}.json"

    def image_path(self, panel: SavedUnitPanel) -> Path:
        candidate = Path(panel.image_path)
        return candidate if candidate.is_absolute() else self.directory / candidate

    def _unique_name(self, name: str) -> str:
        base_name = self._safe_name(name) or self._timestamp_name()
        candidate = base_name
        suffix = 2
        while self.path_for(candidate).exists():
            candidate = f"{base_name}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _timestamp_name() -> str:
        return f"unit-panel-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    @staticmethod
    def _safe_name(name: str) -> str:
        return "".join(
            ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_", " ")
        ).strip()
