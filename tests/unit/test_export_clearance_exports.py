from __future__ import annotations

from datetime import date, datetime

from openpyxl import load_workbook

import export_clearance_store as store


def test_export_cleared_workbook_uses_current_headers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "export_clearance.db")
    store.init_db()

    now = datetime(2026, 5, 18, 9, 30).isoformat(timespec="seconds")
    with store.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO export_clearance_batches (
                batch_code, tracker, manifest_code, shipment_date, trip_sequence,
                source_file_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("BATCH-1", "Alice", "MANIFEST-1", "2026-05-17", 1, 1, now),
        )
        batch_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO export_clearance_records (
                batch_id, tan_number, tan_description, sn_number, ship_mode,
                destination, total_pcs, carton_count, pallet_count, total_value_usd,
                gross_weight_kg, truck_plate, container_no, seal_no, port,
                source_file_name, clearance_status, clearance_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                "TAN#100001",
                "",
                "",
                "",
                "US",
                10,
                5,
                2,
                123.45,
                67.8,
                "",
                "",
                "",
                "",
                "sanitized.xlsx",
                "cleared",
                now,
                now,
                now,
            ),
        )

    workbook_bytes = store.export_cleared_workbook(clear_date=date(2026, 5, 18))
    workbook = load_workbook(workbook_bytes)

    all_sheet = workbook["全部已清关"]
    assert [cell.value for cell in all_sheet[1]] == [
        "清关时间",
        "出货时间",
        "Tan号",
        "车单编号",
        "提单号",
        "板数/箱数",
        "毛重",
        "货值",
        "目的国",
        "跟单员",
    ]
    assert all_sheet["C2"].value == "TAN#100001"
    assert all_sheet["F2"].value == "2板/5箱"

    detail_sheet = workbook["当日清关-明细"]
    assert [cell.value for cell in detail_sheet[1]] == ["出货时间", "Tan号", "提单号", "板数/箱数", "毛重", "货值"]
