from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from app.core.db import connect, run_migrations
from app.shared.lazy_imports import lazy_module
from app.shared.performance import cached_file_result
from app_paths import RUNTIME_DIR
from invoice_reconciler import parse_decimal_value

openpyxl = lazy_module("openpyxl")
openpyxl_styles = lazy_module("openpyxl.styles")
pd = lazy_module("pandas")


DB_PATH = RUNTIME_DIR / "export_clearance.db"


@dataclass
class ExportClearanceImportInput:
    tracker: str
    manifest_code: str
    shipment_date: date
    trip_sequence: int
    source_files: Sequence[Path]


def get_connection() -> sqlite3.Connection:
    return connect(DB_PATH)


def migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS export_clearance_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_code TEXT NOT NULL UNIQUE,
            tracker TEXT NOT NULL,
            manifest_code TEXT NOT NULL,
            shipment_date TEXT NOT NULL,
            trip_sequence INTEGER NOT NULL,
            source_file_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS export_clearance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            tan_number TEXT NOT NULL,
            tan_description TEXT,
            sn_number TEXT,
            ship_mode TEXT,
            destination TEXT,
            total_pcs INTEGER NOT NULL,
            carton_count INTEGER NOT NULL,
            pallet_count INTEGER NOT NULL,
            total_value_usd REAL NOT NULL,
            gross_weight_kg REAL NOT NULL,
            truck_plate TEXT,
            container_no TEXT,
            seal_no TEXT,
            port TEXT,
            source_file_name TEXT NOT NULL,
            clearance_status TEXT NOT NULL DEFAULT 'pending',
            clearance_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES export_clearance_batches(id)
        );

        CREATE INDEX IF NOT EXISTS idx_export_clearance_records_batch
            ON export_clearance_records(batch_id);
        CREATE INDEX IF NOT EXISTS idx_export_clearance_records_status
            ON export_clearance_records(clearance_status);
        CREATE INDEX IF NOT EXISTS idx_export_clearance_records_tan
            ON export_clearance_records(tan_number);
        CREATE INDEX IF NOT EXISTS idx_export_clearance_batches_created
            ON export_clearance_batches(created_at);
        """
    )


MIGRATIONS = {
    1: migration_001_initial_schema,
}


def init_db() -> None:
    with get_connection() as conn:
        run_migrations(conn, MIGRATIONS)


def load_excel_file(path: Path) -> tuple[pd.ExcelFile, str]:
    last_error: Exception | None = None
    for engine in ["openpyxl", "xlrd"]:
        try:
            return pd.ExcelFile(path, engine=engine), engine
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    raise last_error


def normalize_header_name(value: object) -> str:
    return str(value or "").strip().replace("\n", "").replace(" ", "").lower()


def clean_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def is_tan_note_row(first_cell: object) -> bool:
    text = str(first_cell or "").strip()
    return text.upper().startswith("TAN#")


def parse_export_clearance_file(path: Path) -> list[dict[str, Any]]:
    return cached_file_result(
        "export_clearance.parse_export_clearance_file",
        path,
        lambda: _parse_export_clearance_file_uncached(path),
    )


def _parse_export_clearance_file_uncached(path: Path) -> list[dict[str, Any]]:
    excel_file, _ = load_excel_file(path)
    sheet = excel_file.parse(excel_file.sheet_names[0], header=None)

    truck_plate = ""
    container_no = ""
    seal_no = ""
    port = ""

    header_row_idx: int | None = None
    for idx in range(len(sheet)):
        row = sheet.iloc[idx].tolist()
        if len(row) >= 3:
            label = str(row[1] or "").strip()
            value = clean_text(row[2])
            if label == "车牌：":
                truck_plate = value
            elif label == "集装箱号：":
                container_no = value
            elif label == "封条号：":
                seal_no = value
            elif label == "出货口岸：":
                port = value
        normalized_row = [normalize_header_name(item) for item in row]
        if "item" in normalized_row and "snno." in normalized_row:
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError(f"{path.name}: 未找到出口清关明细表头。")

    header_values = sheet.iloc[header_row_idx].tolist()
    header_map = {
        normalize_header_name(value): idx
        for idx, value in enumerate(header_values)
        if normalize_header_name(value)
    }

    def col(*names: str) -> int | None:
        for name in names:
            idx = header_map.get(normalize_header_name(name))
            if idx is not None:
                return idx
        return None

    sn_col = col("SN NO.")
    ship_mode_col = col("ship mode")
    destination_col = col("目的国")
    pcs_col = col("总数量PCS", "总数量")
    value_col = col("总价USD", "货值")
    gross_col = col("毛重KG", "毛重")
    carton_col = col("箱数", "总箱数")
    pallet_col = col("卡板数", "板数")

    current_group_rows: list[pd.Series] = []
    parsed_records: list[dict[str, Any]] = []

    for idx in range(header_row_idx + 1, len(sheet)):
        row = sheet.iloc[idx]
        first_value = row.iloc[0] if len(row) > 0 else ""
        first_text = str(first_value or "").strip()

        if not first_text and row.isna().all():
            continue

        if is_tan_note_row(first_value):
            tan_number = normalize_tan_number(first_value)
            tan_description = str(row.iloc[1] or "").strip() if len(row) > 1 else ""
            if current_group_rows:
                parsed_records.append(
                    {
                        "tan_number": tan_number,
                        "tan_description": tan_description,
                        "sn_number": unique_join(item.iloc[sn_col] for item in current_group_rows) if sn_col is not None else "",
                        "ship_mode": unique_join(item.iloc[ship_mode_col] for item in current_group_rows) if ship_mode_col is not None else "",
                        "destination": unique_join(item.iloc[destination_col] for item in current_group_rows) if destination_col is not None else "",
                        "total_pcs": int(sum_decimal(current_group_rows, pcs_col)),
                        "carton_count": int(sum_decimal(current_group_rows, carton_col)),
                        "pallet_count": int(sum_decimal(current_group_rows, pallet_col)),
                        "total_value_usd": float(sum_decimal(current_group_rows, value_col)),
                        "gross_weight_kg": float(sum_decimal(current_group_rows, gross_col)),
                        "truck_plate": truck_plate,
                        "container_no": container_no,
                        "seal_no": seal_no,
                        "port": port,
                        "source_file_name": path.name,
                    }
                )
            current_group_rows = []
            continue

        if isinstance(first_value, (int, float)) or first_text.isdigit():
            current_group_rows.append(row)

    return parsed_records


def sum_decimal(rows: Sequence[pd.Series], col_idx: int | None) -> float:
    if col_idx is None:
        return 0.0
    total = 0.0
    for row in rows:
        total += float(parse_decimal_value(row.iloc[col_idx]))
    return total


def unique_join(values: Iterable[object]) -> str:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan" or text in seen:
            continue
        seen.append(text)
    return " / ".join(seen)


def find_duplicate_export_record(
    conn: sqlite3.Connection,
    *,
    manifest_code: str,
    shipment_date: str,
    record: dict[str, Any],
) -> sqlite3.Row | None:
    rows = conn.execute(
        """
        SELECT r.*, b.manifest_code, b.shipment_date
        FROM export_clearance_records r
        JOIN export_clearance_batches b ON b.id = r.batch_id
        WHERE b.manifest_code = ?
          AND b.shipment_date = ?
          AND r.tan_number = ?
        ORDER BY CASE WHEN r.clearance_status = 'cleared' THEN 0 ELSE 1 END, r.id ASC
        """,
        (manifest_code, shipment_date, record["tan_number"]),
    ).fetchall()
    target_key = export_record_business_key(manifest_code, shipment_date, record)
    for row in rows:
        if export_record_business_key(row["manifest_code"], row["shipment_date"], row) == target_key:
            return row
    return None


def import_export_clearance_batch(import_input: ExportClearanceImportInput) -> dict[str, Any]:
    init_db()
    imported_at = datetime.now()
    batch_code = f"ECB-{imported_at.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    records: list[dict[str, Any]] = []
    for source_file in import_input.source_files:
        records.extend(parse_export_clearance_file(source_file))

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO export_clearance_batches (
                batch_code, tracker, manifest_code, shipment_date, trip_sequence, source_file_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_code,
                import_input.tracker,
                import_input.manifest_code,
                import_input.shipment_date.isoformat(),
                import_input.trip_sequence,
                len(import_input.source_files),
                imported_at.isoformat(timespec="seconds"),
            ),
        )
        batch_id = cursor.lastrowid
        duplicate_count = 0
        now_text = imported_at.isoformat(timespec="seconds")
        insert_rows: list[tuple[Any, ...]] = []
        for record in records:
            duplicate = find_duplicate_export_record(
                conn,
                manifest_code=import_input.manifest_code,
                shipment_date=import_input.shipment_date.isoformat(),
                record=record,
            )
            if duplicate is not None:
                duplicate_count += 1
                continue
            insert_rows.append(
                (
                    batch_id,
                    record["tan_number"],
                    record["tan_description"],
                    record["sn_number"],
                    record["ship_mode"],
                    record["destination"],
                    record["total_pcs"],
                    record["carton_count"],
                    record["pallet_count"],
                    record["total_value_usd"],
                    record["gross_weight_kg"],
                    record["truck_plate"],
                    record["container_no"],
                    record["seal_no"],
                    record["port"],
                    record["source_file_name"],
                    now_text,
                    now_text,
                )
            )
        if insert_rows:
            conn.executemany(
                """
                INSERT INTO export_clearance_records (
                    batch_id, tan_number, tan_description, sn_number, ship_mode, destination,
                    total_pcs, carton_count, pallet_count, total_value_usd, gross_weight_kg,
                    truck_plate, container_no, seal_no, port, source_file_name,
                    clearance_status, clearance_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                insert_rows,
            )
        inserted_count = len(insert_rows)

    detail = get_batch_detail(batch_id)
    detail["import_stats"] = {
        "parsed_count": len(records),
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
    }
    return detail


