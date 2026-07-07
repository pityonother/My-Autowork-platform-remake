from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR
from app.modules.finance import exports, repository
from app.modules.finance.parsers import parse_exchange_rate
from app.shared.performance import timed_step
from app.shared.uploads import save_upload


SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}


def import_payment_file(payment_file: UploadFile) -> dict:
    from app.modules.finance.legacy_adapter import FinanceImportInput, import_finance_batch

    session_id = uuid.uuid4().hex[:12]
    payment_path = save_upload(session_id, payment_file, "payment", allowed_suffixes=SPREADSHEET_SUFFIXES)
    with timed_step("finance.import_payment_file"):
        return import_finance_batch(FinanceImportInput(payment_path=payment_path))


def preview_export_rows(
    *,
    exchange_rate: str,
    category: str,
    batch_id: int | None,
    currency: str | None,
    task_status: str | None,
    date_from: str | None,
    date_to: str | None,
    only_exportable: bool,
    only_invoice_required: bool,
) -> tuple[list, str]:
    if not exchange_rate:
        return [], ""
    try:
        rate = parse_exchange_rate(exchange_rate)
        if rate is None:
            raise ValueError("请输入有效汇率。")
        if category and category != "fy_export":
            return [], ""
        return (
            exports.build_finance_export_rows(
                exchange_rate=rate,
                batch_id=batch_id,
                currency=currency,
                task_status=task_status,
                date_from=date_from,
                date_to=date_to,
                only_exportable=only_exportable,
                only_invoice_required=only_invoice_required,
            ),
            "",
        )
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)


def export_outbound_bill(
    *,
    bill_file: UploadFile,
    exchange_rate: str,
    batch_id: int | None,
    currency: str | None,
    category: str,
    task_status: str | None,
    date_from: str | None,
    date_to: str | None,
    only_exportable: bool,
    only_invoice_required: bool,
) -> Path:
    rate = parse_exchange_rate(exchange_rate)
    if rate is None or rate <= 0:
        raise ValueError("请输入大于 0 的汇率。")
    session_id = uuid.uuid4().hex[:12]
    bill_path = save_upload(session_id, bill_file, "finance_bill", allowed_suffixes=SPREADSHEET_SUFFIXES)
    rows = []
    if not category or category == "fy_export":
        rows = exports.build_finance_export_rows(
            exchange_rate=rate,
            batch_id=batch_id,
            currency=currency,
            task_status=task_status,
            date_from=date_from,
            date_to=date_to,
            only_exportable=only_exportable,
            only_invoice_required=only_invoice_required,
        )
    if not rows:
        raise ValueError("当前没有可导出到 OUTBOUND 的福永伟创力代支记录。")
    output_path = OUTPUT_DIR / f"finance_outbound_{session_id}.xls"
    with timed_step("finance.export_outbound_bill"):
        processed_record_ids = exports.export_finance_outbound_bill(bill_path, rows, output_path)
    repository.mark_finance_records_exported(processed_record_ids)
    return output_path
