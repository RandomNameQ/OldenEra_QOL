from PIL import Image, ImageDraw
import pytest

from oldenera_qol.modules.unit_placer.panel_scanner import (
    PanelUnitScanner,
    _quantity_font,
    _read_quantity_by_cv,
    split_panel_cards,
)
from oldenera_qol.units.repository import UnitRepository
from oldenera_qol.vision.ocr import OcrResult
from oldenera_qol.units.models import UnitRecord


def test_split_panel_cards_returns_stable_left_to_right_regions() -> None:
    image = Image.new("RGB", (75, 20), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 19, 19), fill="gray")
    draw.rectangle((25, 0, 44, 19), fill="gray")
    draw.rectangle((55, 0, 74, 19), fill="gray")

    cards = split_panel_cards(image)

    assert [(card.index, card.rect.x, card.rect.width) for card in cards] == [
        (0, 0, 20),
        (1, 25, 20),
        (2, 55, 20),
    ]


def test_split_panel_cards_can_use_expected_count_for_uniform_game_panel() -> None:
    image = Image.new("RGB", (70, 20), "black")

    cards = split_panel_cards(image, expected_count=7)

    assert len(cards) == 7
    assert cards[0].rect.x == 0
    assert cards[-1].rect.x == 60


def test_split_panel_cards_falls_back_to_uniform_slots_for_continuous_panel() -> None:
    image = Image.new("RGB", (596, 106), "gray")

    cards = split_panel_cards(image)

    assert len(cards) == 7
    assert cards[0].rect.x == 0
    assert cards[-1].rect.x == 510


