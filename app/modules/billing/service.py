from __future__ import annotations

import uuid
from typing import Sequence

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR
from app.modules.billing.legacy_adapter import ReconcileOutput, reconcile, slt_sort_key
from app.shared.state import SESSION_STORE
from app.shared.uploads import save_upload


SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}
DOCUMENT_SUFFIXES = SPREADSHEET_SUFFIXES | {".pdf"}


def build_billing_session(
    *,
    master_file: UploadFile | None,
    invoice_files: Sequence[UploadFile],
    delivery_note_files: Sequence[UploadFile],
    source_files: Sequence[UploadFile],
) -> str:
    session_id = uuid.uuid4().hex[:12]
    master_path = (
        save_upload(session_id, master_file, "master", allowed_suffixes=SPREADSHEET_SUFFIXES)
        if master_file and master_file.filename
        else None
    )
    invoice_paths = [
        save_upload(session_id, item, f"invoice_{idx:03d}", allowed_suffixes=DOCUMENT_SUFFIXES)
        for idx, item in enumerate(invoice_files, start=1)
        if item.filename
    ]
    delivery_paths = [
        save_upload(session_id, item, f"delivery_{idx:03d}", allowed_suffixes=DOCUMENT_SUFFIXES)
        for idx, item in enumerate(delivery_note_files, start=1)
        if item.filename
    ]
    source_paths = [
        save_upload(session_id, item, f"source_{idx:03d}", allowed_suffixes=SPREADSHEET_SUFFIXES)
        for idx, item in enumerate(source_files, start=1)
        if item.filename
    ]
    if not master_path or not invoice_paths:
        raise ValueError("做账单至少需要上传空白账单格式和单页账单。")

    output_path = OUTPUT_DIR / f"reconciled_{session_id}.xlsx"
    result = reconcile(
        master_path=master_path,
        invoice_paths=invoice_paths,
        delivery_note_paths=delivery_paths,
        source_paths=source_paths,
        output_path=output_path,
    )
    SESSION_STORE[session_id] = {
        "master_name": master_file.filename if master_file else "",
        "invoice_count": len(invoice_paths),
        "delivery_note_count": len(delivery_paths),
        "source_count": len(source_paths),
        "result": result,
    }
    return session_id


def get_sorted_invoice_previews(session: dict) -> list[dict]:
    result: ReconcileOutput | None = session.get("result")
    if not result:
        return []
    return sorted(
        result.invoice_previews,
        key=lambda item: slt_sort_key(item.get("customer_order_no", "")),
    )
