from oldenera_qol.modules.unit_placer.planner import build_move_plan
from oldenera_qol.profiles.models import DestinationSlot, UnitProfile
from oldenera_qol.vision.models import Rect, UnitDetection


def test_build_move_plan_assigns_identical_duplicates_by_screen_order() -> None:
    profile = UnitProfile(
        profile_name="default",
        slots=[
            DestinationSlot("slot_a", "archer", 64, 500, 100),
            DestinationSlot("slot_b", "archer", 64, 600, 100),
        ],
    )
    detections = [
        UnitDetection("archer", Rect(200, 20, 40, 40), 0.91, quantity=64),
        UnitDetection("archer", Rect(100, 20, 40, 40), 0.95, quantity=64),
    ]

    plan = build_move_plan(detections, profile)

    assert [action.slot.id for action in plan.actions] == ["slot_a", "slot_b"]
    assert [action.source for action in plan.actions] == [(120, 40), (220, 40)]


def test_build_move_plan_logs_missing_slots_and_ocr_failures() -> None:
    profile = UnitProfile(
        profile_name="default",
        slots=[DestinationSlot("slot_a", "archer", 64, 500, 100)],
    )
    detections = [UnitDetection("archer", Rect(10, 10, 40, 40), 0.91, quantity=None)]

    plan = build_move_plan(detections, profile)

    assert plan.actions == []
    assert any("Missing unit" in message for message in plan.log_messages)
    assert any("OCR returned no digits" in message for message in plan.log_messages)


def test_build_move_plan_supports_min_max_and_any_quantity_rules() -> None:
    profile = UnitProfile(
        profile_name="default",
        slots=[
            DestinationSlot("slot_min", "archer", 20, 500, 100, "min"),
            DestinationSlot("slot_max", "archer", 10, 600, 100, "max"),
            DestinationSlot("slot_any", "griffin", 1, 700, 100, "any"),
        ],
    )
    detections = [
        UnitDetection("archer", Rect(10, 10, 40, 40), 0.91, quantity=24),
        UnitDetection("archer", Rect(60, 10, 40, 40), 0.91, quantity=8),
        UnitDetection("griffin", Rect(110, 10, 40, 40), 0.91, quantity=123),
    ]

    plan = build_move_plan(detections, profile)

    assert [action.slot.id for action in plan.actions] == ["slot_min", "slot_max", "slot_any"]
