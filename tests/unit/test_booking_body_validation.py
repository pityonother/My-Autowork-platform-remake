from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.modules.booking.body_validation import (
    _parse_per_box_expression,
    build_body_validation_preview,
    build_corrected_body_validation_workbook,
)
from app.modules.booking.sil_fuca_delivery import SilFucaDeliveryRecord, SilFucaDeliveryResponse
from app.modules.booking import routes as booking_routes
from booking_web_app import app as booking_app


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Booking Form"
    for column_index, title in enumerate(
        [
            "Line",
            "Case number",
            "PO No.",
            "PN",
            "Part Description",
            "Quantity",
            "Unit",
            "Cartons",
            "N.Wt",
            "G.Wt",
            "CBM",
            "Pallet",
            "Invoice No.",
            "production date",
            "Invoice Date",
            "Made In",
            "Batch No.",
            "ASN",
            "Supplier card number",
            "Supplier delivery note number",
            "Tray Type",
            "brand",
            "LEDBinCode",
            "Min package",
            "Standard quantity per box",
            "IPPC",
            "Remark",
        ],
        start=1,
    ):
        ws.cell(8, column_index).value = title
    for offset, row in enumerate(rows, start=9):
        for column_index, value in enumerate(row, start=1):
            ws.cell(offset, column_index).value = value
    ws.cell(9 + len(rows), 1).value = "Total"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _set_number_format(content: bytes, cell_address: str, number_format: str) -> bytes:
    wb = load_workbook(BytesIO(content))
    ws = wb[wb.sheetnames[0]]
    ws[cell_address].number_format = number_format
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _valid_row(*, made_date: object = "2026-01-12", per_box: object = 4000) -> list[object]:
    return [
        1,
        "CASE1",
        "C33C-25040701-0001",
        "ABC123",
        "IC",
        4000,
        "PCS",
        1,
        1,
        2,
        0.1,
        0,
        "INV1",
        made_date,
        "",
        "CN",
        "B1",
        "",
        "",
        "123456789012345",
        "",
        "BRAND",
        "BIN",
        1000,
        per_box,
        "",
        "",
    ]


def _sil_fuca_row(*, po: str, pn: str, quantity: object) -> list[object]:
    row = _valid_row()
    row[3 - 1] = po
    row[4 - 1] = pn
    row[6 - 1] = quantity
    return row


def _delivery_record(
    *,
    po: str,
    pn: str = "1010300202002T01",
    delivery_quantity: object = "20000",
    delivery_date: str = "2026-07-03",
) -> SilFucaDeliveryRecord:
    return SilFucaDeliveryRecord(
        po=po,
        product_code=pn,
        delivery_quantity=Decimal(str(delivery_quantity)),
        delivery_date=date.fromisoformat(delivery_date),
        delivery_list_no="2026062700003-0000000023",
    )


class _FakeSilFucaDeliveryClient:
    def __init__(
        self,
        *,
        new_records: dict[tuple[str, str], tuple[SilFucaDeliveryRecord, ...]] | None = None,
        new_errors: dict[tuple[str, str], tuple[str, ...]] | None = None,
        all_records: tuple[SilFucaDeliveryRecord, ...] = (),
    ) -> None:
        self.new_records = new_records or {}
        self.new_errors = new_errors or {}
        self.all_records = all_records
        self.queries = []
        self.all_call_count = 0

    def get_delivery_list_new(self, query):
        self.queries.append(query)
        key = (query.po, query.pn)
        records = self.new_records.get(key, ())
        return SilFucaDeliveryResponse(
            success=bool(records),
            records=records,
            errors=self.new_errors.get(key, ()),
        )

    def get_all_delivery_list(self):
        self.all_call_count += 1
        return self.all_records


