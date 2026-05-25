from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowBounds:
    left: int
    top: int
    width: int
    height: int

    def relative_to_screen(self, point: tuple[int, int]) -> tuple[int, int]:
        return (self.left + point[0], self.top + point[1])

    def screen_to_relative(self, point: tuple[int, int]) -> tuple[int, int]:
        return (point[0] - self.left, point[1] - self.top)


class ScreenCapture:
    def capture_window(self, bounds: WindowBounds):
        try:
            import mss
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - exercised in real environment
            raise RuntimeError("mss and Pillow are required for screen capture") from exc

        monitor = {
            "left": bounds.left,
            "top": bounds.top,
            "width": bounds.width,
            "height": bounds.height,
        }
        with mss.mss() as capture:
            raw = capture.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.rgb)

