from __future__ import annotations

from types import ModuleType
from typing import Any


class ModuleRuleAdapter:
    def __init__(self, module: ModuleType) -> None:
        self.module = module

    def __getattr__(self, name: str) -> Any:
        return getattr(self.module, name)

    @property
    def SUPPLIER_NAME(self) -> str:
        return self.module.SUPPLIER_NAME

    def post_process(self, detail_rows: list[dict[str, Any]], packadc_rows: list[dict[str, Any]]):
        return self.module.post_process(detail_rows, packadc_rows)
