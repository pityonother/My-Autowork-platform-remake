from __future__ import annotations

from datetime import date

from openpyxl import Workbook, load_workbook

from app.modules.booking.legacy_adapter import BookingPreview, build_booking_preview, write_booking_workbook
from app.modules.booking.mail_builder import extract_sil_warehouse_no, replace_mail_template_values
from app.modules.booking.rules.registry import SUPPLIER_RULES, get_supplier_names


def test_booking_rule_registry_exposes_expected_suppliers() -> None:
    assert "SIL-FUCA" in get_supplier_names()
    assert "SIL-WEIKENG" in get_supplier_names()
    assert "VC_DZYQ" in get_supplier_names()


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


def test_vc_dzyq_rule_maps_desktop_document_requirements(tmp_path) -> None:
    source_path = tmp_path / "VC_DZYQ.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "清单 "
    ws.append(
        [
            "厂商编号",
            "厂商",
            "Customer_PO",
            "",
            "PO Item",
            "CustPartNumber",
            "CPNRev",
            "TI_MATERIAL",
            "BoxQty",
            "Net",
            "Net Wght Unit",
            "Total Wght",
            "Total Wght Unit",
            "PLS",
        ]
    )
    ws.append(["VC_DZYQ", "TI原厂", "C33C-26010025", "0001", "1010170933002T", "", "TLV70933PKR", 2000, 98, "G", 0.79, "KG", 2, "US"])
    ws.append([None, None, None, None, None, None, "合计", 2000, None, None, None, None, 2, None])
    wb.save(source_path)

    preview = build_booking_preview(session_id="vc-test", supplier="VC_DZYQ", source_path=source_path)

    assert preview.can_generate
    assert len(preview.rows) == 1
    row = preview.rows[0]
    assert row["订单号"] == "1010170933002T"
    assert row["启益料号"] == "C33C-26010025-0001"
    assert row["商品名称"] == "IC"
    assert row["数量"] == 2000
    assert row["单位"] == "PCS"
    assert row["纸箱数"] == 2
    assert row["净重"] == 0.098
    assert row["毛重"] == 0.79
    assert row["体积"] == 0.01
    assert row["生产日期"] == date.today().strftime("%Y-%m-%d")
    assert row["产地 (made in)"] == "US"
    assert row["批次"] == "0"
    assert row["品牌"] == "无"
    assert row["LEDBinCode"] == "无"
    assert row["最小包装数"] == 2000
    assert row["每箱标准数"] == 2000


def test_write_booking_workbook_unmerges_template_rows_for_all_suppliers(tmp_path) -> None:
    columns = [
        "订单号",
        "启益料号",
        "商品名称",
        "数量",
        "单位",
        "纸箱数",
        "净重",
        "毛重",
        "体积",
        "产地 (made in)",
        "批次",
        "品牌",
        "LEDBinCode",
        "最小包装数",
        "每箱标准数",
    ]
    rows = [
        {
            "订单号": f"PO-{index:04d}",
            "启益料号": f"PART-{index:04d}",
            "商品名称": "IC",
            "数量": 1000 + index,
            "单位": "PCS",
            "纸箱数": index,
            "净重": index / 10,
            "毛重": index / 10 + 1,
            "体积": 0.01 if index == 1 else 0,
            "产地 (made in)": "US",
            "批次": "0",
            "品牌": "无",
            "LEDBinCode": "无",
            "最小包装数": 1000 + index,
            "每箱标准数": 1000 + index,
        }
        for index in range(1, 17)
    ]
    preview = BookingPreview(
        session_id="global-merge-test",
        supplier="SIL-FUCA",
        source_filename="synthetic.xlsx",
        pack_filename="",
        rows=rows,
        columns=columns,
    )
    output_path = write_booking_workbook(preview, tmp_path)
    output_wb = load_workbook(output_path, data_only=True)
    output_ws = output_wb[output_wb.sheetnames[0]]

    assert output_ws["C20"].value == "PO-0012"
    assert output_ws["D20"].value == "PART-0012"
    assert output_ws["E20"].value == "IC"
    assert output_ws["C21"].value == "PO-0013"
    assert output_ws["D21"].value == "PART-0013"
    assert output_ws["C24"].value == "PO-0016"
    assert output_ws["D24"].value == "PART-0016"
    assert output_ws["B20"].style_id == output_ws["B19"].style_id
    assert output_ws["C20"].style_id == output_ws["C19"].style_id
    assert output_ws["E20"].style_id == output_ws["E19"].style_id
    assert output_ws["B21"].style_id == output_ws["B19"].style_id
    assert output_ws["C21"].style_id == output_ws["C19"].style_id
    assert output_ws["E24"].style_id == output_ws["E19"].style_id
