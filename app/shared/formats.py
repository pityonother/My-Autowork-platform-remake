from __future__ import annotations

from decimal import Decimal
from typing import Any


def display_number(value: Any, places: int = 2) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return str(value)
    return f"{number:,.{places}f}"
