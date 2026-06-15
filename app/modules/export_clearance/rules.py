from __future__ import annotations

import re
from typing import Any

TAN_NUMBER_RE = re.compile(r"^\s*T\s*A\s*N\s*[#＃]?\s*([A-Za-z0-9-]+)\s*$", re.IGNORECASE)


def clean_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def normalize_tan_number(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = TAN_NUMBER_RE.match(text)
    if match:
        return f"TAN#{match.group(1).upper()}"
    return text.replace("Tan#", "TAN#").replace("tan#", "TAN#")


def is_tan_number(value: object) -> bool:
    text = str(value or "").strip()
    return bool(TAN_NUMBER_RE.match(text))


def export_record_business_key(
    manifest_code: str,
    shipment_date: str,
    record: dict[str, Any] | Any,
) -> tuple[Any, ...]:
    return (
        clean_text(manifest_code),
        clean_text(shipment_date),
        clean_text(record["tan_number"]),
        int(record["total_pcs"] or 0),
        int(record["carton_count"] or 0),
        int(record["pallet_count"] or 0),
        float(record["total_value_usd"] or 0),
        float(record["gross_weight_kg"] or 0),
    )


def urgency_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    priority_map = {"red": 0, "orange": 1, "white": 2}
    return (
        priority_map.get(item["urgency_color"], 3),
        item["shipment_date"] or "",
        item["tan_number"],
    )


def format_pallet_carton_text(pallet_count: Any, carton_count: Any) -> str:
    return f"{int(float(pallet_count or 0))}板/{int(float(carton_count or 0))}箱"


__all__ = [
    "export_record_business_key",
    "format_pallet_carton_text",
    "is_tan_number",
    "normalize_tan_number",
    "urgency_sort_key",
]
