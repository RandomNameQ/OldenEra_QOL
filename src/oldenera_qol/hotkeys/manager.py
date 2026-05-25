from __future__ import annotations

from collections.abc import Callable

from oldenera_qol.config.settings import normalize_hotkey, validate_hotkeys


class HotkeyManager:
    def __init__(self) -> None:
        self._listener = None
        self._bindings: dict[str, Callable[[], None]] = {}

    def register(self, hotkeys: dict[str, str], callbacks: dict[str, Callable[[], None]]) -> list[str]:
        issues = validate_hotkeys(hotkeys)
        if issues:
            return issues
        self.stop()
        self._bindings = {
            _to_pynput(value): callbacks[action]
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


def _to_pynput(hotkey: str) -> str:
    parts = normalize_hotkey(hotkey).split("+")
    converted = []
    for part in parts:
        if len(part) == 1:
            converted.append(part)
        else:
            converted.append(f"<{part}>")
    return "+".join(converted)

