from __future__ import annotations

from app.modules.export_clearance.rules import (
    export_record_business_key,
    format_pallet_carton_text,
    normalize_tan_number,
    urgency_sort_key,
)


def test_export_clearance_rule_helpers_normalize_display_values() -> None:
    assert normalize_tan_number("tan#123") == "TAN#123"
    assert format_pallet_carton_text("2.0", "3.0") == "2板/3箱"


def test_export_record_business_key_uses_core_identity_fields() -> None:
    record = {
        "tan_number": "TAN#1",
        "total_pcs": "10",
        "carton_count": "2",
        "pallet_count": "1",
        "total_value_usd": "33.5",
        "gross_weight_kg": "44.2",
    }

    assert export_record_business_key(" M1 ", "2026-05-18", record) == (
        "M1",
        "2026-05-18",
        "TAN#1",
        10,
        2,
        1,
        33.5,
        44.2,
    )


def test_export_clearance_urgency_sort_orders_red_first() -> None:
    rows = [
        {"urgency_color": "white", "shipment_date": "2026-05-18", "tan_number": "TAN#2"},
        {"urgency_color": "red", "shipment_date": "2026-05-17", "tan_number": "TAN#1"},
        {"urgency_color": "orange", "shipment_date": "2026-05-16", "tan_number": "TAN#3"},
    ]

    assert [item["urgency_color"] for item in sorted(rows, key=urgency_sort_key)] == ["red", "orange", "white"]
