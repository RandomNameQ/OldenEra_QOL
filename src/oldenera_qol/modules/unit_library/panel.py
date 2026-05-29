from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from oldenera_qol.app.widgets import LogPanel, make_header
from oldenera_qol.localization import DEFAULT_LOCALE, Translator
from oldenera_qol.units.importer import WikiUnitImporter
from oldenera_qol.units.models import UnitRecord
from oldenera_qol.units.repository import UnitRepository


EDITABLE_FIELDS = {
    "Icon": "icon",
    "3D visual": "visual_3d",
    "Faction": "faction",
    "Faction image": "faction_image",
}


class UnitLibraryPanel(QWidget):
    id = "unit_library"
    name = "Units"

    def __init__(
        self,
        app_root: Path,
        repository: UnitRepository,
        log,
        translator: Translator | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        super().__init__()
        self.app_root = app_root
        self.repository = repository
        self.log = log
        self.translator = translator
        self.locale = locale
        self.units: dict[str, UnitRecord] = {}
        self.selected_unit_name: str | None = None
        self._icon_cache: dict[str, QIcon] = {}
        self._preview_cache: dict[str, QPixmap] = {}

        self.unit_list = QListWidget()
        self.name_value = QLineEdit()
        self.name_value.setReadOnly(True)
        self.unit_id_value = QLineEdit()
        self.faction_value = QLineEdit()
        self.faction_id_value = QLineEdit()
        self.icon_value = QLineEdit()
        self.visual_value = QLineEdit()
        self.faction_image_value = QLineEdit()
        self.field_selector = QComboBox()
        self.field_selector.addItems(EDITABLE_FIELDS.keys())
        self.log_panel = LogPanel()
        self.preview = QLabel()
        self.preview.setMinimumSize(120, 120)

        self._build_layout()
        self.refresh_units()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            make_header(
                self.tr("units.title"),
                self.tr("units.subtitle"),
            )
        )

        toolbar = QHBoxLayout()
        import_button = QPushButton(self.tr("units.importFromWiki"))
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self.import_from_wiki)
        save_button = QPushButton(self.tr("units.saveUnit"))
        save_button.clicked.connect(self.save_current_unit)
        choose_button = QPushButton(self.tr("units.chooseFileForField"))
        choose_button.clicked.connect(self.choose_file_for_selected_field)
        toolbar.addWidget(import_button)
        toolbar.addWidget(save_button)
        toolbar.addWidget(self.field_selector)
        toolbar.addWidget(choose_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        splitter = QSplitter()
        splitter.addWidget(self.unit_list)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        for label, widget in [
            ("Name", self.name_value),
            ("Unit ID", self.unit_id_value),
            ("Faction", self.faction_value),
            ("Faction ID", self.faction_id_value),
            ("Icon", self.icon_value),
            ("3D visual", self.visual_value),
            ("Faction image", self.faction_image_value),
        ]:
            detail_layout.addWidget(QLabel(self._field_label(label)))
            detail_layout.addWidget(widget)
        detail_layout.addWidget(QLabel(self.tr("units.preview")))
        detail_layout.addWidget(self.preview)
        detail_layout.addStretch(1)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        layout.addWidget(QLabel(self.tr("units.log")))
        layout.addWidget(self.log_panel)

        self.unit_list.currentItemChanged.connect(self._unit_selection_changed)

    def refresh_units(self) -> None:
        self.units = self.repository.load()
        self._icon_cache = {}
        self._preview_cache = {}
        self.unit_list.clear()
        for name, record in self.units.items():
            item = QListWidgetItem(record.display_name(self.locale))
            item.setData(Qt.ItemDataRole.UserRole, name)
            if record.display_name(self.locale) != name:
                item.setToolTip(name)
            icon_path = self._absolute_path(record.icon)
            if icon_path.exists():
                item.setIcon(self._icon_for_path(icon_path))
            self.unit_list.addItem(item)
        self.log_panel.append(self.tr("units.loaded", count=len(self.units)))

    def import_from_wiki(self) -> None:
        wiki_root = Path("E:/Project/OldenEraWiki")
        try:
            units = WikiUnitImporter(wiki_root, self.app_root).import_units(self.repository)
        except Exception as exc:
            self.log_panel.append(self.tr("units.importFailed", error=exc))
            return
        self.refresh_units()
        self.log_panel.append(self.tr("units.imported", count=len(units), path=wiki_root))

    def save_current_unit(self) -> None:
        if self.selected_unit_name is None:
            return
        record = UnitRecord(
            name=self.selected_unit_name,
            unit_id=self.unit_id_value.text().strip(),
            icon=self._relative_path(self.icon_value.text().strip()),
            visual_3d=self._relative_path(self.visual_value.text().strip()),
            faction=self.faction_value.text().strip(),
            faction_id=self.faction_id_value.text().strip(),
            faction_image=self._relative_path(self.faction_image_value.text().strip()),
        )
        self.units[self.selected_unit_name] = record
        self.repository.save(self.units)
        self.refresh_units()
        self.log_panel.append(self.tr("units.saved", name=record.display_name(self.locale)))

    def choose_file_for_selected_field(self) -> None:
        if self.selected_unit_name is None:
            return
        field = EDITABLE_FIELDS[self.field_selector.currentText()]
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose {self.field_selector.currentText()}",
            str(self.app_root),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*.*)",
        )
        if not file_path:
            return
        relative = self._relative_path(file_path)
        if field == "icon":
            self.icon_value.setText(relative)
        elif field == "visual_3d":
            self.visual_value.setText(relative)
        elif field == "faction_image":
            self.faction_image_value.setText(relative)
        self.save_current_unit()

    def _unit_selection_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self.selected_unit_name = None
            return
        self.selected_unit_name = str(current.data(Qt.ItemDataRole.UserRole) or current.text())
        record = self.units[self.selected_unit_name]
        self.name_value.setText(record.name)
        self.unit_id_value.setText(record.unit_id)
        self.faction_value.setText(record.faction)
        self.faction_id_value.setText(record.faction_id)
        self.icon_value.setText(record.icon)
        self.visual_value.setText(record.visual_3d)
        self.faction_image_value.setText(record.faction_image)
        self._update_preview(record.icon)

    def _field_label(self, label: str) -> str:
        keys = {
            "Name": "units.name",
            "Unit ID": "units.unitId",
            "Faction": "units.faction",
            "Faction ID": "units.factionId",
            "Icon": "units.icon",
            "3D visual": "units.visual3d",
            "Faction image": "units.factionImage",
        }
        return self.tr(keys[label])

    def tr(self, key: str, **values: object) -> str:
        if self.translator is None:
            return key
        return self.translator.t(key, **values)

    def _update_preview(self, path: str) -> None:
        absolute = self._absolute_path(path)
        if not absolute.exists():
            self.preview.clear()
            return
        cache_key = str(absolute)
        pixmap = self._preview_cache.get(cache_key)
        if pixmap is None:
            pixmap = QPixmap(cache_key).scaled(96, 96)
            self._preview_cache[cache_key] = pixmap
        self.preview.setPixmap(pixmap)

    def _icon_for_path(self, path: Path) -> QIcon:
        cache_key = str(path)
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached
        icon = QIcon(cache_key)
        self._icon_cache[cache_key] = icon
        return icon

    def _absolute_path(self, path: str) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.app_root / candidate

    def _relative_path(self, path: str) -> str:
        if not path:
            return ""
        candidate = Path(path)
        if not candidate.is_absolute():
            return path.replace("\\", "/")
        try:
            return str(candidate.relative_to(self.app_root)).replace("\\", "/")
        except ValueError:
            return str(candidate)
