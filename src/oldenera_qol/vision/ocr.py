from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OcrResult:
    value: int | None
    text: str
    confidence: float


class QuantityOcr:
    def __init__(self, tesseract_cmd: str = "") -> None:
        self.tesseract_cmd = tesseract_cmd
        self._tesseract_unavailable_message = ""

    def read_quantity(self, image) -> OcrResult:
        if self._tesseract_unavailable_message:
            return OcrResult(
                value=None,
                text=self._tesseract_unavailable_message,
                confidence=0.0,
            )

        try:
            import cv2
            import numpy as np
            import pytesseract
        except ImportError as exc:  # pragma: no cover - exercised in real environment
            raise RuntimeError("OpenCV, NumPy, and pytesseract are required for OCR") from exc

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        source = np.array(image)
        if source.ndim == 3:
            source = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
        scaled = cv2.resize(source, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, thresholded = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        config = "--psm 7 -c tessedit_char_whitelist=0123456789"
        try:
            data = pytesseract.image_to_data(
                thresholded,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            if is_tesseract_unavailable_error(exc):
                self._tesseract_unavailable_message = _ocr_unavailable_text(exc)
                return OcrResult(
                    value=None,
                    text=self._tesseract_unavailable_message,
                    confidence=0.0,
                )
            raise
        candidates = [
            (text.strip(), float(conf))
            for text, conf in zip(data.get("text", []), data.get("conf", []))
            if text.strip().isdigit() and float(conf) >= 0
        ]
        if not candidates:
            return OcrResult(value=None, text="", confidence=0.0)
        text, confidence = max(candidates, key=lambda item: item[1])
        return OcrResult(value=int(text), text=text, confidence=confidence / 100.0)


def is_tesseract_unavailable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        exc.__class__.__name__ == "TesseractNotFoundError"
        or isinstance(exc, FileNotFoundError)
        or "tesseract is not installed" in message
        or "not in your path" in message
    )


def _ocr_unavailable_text(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else "Tesseract OCR is unavailable"