def test_booking_body_validation_flags_static_body_issues() -> None:
    content = _workbook_bytes(
        [
            [
                1,
                "",
                "BADPO",
                "PN-1",
                "IC",
                0,
                "PCS",
                "1.5",
                0,
                0,
                "10X10",
                "NA",
                "INV #1",
                "bad-date",
                "",
                "MARS",
                "",
                "",
                "",
                "BAD",
                "WOODEN PALLET",
                "NA",
                "",
                10,
                3,
                "",
                "",
            ]
        ]
    )

    preview = build_body_validation_preview(content, filename="bad.xlsx")
    issue_fields = {issue.field_code for issue in preview.issues}

    assert preview.row_count == 1
    assert {
        "case_number",
        "PO_No",
        "Customer_Part_No",
        "Quantity",
        "Pkgs",
        "CBM",
        "Pallet",
        "Invoice_No",
        "madeDate",
        "Made_In",
        "packing",
        "brand",
        "per_box",
    }.issubset(issue_fields)
    assert "Pallet" in preview.rows[0].issue_fields


def test_booking_body_validation_applies_safe_static_fixes() -> None:
    content = _workbook_bytes(
        [
            [
                1,
                "CASE1",
                "C33C-25040701-0001",
                "ABC123",
                "IC",
                10,
                "",
                1,
                1,
                2,
                0,
                "NA",
                "INV #1",
                "202510",
                "",
                "CN",
                "",
                "",
                "",
                "123456789012345",
                "",
                "NA",
                "",
                "",
                "",
                "",
                "",
            ]
        ]
    )

    preview = build_body_validation_preview(content, filename="fix.xlsx", apply_fixes=True)
    row = preview.rows[0]

    assert row.values["unit"] == "PCS"
    assert row.values["Pallet"] == "0"
    assert row.values["Invoice_No"] == "INV1"
    assert row.values["Batch_No"] == "0"
    assert row.values["brand"] == "无"
    assert row.values["LEDBinCode"] == "无"
    assert row.values["min_package"] == "10"
    assert row.values["per_box"] == "10"
    assert preview.issue_count == 0
    assert preview.fix_count == 8


def test_booking_body_validation_keeps_manual_review_na_fields_unfixed() -> None:
    row = _valid_row(per_box=4000)
    row[8 - 1] = "NA"  # Cartons / Pkgs
    row[24 - 1] = "NA"  # Min package
    content = _workbook_bytes([row])

    preview = build_body_validation_preview(content, filename="manual-na.xlsx", apply_fixes=True)
    fixed_row = preview.rows[0]

    assert fixed_row.values["Pkgs"] == "NA"
    assert fixed_row.values["min_package"] == "NA"
    assert "Pkgs" in fixed_row.issue_fields
    assert "min_package" in fixed_row.issue_fields


def test_booking_body_validation_fills_empty_case_number_with_zero() -> None:
    row = _valid_row()
    row[2 - 1] = ""
    content = _workbook_bytes([row])

    preview = build_body_validation_preview(content, filename="case-number.xlsx", apply_fixes=True)

    assert preview.rows[0].values["case_number"] == "0"
    assert preview.rows[0].correction_kind_for("case_number") == "default_zero"
    assert "case_number" in preview.rows[0].fixed_fields
    assert preview.issue_count == 0

    corrected = build_corrected_body_validation_workbook(content, filename="case-number.xlsx")
    wb = load_workbook(BytesIO(corrected))
    assert wb[wb.sheetnames[0]]["B9"].value == "0"


def test_booking_body_validation_normalizes_static_text_and_numeric_values() -> None:
    row = _valid_row()
    row[23 - 1] = "BIN"  # Keep LEDBinCode valid after changing nearby fields.
    row[24 - 1] = 1000
    row[25 - 1] = 4000
    row[3 - 1] = "C33C250407010001"
    row[4 - 1] = "AB-123 / 45"
    row[6 - 1] = "1,000 pcs"
    row[8 - 1] = "2+3"
    row[13 - 1] = "INV-001/02"
    row[16 - 1] = "TW"
    content = _workbook_bytes([row])

    preview = build_body_validation_preview(content, filename="normalize.xlsx", apply_fixes=True)
    fixed_row = preview.rows[0]

    assert fixed_row.values["PO_No"] == "C33C-25040701-0001"
    assert fixed_row.values["Customer_Part_No"] == "AB12345"
    assert fixed_row.values["Quantity"] == "1000"
    assert fixed_row.values["Pkgs"] == "5"
    assert fixed_row.values["Invoice_No"] == "INV00102"
    assert fixed_row.values["Made_In"] == "TW,CN"
    assert preview.issue_count == 0


