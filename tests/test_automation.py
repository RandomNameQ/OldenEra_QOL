from types import SimpleNamespace

from oldenera_qol.automation.mouse import AutomationTiming, DragExecutor, EmergencyStop
from oldenera_qol.modules.unit_placer.planner import MoveAction, MovePlan
from oldenera_qol.profiles.models import DestinationSlot
from oldenera_qol.vision.capture import WindowBounds
from oldenera_qol.vision.models import Rect, UnitDetection


def test_emergency_stop_tracks_requested_state() -> None:
    stop = EmergencyStop()

    stop.request()
    assert stop.is_requested is True

    stop.reset()
    assert stop.is_requested is False


def test_drag_executor_converts_relative_coordinates(monkeypatch) -> None:
    calls = []
    fake_input = SimpleNamespace(
        moveTo=lambda *args, **kwargs: calls.append(("moveTo", args, kwargs)),
        mouseDown=lambda *args, **kwargs: calls.append(("mouseDown", args, kwargs)),
        mouseUp=lambda *args, **kwargs: calls.append(("mouseUp", args, kwargs)),
    )
    monkeypatch.setitem(__import__("sys").modules, "pydirectinput", fake_input)
    action = MoveAction(
        detection=UnitDetection("archer", Rect(10, 20, 40, 40), 0.9, quantity=64),
        slot=DestinationSlot("slot_1", "archer", 64, 80, 90),
        source=(30, 40),
        target=(80, 90),
    )
    logs: list[str] = []

    DragExecutor(AutomationTiming(0, 0, "left")).execute(
        MovePlan([action], []),
        WindowBounds(100, 200, 800, 600),
        EmergencyStop(),
        logs.append,
    )

    assert calls[0][1][:2] == (130, 240)
    assert calls[1][0] == "mouseDown"
    assert calls[2][1][:2] == (180, 290)
    assert calls[3][0] == "mouseUp"
    assert "Dragging slot_1" in logs[0]


def test_drag_executor_stops_before_first_move(monkeypatch) -> None:
    calls = []
    fake_input = SimpleNamespace(
        moveTo=lambda *args, **kwargs: calls.append("move"),
        mouseDown=lambda *args, **kwargs: calls.append("down"),
        mouseUp=lambda *args, **kwargs: calls.append("up"),
    )
    monkeypatch.setitem(__import__("sys").modules, "pydirectinput", fake_input)
    stop = EmergencyStop()
    stop.request()
    action = MoveAction(
        detection=UnitDetection("archer", Rect(0, 0, 10, 10), 0.9, quantity=1),
        slot=DestinationSlot("slot_1", "archer", 1, 10, 10),
        source=(5, 5),
        target=(10, 10),
    )
    logs: list[str] = []

    DragExecutor(AutomationTiming(0, 0, "left")).execute(
        MovePlan([action], []),
        WindowBounds(0, 0, 100, 100),
        stop,
        logs.append,
    )

    assert calls == []
    assert "Emergency stop" in logs[0]
