from __future__ import annotations

from dataclasses import dataclass

from oldenera_qol.vision.capture import WindowBounds


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    bounds: WindowBounds
    process_id: int | None = None


class WindowController:
    def list_windows(self) -> list[WindowInfo]:
        try:
            import win32gui
        except ImportError:
            return []

        windows: list[WindowInfo] = []

        def callback(handle, _extra):
            if not win32gui.IsWindowVisible(handle):
                return
            title = win32gui.GetWindowText(handle)
            if not title.strip():
                return
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            windows.append(
                WindowInfo(
                    handle=handle,
                    title=title,
                    bounds=WindowBounds(left, top, right - left, bottom - top),
                    process_id=self.process_id(handle),
                )
            )

        win32gui.EnumWindows(callback, None)
        return sorted(windows, key=lambda item: item.title.lower())

    def find_by_title_hint(self, title_hint: str) -> WindowInfo | None:
        hint = title_hint.lower().strip()
        for window in self.list_windows():
            if not hint or hint in window.title.lower():
                return window
        return None

    def focus(self, handle: int) -> bool:
        try:
            import win32gui
        except ImportError:
            return False
        try:
            win32gui.SetForegroundWindow(handle)
        except Exception:
            return False
        return True

    def foreground_handle(self) -> int | None:
        try:
            import win32gui
        except ImportError:
            return None
        handle = win32gui.GetForegroundWindow()
        return int(handle) if handle else None

    def process_id(self, handle: int) -> int | None:
        try:
            import win32process
        except ImportError:
            return None
        try:
            _thread_id, process_id = win32process.GetWindowThreadProcessId(handle)
        except Exception:
            return None
        return int(process_id) if process_id else None