def get_batch_detail(batch_id: int) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        batch = conn.execute(
            """
            SELECT * FROM export_clearance_batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if batch is None:
            raise ValueError("未找到导入批次。")
        records = conn.execute(
            """
            SELECT r.*, b.batch_code, b.tracker, b.manifest_code, b.shipment_date, b.trip_sequence
            FROM export_clearance_records r
            JOIN export_clearance_batches b ON b.id = r.batch_id
            WHERE r.batch_id = ?
            ORDER BY r.id DESC
            """,
            (batch_id,),
        ).fetchall()
    return {
        "batch": dict(batch),
        "records": [format_record(row) for row in records],
    }


def list_batches() -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                b.*,
                COUNT(r.id) AS record_count,
                SUM(CASE WHEN r.clearance_status = 'cleared' THEN 1 ELSE 0 END) AS cleared_count,
                SUM(CASE WHEN r.clearance_status = 'pending' THEN 1 ELSE 0 END) AS pending_count
            FROM export_clearance_batches b
            LEFT JOIN export_clearance_records r ON r.batch_id = b.id
            GROUP BY b.id
            ORDER BY b.created_at DESC
            LIMIT 10000
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_records(
    *,
    clearance_status: str | None = None,
    shipment_date_from: str | None = None,
    shipment_date_to: str | None = None,
    tan_number: str | None = None,
    sort_by: str = "urgency",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    init_db()
    query = """
        SELECT r.*, b.batch_code, b.tracker, b.manifest_code, b.shipment_date, b.trip_sequence
        FROM export_clearance_records r
        JOIN export_clearance_batches b ON b.id = r.batch_id
    """
    params: list[Any] = []
    clauses: list[str] = []
    if clearance_status:
        clauses.append("r.clearance_status = ?")
        params.append(clearance_status)
    if shipment_date_from:
        clauses.append("b.shipment_date >= ?")
        params.append(shipment_date_from)
    if shipment_date_to:
        clauses.append("b.shipment_date <= ?")
        params.append(shipment_date_to)
    if tan_number:
        clauses.append("LOWER(r.tan_number) LIKE ?")
        params.append(f"%{tan_number.strip().lower()}%")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY b.shipment_date ASC, r.id ASC"
    query += " LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    records = [format_record(row) for row in rows]
    if sort_by == "urgency":
        records.sort(key=urgency_sort_key)
    elif sort_by == "shipment_date":
        records.sort(key=lambda item: (item["shipment_date"], item["tan_number"]))
    return records


def format_record(row: sqlite3.Row) -> dict[str, Any]:
    shipment_date = str(row["shipment_date"] or "")
    age_days = calculate_age_days(shipment_date)
    clearance_status = row["clearance_status"]
    urgency_color = "white" if clearance_status == "cleared" else resolve_urgency_color(age_days)
    urgency_label = "已清关" if clearance_status == "cleared" else {"white": "7天内", "orange": "7-14天", "red": "超过14天"}.get(urgency_color, "")
    return {
        "id": row["id"],
        "batch_id": row["batch_id"],
        "batch_code": row["batch_code"],
        "tracker": row["tracker"],
        "manifest_code": row["manifest_code"],
        "shipment_date": shipment_date,
        "trip_sequence": row["trip_sequence"],
        "tan_number": row["tan_number"],
        "tan_description": row["tan_description"] or "",
        "sn_number": row["sn_number"] or "",
        "ship_mode": row["ship_mode"] or "",
        "destination": row["destination"] or "",
        "total_pcs": int(row["total_pcs"] or 0),
        "carton_count": int(row["carton_count"] or 0),
        "pallet_count": int(row["pallet_count"] or 0),
        "total_value_usd": float(row["total_value_usd"] or 0),
        "gross_weight_kg": float(row["gross_weight_kg"] or 0),
        "truck_plate": row["truck_plate"] or "",
        "container_no": row["container_no"] or "",
        "seal_no": row["seal_no"] or "",
        "port": row["port"] or "",
        "source_file_name": row["source_file_name"],
        "clearance_status": clearance_status,
        "clearance_at": row["clearance_at"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "age_days": age_days,
        "urgency_color": urgency_color,
        "urgency_label": urgency_label,
    }


def calculate_age_days(shipment_date_text: str) -> int:
    if not shipment_date_text:
        return 0
    shipment_date = date.fromisoformat(shipment_date_text)
    return (date.today() - shipment_date).days


def resolve_urgency_color(age_days: int) -> str:
    if age_days > 14:
        return "red"
    if age_days > 7:
        return "orange"
    return "white"


def mark_record_clearance(record_id: int, status: str) -> None:
    init_db()
    clearance_at = datetime.now().isoformat(timespec="seconds") if status == "cleared" else None
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE export_clearance_records
            SET clearance_status = ?, clearance_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, clearance_at, datetime.now().isoformat(timespec="seconds"), record_id),
        )


def export_pending_workbook() -> BytesIO:
    rows = list_records(clearance_status="pending", sort_by="shipment_date")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "未清关货物"
    headers = ["出货日期", "TAN号", "板数", "箱数", "货值", "毛重"]
    worksheet.append(headers)

    fills = {
        "orange": openpyxl_styles.PatternFill(fill_type="solid", start_color="FFFFA500", end_color="FFFFA500"),
        "red": openpyxl_styles.PatternFill(fill_type="solid", start_color="FFFF4C4C", end_color="FFFF4C4C"),
    }

    for row in rows:
        worksheet.append(
            [
                row["shipment_date"],
                row["tan_number"],
                row["pallet_count"],
                row["carton_count"],
                row["total_value_usd"],
                row["gross_weight_kg"],
            ]
        )
        style = fills.get(row["urgency_color"])
        if style:
            excel_row = worksheet.max_row
            for col in range(1, 7):
                worksheet.cell(row=excel_row, column=col).fill = style

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def format_clearance_time(value: str) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")


def export_cleared_workbook(clear_date: date | None = None) -> BytesIO:
    init_db()
    target_date = clear_date or date.today()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.*, b.batch_code, b.tracker, b.manifest_code, b.shipment_date, b.trip_sequence
            FROM export_clearance_records r
            JOIN export_clearance_batches b ON b.id = r.batch_id
            WHERE r.clearance_status = 'cleared'
            ORDER BY r.clearance_at DESC, r.id DESC
            LIMIT 10000
            """
        ).fetchall()
    all_records = [format_record(row) for row in rows]
    daily_records = [
        row
        for row in all_records
        if row["clearance_at"] and datetime.fromisoformat(row["clearance_at"]).date() == target_date
    ]

    workbook = openpyxl.Workbook()
    ws_all = workbook.active
    ws_all.title = "全部已清关"
    ws_all.append(["清关时间", "出货时间", "Tan号", "车单编号", "提单号", "板数/箱数", "毛重", "货值", "目的国", "跟单员"])
    for row in all_records:
        ws_all.append(
            [
                format_clearance_time(row["clearance_at"]),
                row["shipment_date"],
                row["tan_number"],
                row["manifest_code"],
                "",
                format_pallet_carton_text(row["pallet_count"], row["carton_count"]),
                row["gross_weight_kg"],
                row["total_value_usd"],
                row["destination"],
                row["tracker"],
            ]
        )

    ws_detail = workbook.create_sheet("当日清关-明细")
    ws_detail.append(["出货时间", "Tan号", "提单号", "板数/箱数", "毛重", "货值"])
    for row in daily_records:
        ws_detail.append(
            [
                row["shipment_date"],
                row["tan_number"],
                "",
                format_pallet_carton_text(row["pallet_count"], row["carton_count"]),
                row["gross_weight_kg"],
                row["total_value_usd"],
            ]
        )

    ws_value = workbook.create_sheet("当日清关-货值")
    ws_value.append(["出货时间", "Tan号", "货值"])
    for row in daily_records:
        ws_value.append([row["shipment_date"], row["tan_number"], row["total_value_usd"]])

    ws_date = workbook.create_sheet("当日清关-日期")
    ws_date.append(["出货时间", "Tan号", "清关日期"])
    for row in daily_records:
        ws_date.append([row["shipment_date"], row["tan_number"], target_date.isoformat()])

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


from app.modules.export_clearance.rules import (
    export_record_business_key,
    format_pallet_carton_text,
    normalize_tan_number,
    urgency_sort_key,
)
