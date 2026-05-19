from __future__ import annotations

from app.modules.booking.mail_builder import extract_sil_warehouse_no, replace_mail_template_values
from app.modules.booking.rules.registry import SUPPLIER_RULES, get_supplier_names


def test_booking_rule_registry_exposes_expected_suppliers() -> None:
    assert "SIL-FUCA" in get_supplier_names()
    assert "SIL-WEIKENG" in get_supplier_names()


def test_weikeng_total_box_count_is_written_only_on_first_row() -> None:
    rule = SUPPLIER_RULES["SIL-WEIKENG"]

    extras, warnings = rule.post_process(
        [{"_summary_box_count": 12}, {"_summary_box_count": 12}],
        [],
    )

    assert warnings == []
    assert extras == [{"Total Box Count": 12}, {"Total Box Count": 0}]


def test_sil_warehouse_mail_helpers_replace_mawb_and_warehouse_no(tmp_path) -> None:
    warehouse_file = tmp_path / "SIL26040490 入仓纸.pdf"

    assert extract_sil_warehouse_no(warehouse_file) == "SIL26040490"
    assert (
        replace_mail_template_values("MAWB# 12345678901<br>SIL26040000", "98765432109", "SIL26040490")
        == "MAWB# 98765432109<br>SIL26040490"
    )
