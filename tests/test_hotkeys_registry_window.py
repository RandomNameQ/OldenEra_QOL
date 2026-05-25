from types import SimpleNamespace

from oldenera_qol.automation.window import WindowController
from oldenera_qol.hotkeys.manager import HotkeyManager, _to_pynput
from oldenera_qol.modules.registry import ModuleRegistry


def test_hotkey_conversion_uses_pynput_modifier_format() -> None:
    assert _to_pynput("ctrl+alt+f1") == "<ctrl>+<alt>+<f1>"
    assert _to_pynput("ctrl+x") == "<ctrl>+x"


def test_hotkey_manager_returns_validation_issues_for_duplicates() -> None:
    manager = HotkeyManager()

    issues = manager.register({"start": "ctrl+a", "stop": "ctrl+a"}, {})

    assert issues
    assert "duplicates" in issues[0]


def test_module_registry_registers_and_retrieves_module() -> None:
    module = SimpleNamespace(id="unit_placer", name="Unit Placer")
    registry = ModuleRegistry()

    registry.register(module)

    assert registry.get("unit_placer") is module
    assert registry.all() == [module]


def test_window_controller_lists_visible_titled_windows(monkeypatch) -> None:
    focused = []

    def enum_windows(callback, extra):
        callback(100, extra)
        callback(200, extra)

    fake_win32gui = SimpleNamespace(
        EnumWindows=enum_windows,
        IsWindowVisible=lambda handle: handle == 100,
        GetWindowText=lambda handle: "Olden Era" if handle == 100 else "",
        GetWindowRect=lambda handle: (10, 20, 810, 620),
        SetForegroundWindow=lambda handle: focused.append(handle),
        GetForegroundWindow=lambda: 100,
    )
    fake_win32process = SimpleNamespace(
        GetWindowThreadProcessId=lambda handle: (1, 4321 if handle == 100 else 0),
    )
    monkeypatch.setitem(__import__("sys").modules, "win32gui", fake_win32gui)
    monkeypatch.setitem(__import__("sys").modules, "win32process", fake_win32process)
    controller = WindowController()

    windows = controller.list_windows()

    assert len(windows) == 1
    assert windows[0].title == "Olden Era"
    assert windows[0].bounds.width == 800
    assert windows[0].process_id == 4321
    assert controller.find_by_title_hint("olden") == windows[0]
    assert controller.foreground_handle() == 100
    assert controller.process_id(100) == 4321
    assert controller.focus(100) is True
    assert focused == [100]
