from __future__ import annotations

from collections.abc import Callable

from oldenera_qol.config.settings import normalize_hotkey, validate_hotkeys

try:
    from PySide6.QtCore import QObject, Qt, Signal
except ImportError:  # pragma: no cover - app runtime includes PySide6
    QObject = None
    Qt = None
    Signal = None


if QObject is not None and Signal is not None:

    class _HotkeyDispatcher(QObject):
        triggered = Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.triggered.connect(self._run, Qt.ConnectionType.QueuedConnection)

        def _run(self, callback: Callable[[], None]) -> None:
            callback()

else:
    _HotkeyDispatcher = None


class HotkeyManager:
    def __init__(self) -> None:
        self._listener = None
        self._bindings: dict[str, Callable[[], None]] = {}
        self._dispatcher = _HotkeyDispatcher() if _HotkeyDispatcher is not None else None

    def register(self, hotkeys: dict[str, str], callbacks: dict[str, Callable[[], None]]) -> list[str]:
        issues = validate_hotkeys(hotkeys)
        if issues:
            return issues
        self.stop()
        self._bindings = {
            _to_pynput(value): self._queued_callback(callbacks[action])
            for action, value in hotkeys.items()
            if action in callbacks
        }
        try:
            from pynput import keyboard
        except ImportError:
            return ["pynput is not installed; global hotkeys are disabled"]
        self._listener = keyboard.GlobalHotKeys(self._bindings)
        self._listener.start()
        return []

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _queued_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        if self._dispatcher is None:
            return callback

        def invoke() -> None:
            self._dispatcher.triggered.emit(callback)

        return invoke


def _to_pynput(hotkey: str) -> str:
    parts = normalize_hotkey(hotkey).split("+")
    converted = []
    for part in parts:
        if len(part) == 1:
            converted.append(part)
        else:
            converted.append(f"<{part}>")
    return "+".join(converted)