def test_booking_body_validation_averages_zero_weight_by_case_number() -> None:
    first = _valid_row()
    first[2 - 1] = "CASE-A"
    first[9 - 1] = 0
    first[10 - 1] = 0
    second = _valid_row()
    second[1 - 1] = 2
    second[2 - 1] = "CASE-A"
    second[9 - 1] = 6
    second[10 - 1] = 8
    content = _workbook_bytes([first, second])

    preview = build_body_validation_preview(content, filename="weights.xlsx", apply_fixes=True)
    first_row, second_row = preview.rows

    assert first_row.values["FJZ"] == "3"
    assert second_row.values["FJZ"] == "3"
    assert first_row.values["G_Wt"] == "4"
    assert second_row.values["G_Wt"] == "4"
    assert first_row.correction_kind_for("FJZ") == "weight_average_by_case"
    assert second_row.correction_kind_for("G_Wt") == "weight_average_by_case"
    assert preview.issue_count == 0


def test_per_box_expression_parser_matches_supplier_examples() -> None:
    assert _parse_per_box_expression("2K+2K") == "4000"
    assert _parse_per_box_expression("6K*5CARTON+5K+3K*3CARTON+1K*2CARTON") == "46000"


def test_booking_body_validation_applies_example_corrections() -> None:
    content = _workbook_bytes(
        [
            _valid_row(made_date="2026-01-12 AND 2026-01-26", per_box="2K+2K"),
            _valid_row(per_box="6K*5carton+5k+3k*3carton+1k*2carton"),
        ]
    )

    preview = build_body_validation_preview(content, filename="supplier.xlsx", apply_fixes=True)
    first_row = preview.rows[0]
    second_row = preview.rows[1]

    assert first_row.source_values["madeDate"] == "2026-01-12AND2026-01-26"
    assert first_row.values["madeDate"] == "2026-01-12"
    assert first_row.correction_options_for("madeDate") == ("2026-01-12", "2026-01-26")
    assert first_row.correction_kind_for("madeDate") == "date_choice"
    assert first_row.values["per_box"] == "4000"
    assert second_row.values["per_box"] == "46000"
    assert "madeDate" in first_row.source_issue_fields
    assert "per_box" in first_row.source_issue_fields
    assert "per_box" in second_row.source_issue_fields
    assert preview.source_issue_count == 3
    assert preview.issue_count == 0


def test_booking_body_validation_flags_excel_date_display_format() -> None:
    content = _workbook_bytes([_valid_row(made_date=datetime(2026, 3, 23))])
    content = _set_number_format(content, "N9", "mm/dd/yy")

    preview = build_body_validation_preview(content, filename="date-format.xlsx")

    date_issue = next(issue for issue in preview.issues if issue.field_code == "madeDate")
    assert date_issue.correction_kind == "date_format"
    assert "mm/dd/yy" in date_issue.message
    assert "2026/3/23" in date_issue.message
    assert "2026-03-23" in date_issue.message

    fixed_preview = build_body_validation_preview(content, filename="date-format.xlsx", apply_fixes=True)
    assert "madeDate" in fixed_preview.rows[0].fixed_fields
    assert fixed_preview.rows[0].correction_kind_for("madeDate") == "date_format"
    assert not fixed_preview.issues


