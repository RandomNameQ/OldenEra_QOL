from pathlib import Path

from oldenera_qol.profiles.models import (
    DestinationSlot,
    QuantityRegion,
    UnitProfile,
    UnitTemplate,
    validate_profile,
)
from oldenera_qol.profiles.repository import ProfileRepository


def test_profile_repository_round_trips_profile(tmp_path: Path) -> None:
    profile = UnitProfile(
        profile_name="default",
        window_title_hint="Olden Era",
        templates=[
            UnitTemplate(
                id="archer",
                name="Archer",
                image_path="assets/templates/archer.png",
                match_threshold=0.86,
                quantity_region=QuantityRegion(-18, 34, 36, 18),
            )
        ],
        slots=[
            DestinationSlot(
                id="slot_1",
                unit_template_id="archer",
                required_quantity=64,
                target_x=820,
                target_y=510,
                quantity_mode="min",
            )
        ],
    )
    repository = ProfileRepository(tmp_path)

    repository.save(profile)
    loaded = repository.load("default")

    assert loaded == profile


def test_validate_profile_reports_missing_template_and_invalid_quantity() -> None:
    profile = UnitProfile(
        profile_name="default",
        slots=[
            DestinationSlot(
                id="slot_1",
                unit_template_id="missing",
                required_quantity=0,
                target_x=1,
                target_y=1,
            )
        ],
    )

    issues = validate_profile(profile)

    assert any("references missing template" in issue for issue in issues)
    assert any("quantity must be positive" in issue for issue in issues)
