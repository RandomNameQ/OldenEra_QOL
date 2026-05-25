from __future__ import annotations

from oldenera_qol.modules.base import QolModule


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, QolModule] = {}

    def register(self, module: QolModule) -> None:
        self._modules[module.id] = module

    def get(self, module_id: str) -> QolModule:
        return self._modules[module_id]

    def all(self) -> list[QolModule]:
        return list(self._modules.values())