def test_booking_body_validation_sil_fuca_delivery_accepts_successful_record() -> None:
    pn = "1010300202002T01"
    content = _workbook_bytes(
        [
            _sil_fuca_row(po="T33U-26040025-0002", pn=pn, quantity=12000),
            _sil_fuca_row(po="T33U-26040025-0002", pn=pn, quantity=8000),
        ]
    )
    client = _FakeSilFucaDeliveryClient(
        new_records={
            ("T33U-26040025-0002", pn): (
                _delivery_record(po="T33U-26040025-0002", pn=pn, delivery_quantity=20000),
            )
        }
    )

    preview = build_body_validation_preview(
        content,
        filename="sil.xlsx",
        apply_fixes=True,
        enable_dynamic_checks=True,
        sil_fuca_delivery_client=client,
        query_date=date(2026, 6, 29),
    )

    assert len(client.queries) == 1
    assert client.queries[0].qty == Decimal("20000")
    assert preview.issue_count == 0
    assert preview.fix_count == 0


def test_sil_fuca_delivery_record_parses_api_date() -> None:
    record = SilFucaDeliveryRecord.from_api(
        {
            "purchase_order_type": "T33U",
            "purchase_order_no": "26040025",
            "purchase_order_seq": "0002",
            "product_code": "1010300202002T01",
            "delivery_quantity": 20000.0,
            "delivery_date": "2026-07-03T00:00:00",
        }
    )

    assert record.po == "T33U-26040025-0002"
    assert record.delivery_quantity == Decimal("20000.0")
    assert record.delivery_date == date(2026, 7, 3)


def test_booking_body_validation_sil_fuca_delivery_suggests_unique_po_sequence() -> None:
    pn = "1010300202002T01"
    content = _workbook_bytes([_sil_fuca_row(po="T33U-26040025-0001", pn=pn, quantity=20000)])
    client = _FakeSilFucaDeliveryClient(
        new_errors={
            ("T33U-26040025-0001", pn): (
                "T33U-26040025-0001 1010300202002T01匹配不上周期交货清单，请检查是否有上传",
            )
        },
        all_records=(
            _delivery_record(po="T33U-26040025-0002", pn=pn, delivery_quantity=20000),
        ),
    )

    preview = build_body_validation_preview(
        content,
        filename="sil.xlsx",
        apply_fixes=True,
        enable_dynamic_checks=True,
        sil_fuca_delivery_client=client,
        query_date=date(2026, 6, 29),
    )

    row = preview.rows[0]
    assert client.all_call_count == 1
    assert row.values["PO_No"] == "T33U-26040025-0002"
    assert row.correction_kind_for("PO_No") == "sil_fuca_delivery_po"
    assert "PO_No" in row.fixed_fields
    assert "PO_No" in row.source_issue_fields
    assert preview.issue_count == 0
    assert preview.source_issue_count == 1

    corrected = build_corrected_body_validation_workbook(
        content,
        filename="sil.xlsx",
        enable_dynamic_checks=True,
        sil_fuca_delivery_client=client,
        query_date=date(2026, 6, 29),
    )
    wb = load_workbook(BytesIO(corrected))
    assert wb[wb.sheetnames[0]]["C9"].value == "T33U-26040025-0002"


def test_booking_body_validation_sil_fuca_delivery_flags_missing_record() -> None:
    pn = "1010300202002T01"
    content = _workbook_bytes([_sil_fuca_row(po="K33U-24090083-0001", pn=pn, quantity=20000)])
    client = _FakeSilFucaDeliveryClient(
        new_errors={
            ("K33U-24090083-0001", pn): (
                "K33U-24090083-0001 匹配不上周期交货清单，请检查是否有上传",
            )
        }
    )

    preview = build_body_validation_preview(
        content,
        filename="sil.xlsx",
        apply_fixes=True,
        enable_dynamic_checks=True,
        sil_fuca_delivery_client=client,
        query_date=date(2026, 6, 29),
    )

    assert preview.issue_count == 1
    assert preview.issues[0].correction_kind == "sil_fuca_delivery_missing"
    assert "匹配不上周期交货清单" in preview.issues[0].message
    assert "PO_No" in preview.rows[0].issue_fields
    assert "PO_No" in preview.rows[0].source_issue_fields


