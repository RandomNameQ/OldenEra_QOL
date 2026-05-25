from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from oldenera_qol.modules.unit_placer.planner import MovePlan
from oldenera_qol.vision.capture import WindowBounds


@dataclass(slots=True)
class AutomationTiming:
    move_duration_seconds: float = 0.18
    pause_between_moves_seconds: float = 0.12
    drag_button: str = "left"


class EmergencyStop:
    def __init__(self) -> None:
        self.is_requested = False

    def request(self) -> None:
        self.is_requested = True

    def reset(self) -> None:
        self.is_requested = False


class DragExecutor:
    def __init__(self, timing: AutomationTiming | None = None) -> None:
        self.timing = timing or AutomationTiming()

    def execute(
        self,
        plan: MovePlan,
        bounds: WindowBounds,
        stop: EmergencyStop,
        log,
    ) -> None:
        try:
            import pydirectinput
        except ImportError as exc:  # pragma: no cover - exercised in real environment
            raise RuntimeError("pydirectinput is required for drag automation") from exc

        for action in plan.actions:
            if stop.is_requested:
                log("Emergency stop triggered; remaining moves cancelled")
                return
            source = bounds.relative_to_screen(action.source)
            target = bounds.relative_to_screen(action.target)
            label = action.label or (action.slot.id if action.slot is not None else "move")
            log(f"Dragging {label} from {source} to {target}")
            pydirectinput.moveTo(*source, duration=self.timing.move_duration_seconds)
            pydirectinput.mouseDown(button=self.timing.drag_button)
            pydirectinput.moveTo(*target, duration=self.timing.move_duration_seconds)
            pydirectinput.mouseUp(button=self.timing.drag_button)
            sleep(self.timing.pause_between_moves_seconds)
