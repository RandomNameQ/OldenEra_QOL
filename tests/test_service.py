from oldenera_qol.modules.unit_placer import service as service_module
from oldenera_qol.modules.unit_placer.service import UnitPlacerService
from oldenera_qol.profiles.models import QuantityRegion, UnitProfile, UnitTemplate
from oldenera_qol.vision.models import Rect, UnitDetection
from oldenera_qol.vision.ocr import OcrResult


class FakeScreenshot:
    def __init__(self) -> None:
        self.crop_boxes = []

    def crop(self, box):
        self.crop_boxes.append(box)
        return f"crop:{box}"


class FakeOcr:
    def read_quantity(self, image):
        return OcrResult(value=64, text="64", confidence=0.98)


def test_unit_placer_service_detects_and_reads_quantity(monkeypatch) -> None:
    def fake_match_template(screenshot, template_path, template_id, threshold):
        return [UnitDetection(template_id, Rect(100, 200, 40, 40), 0.93)]

    monkeypatch.setattr(service_module, "match_template", fake_match_template)
    screenshot = FakeScreenshot()
    profile = UnitProfile(
        profile_name="default",
        templates=[
            UnitTemplate(
                id="archer",
                name="Archer",
                image_path="archer.png",
                match_threshold=0.86,
                quantity_region=QuantityRegion(-18, 34, 36, 18),
            )
        ],
    )
    logs: list[str] = []

    detections = UnitPlacerService(profile, FakeOcr(), logs.append).detect(screenshot)

    assert detections[0].quantity == 64
    assert detections[0].quantity_confidence == 0.98
    assert screenshot.crop_boxes == [(82, 234, 118, 252)]
    assert logs == []


def test_unit_placer_service_logs_ocr_failures(monkeypatch) -> None:
    class EmptyOcr:
        def read_quantity(self, image):
            return OcrResult(value=None, text="", confidence=0.0)

    monkeypatch.setattr(
        service_module,
        "match_template",
        lambda *_args, **_kwargs: [UnitDetection("archer", Rect(0, 0, 40, 40), 0.93)],
    )
    profile = UnitProfile(
        profile_name="default",
        templates=[
            UnitTemplate(
                id="archer",
                name="Archer",
                image_path="archer.png",
                match_threshold=0.86,
                quantity_region=QuantityRegion(0, 0, 10, 10),
            )
        ],
    )
    logs: list[str] = []

    detections = UnitPlacerService(profile, EmptyOcr(), logs.append).detect(FakeScreenshot())

    assert detections[0].quantity is None
    assert "OCR returned no digits" in logs[0]