def test_booking_body_validation_sil_fuca_delivery_checks_quantity_and_date() -> None:
    pn = "1010300202002T01"
    content = _workbook_bytes(
        [
            _sil_fuca_row(po="T33U-26040025-0002", pn=pn, quantity=21000),
            _sil_fuca_row(po="K33U-26040025-0002", pn=pn, quantity=1000),
        ]
    )
    client = _FakeSilFucaDeliveryClient(
        new_records={
            ("T33U-26040025-0002", pn): (
                _delivery_record(po="T33U-26040025-0002", pn=pn, delivery_quantity=20000),
            ),
            ("K33U-26040025-0002", pn): (
                _delivery_record(po="K33U-26040025-0002", pn=pn, delivery_quantity=20000, delivery_date="2026-06-29"),
            ),
        }
    )

    preview = build_body_validation_preview(
        content,
        filename="sil.xlsx",
        apply_fixes=True,
        enable_dynamic_checks=True,
        sil_fuca_delivery_client=client,
        query_date=date(2026, 6, 29),
    )

    messages = {issue.field_code: issue.message for issue in preview.issues}
    assert "大于周期清单数量 20000" in messages["Quantity"]
    assert "没有早于周期交货日期 2026-06-29" in messages["PO_No"]


def test_booking_body_validation_route_marks_error_cells() -> None:
    content = _workbook_bytes(
        [
            [
                1,
                "",
                "BADPO",
                "PN-1",
                "IC",
                0,
                "PCS",
                0,
                0,
                0,
                0,
                "",
                "INV #1",
                "bad-date",
                "",
                "MARS",
                "",
                "",
                "",
                "BAD",
                "",
                "NA",
                "",
                10,
                3,
                "",
                "",
            ]
        ]
    )
    client = TestClient(booking_app)

    response = client.post(
        "/modules/booking/body-validation",
        data={"apply_fixes": "0"},
        files={
            "booking_file": (
                "supplier_booking.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert "源数据导入表" in response.text
    assert "screening-cell-error" in response.text
    assert "PO No. 格式应类似" in response.text


def test_booking_body_validation_export_downloads_corrected_workbook(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(booking_routes, "BODY_VALIDATION_EXPORT_DIR", tmp_path)
    monkeypatch.setattr(booking_routes, "BODY_VALIDATION_UPLOAD_DIR", tmp_path / "uploads")
    content = _workbook_bytes(
        [
            _valid_row(made_date="2026-01-12 AND 2026-01-26", per_box="2K+2K"),
            _valid_row(made_date=datetime(2026, 3, 23), per_box=5000),
        ]
    )
    client = TestClient(booking_app)

    response = client.post(
        "/modules/booking/body-validation",
        data={"apply_fixes": "0"},
        files={
            "booking_file": (
                "supplier booking.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert "/modules/booking/body-validation/export/" not in response.text
    session_match = re.search(r'name="validation_session_id" value="([0-9a-f]{32})"', response.text)
    assert session_match

    suggestion_response = client.post(
        "/modules/booking/body-validation",
        data={"apply_fixes": "1", "validation_session_id": session_match.group(1)},
    )

    assert suggestion_response.status_code == 200
    match = re.search(r'href="([^"]*/modules/booking/body-validation/export/[^"]+)"', suggestion_response.text)
    assert match

    download = client.get(match.group(1))
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    wb = load_workbook(BytesIO(download.content))
    ws = wb[wb.sheetnames[0]]
    assert ws["N9"].value == datetime(2026, 1, 12)
    assert ws["N9"].number_format == "yyyy-mm-dd"
    assert ws["N10"].value == datetime(2026, 3, 23)
    assert ws["N10"].number_format == "yyyy-mm-dd"
    assert str(ws["Y9"].value) == "4000"