def test_panel_unit_scanner_reuses_loaded_icon_templates(tmp_path, monkeypatch) -> None:
    import cv2
    import numpy as np

    icon_path = tmp_path / "icon.png"
    icon_path.write_bytes(b"fake")
    scanner = PanelUnitScanner(
        units={
            "Archer": UnitRecord(
                name="Archer",
                unit_id="archer",
                icon="icon.png",
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            )
        },
        app_root=tmp_path,
        ocr=object(),
    )
    read_calls: list[str] = []

    def fake_imread(path, _mode):
        read_calls.append(path)
        return np.ones((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(cv2, "imread", fake_imread)
    monkeypatch.setattr(cv2, "matchTemplate", lambda *_args: np.array([[0.95]], dtype=np.float32))
    monkeypatch.setattr(cv2, "minMaxLoc", lambda result: (0.0, float(result.max()), (0, 0), (0, 0)))

    image = Image.new("RGB", (20, 20), "white")

    first_name, first_score, first_candidates = scanner._match_unit(image)
    second_name, second_score, second_candidates = scanner._match_unit(image)
    assert (first_name, first_score) == ("Archer", pytest.approx(0.95))
    assert (second_name, second_score) == ("Archer", pytest.approx(0.95))
    assert first_candidates[0] == ("Archer", pytest.approx(0.95))
    assert second_candidates[0] == ("Archer", pytest.approx(0.95))
    assert read_calls == [str(icon_path)]


def test_panel_unit_scanner_skips_pseudo_any_icon_templates(tmp_path, monkeypatch) -> None:
    import cv2
    import numpy as np

    archer_icon_path = tmp_path / "archer.png"
    any_icon_path = tmp_path / "any.png"
    archer_icon_path.write_bytes(b"fake")
    any_icon_path.write_bytes(b"fake")
    scanner = PanelUnitScanner(
        units={
            "ANY": UnitRecord(
                name="ANY",
                unit_id="any",
                icon="any.png",
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            ),
            "Archer": UnitRecord(
                name="Archer",
                unit_id="archer",
                icon="archer.png",
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            ),
        },
        app_root=tmp_path,
        ocr=object(),
    )
    read_calls: list[str] = []

    def fake_imread(path, _mode):
        read_calls.append(path)
        return np.ones((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(cv2, "imread", fake_imread)

    templates = scanner._unit_icon_templates()

    assert [name for name, _icon, _mask in templates] == ["Archer"]
    assert read_calls == [str(archer_icon_path)]


def test_panel_unit_scanner_ignores_transparent_icon_backgrounds(tmp_path) -> None:
    icon_path = tmp_path / "icon.png"
    icon = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rectangle((7, 7, 12, 12), fill=(255, 0, 0, 255))
    icon.save(icon_path)
    scanner = PanelUnitScanner(
        units={
            "Archer": UnitRecord(
                name="Archer",
                unit_id="archer",
                icon="icon.png",
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            )
        },
        app_root=tmp_path,
        ocr=object(),
    )

    assert scanner._match_unit(Image.new("RGB", (20, 20), "black"))[0] == "unknown"


def test_panel_unit_scanner_reuses_unchanged_panel_scan(tmp_path, monkeypatch) -> None:
    class FakeOcr:
        def __init__(self) -> None:
            self.calls = 0

        def read_quantity(self, _image):
            self.calls += 1
            return OcrResult(value=12, text="12", confidence=0.9)

    ocr = FakeOcr()
    scanner = PanelUnitScanner(units={}, app_root=tmp_path, ocr=ocr)
    match_calls: list[object] = []

    def fake_match(image):
        match_calls.append(image)
        return ("Archer", 0.95)

    monkeypatch.setattr(scanner, "_match_unit", fake_match)
    image = Image.new("RGB", (40, 20), "white")

    first = scanner.scan_panel_image(image, expected_count=2)
    second = scanner.scan_panel_image(image.copy(), expected_count=2)

    assert first == second
    assert first[0].card_rect is not None
    assert (first[0].card_rect.x, first[0].card_rect.width) == (0, 20)
    assert first[1].card_rect is not None
    assert (first[1].card_rect.x, first[1].card_rect.width) == (20, 20)
    assert len(match_calls) == 2
    assert ocr.calls == 2


def test_panel_unit_scanner_can_treat_unmatched_cards_as_any_without_icon_matching(
    tmp_path,
    monkeypatch,
) -> None:
    class FakeOcr:
        def read_quantity(self, _image):
            return OcrResult(value=42, text="42", confidence=0.9)

    scanner = PanelUnitScanner(
        units={},
        app_root=tmp_path,
        ocr=FakeOcr(),
        use_any_for_unmatched=True,
    )
    monkeypatch.setattr(
        scanner,
        "_match_unit",
        lambda _image: (_ for _ in ()).throw(AssertionError("ANY scan must not match icons")),
    )

    detections = scanner.scan_panel_image(Image.new("RGB", (40, 20), "white"), expected_count=2)

    assert [detection.unit_name for detection in detections] == ["ANY", "ANY"]
    assert [detection.quantity for detection in detections] == [42, 42]


def test_quantity_reader_ignores_top_edge_frame_artifacts() -> None:
    image = Image.new("RGB", (85, 31), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 0, 19, 4), fill="white")
    draw.rectangle((62, 0, 68, 4), fill="white")
    font = _quantity_font(11)
    bbox = draw.textbbox((0, 0), "1", font=font)
    draw.text(
        ((85 - (bbox[2] - bbox[0])) // 2, 9 - bbox[1]),
        "1",
        fill="white",
        font=font,
    )

    result = _read_quantity_by_cv(image)

    assert result.value == 1


def test_panel_unit_scanner_keeps_unit_detection_when_tesseract_is_missing(tmp_path, monkeypatch) -> None:
    class MissingTesseractOcr:
        def read_quantity(self, _image):
            raise RuntimeError("tesseract is not installed or it's not in your PATH")

    scanner = PanelUnitScanner(units={}, app_root=tmp_path, ocr=MissingTesseractOcr())
    monkeypatch.setattr(scanner, "_match_unit", lambda _image: ("Skeleton", 0.95))
    image = Image.new("RGB", (80, 20), "white")

    detections = scanner.scan_panel_image(image, expected_count=2)

    assert [detection.unit_name for detection in detections] == ["Skeleton", "Skeleton"]
    assert [detection.quantity for detection in detections] == [None, None]
    assert all("tesseract" in detection.quantity_text.lower() for detection in detections)


def test_panel_scanner_recognizes_skeleton_example_panel_without_tesseract() -> None:
    class MissingTesseractOcr:
        def read_quantity(self, _image):
            raise RuntimeError("tesseract is not installed or it's not in your PATH")

    image = _skeleton_panel_fixture()
    scanner = PanelUnitScanner(
        units={
            "Skeleton": UnitRecord(
                name="Skeleton",
                unit_id="skeleton",
                icon="assets/units/icons/skeleton.png",
                visual_3d="",
                faction="",
                faction_id="",
                faction_image="",
            )
        },
        app_root=__import__("pathlib").Path.cwd(),
        ocr=MissingTesseractOcr(),
    )

    detections = scanner.scan_panel_image(image)

    assert len(detections) == 7
    assert [detection.unit_name for detection in detections] == ["Skeleton"] * 7
    assert all(detection.confidence >= 0.9 for detection in detections)


def test_panel_scanner_recognizes_skeleton_example_with_full_unit_database() -> None:
    class MissingTesseractOcr:
        def read_quantity(self, _image):
            raise RuntimeError("tesseract is not installed or it's not in your PATH")

    root = __import__("pathlib").Path.cwd()
    scanner = PanelUnitScanner(
        units=UnitRepository(root / "data" / "units.json").load(),
        app_root=root,
        ocr=MissingTesseractOcr(),
    )

    detections = scanner.scan_panel_image(_skeleton_panel_fixture())

    assert len(detections) == 7
    assert [detection.unit_name for detection in detections] == ["Skeleton"] * 7


def test_panel_scanner_recognizes_live_like_skeleton_panel_capture_with_full_unit_database() -> None:
    class MissingTesseractOcr:
        def read_quantity(self, _image):
            raise RuntimeError("tesseract is not installed or it's not in your PATH")

    root = __import__("pathlib").Path.cwd()
    scanner = PanelUnitScanner(
        units=UnitRepository(root / "data" / "units.json").load(),
        app_root=root,
        ocr=MissingTesseractOcr(),
    )

    detections = scanner.scan_panel_image(_live_like_skeleton_panel_fixture(), expected_count=7)

    assert len(detections) == 7
    assert [detection.unit_name for detection in detections] == ["Skeleton"] * 7


def _live_like_skeleton_panel_fixture() -> Image.Image:
    from pathlib import Path

    icon = Image.open(Path.cwd() / "assets" / "units" / "icons" / "skeleton.png").convert("RGBA")
    panel = Image.new("RGB", (600, 98), "#101722")
    draw = ImageDraw.Draw(panel)
    slot_width = 600 // 7
    for index in range(7):
        x = index * slot_width
        right = 600 if index == 6 else x + slot_width
        draw.rounded_rectangle(
            (x + 1, 2, right - 2, 96),
            radius=8,
            fill="#202633",
            outline="#725935",
            width=2,
        )
        draw.rounded_rectangle(
            (x + 7, 8, right - 8, 89),
            radius=7,
            fill="#171b24",
            outline="#313a49",
            width=1,
        )
        portrait = icon.copy()
        portrait.thumbnail((72, 72), Image.Resampling.LANCZOS)
        panel.paste(portrait, (x + (right - x - portrait.width) // 2, 8), portrait)
        quantity = "58" if index == 6 else "1"
        font = _quantity_font(11)
        bbox = draw.textbbox((0, 0), quantity, font=font)
        draw.text(
            (x + (right - x - (bbox[2] - bbox[0])) // 2, 75 - bbox[1]),
            quantity,
            fill="white",
            font=font,
        )
    return panel


def _skeleton_panel_fixture() -> Image.Image:
    from pathlib import Path

    icon = Image.open(Path.cwd() / "assets" / "units" / "icons" / "skeleton.png").convert("RGBA")
    panel = Image.new("RGB", (596, 106), "#101722")
    draw = ImageDraw.Draw(panel)
    slot_width = 596 // 7
    for index in range(7):
        x = index * slot_width
        right = 596 if index == 6 else x + slot_width
        draw.rounded_rectangle(
            (x + 2, 3, right - 3, 102),
            radius=10,
            fill="#202633",
            outline="#725935",
            width=2,
        )
        draw.rounded_rectangle(
            (x + 8, 10, right - 9, 95),
            radius=8,
            fill="#171b24",
            outline="#313a49",
            width=1,
        )
        portrait = icon.copy()
        portrait.thumbnail((52, 68), Image.Resampling.LANCZOS)
        panel.paste(portrait, (x + (right - x - portrait.width) // 2, 17), portrait)
        quantity = "58" if index == 6 else "1"
        font = _quantity_font(10)
        bbox = draw.textbbox((0, 0), quantity, font=font)
        draw.text(
            (x + (right - x - (bbox[2] - bbox[0])) // 2, 78 - bbox[1]),
            quantity,
            fill="white",
            font=font,
        )
    return panel
