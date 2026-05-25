from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    message: str
    severity: str = "error"


class QolModule(Protocol):
    id: str
    name: str

    def build_panel(self):
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def validate_profile(self) -> list[ValidationIssue]:
        ...

