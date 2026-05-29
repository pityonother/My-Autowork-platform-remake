from __future__ import annotations

from app.modules.booking.rules.adapter import ModuleRuleAdapter
from app.modules.booking.rules.protocol import BookingSupplierRule
from booking_rules import sil, vc_dzyq, weikeng


class BookingRuleRegistry:
    def __init__(self) -> None:
        self._items: dict[str, BookingSupplierRule] = {}

    def register(self, rule: BookingSupplierRule) -> None:
        self._items[rule.SUPPLIER_NAME] = rule

    def names(self) -> list[str]:
        return sorted(self._items.keys())

    def as_dict(self) -> dict[str, BookingSupplierRule]:
        return dict(self._items)


registry = BookingRuleRegistry()
registry.register(ModuleRuleAdapter(sil))
registry.register(ModuleRuleAdapter(vc_dzyq))
registry.register(ModuleRuleAdapter(weikeng))

SUPPLIER_RULES = registry.as_dict()


def get_supplier_names() -> list[str]:
    return registry.names()
