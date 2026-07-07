from __future__ import annotations

import uuid
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR
from app.shared.performance import timed_step
from app.shared.state import SESSION_STORE
from app.shared.uploads import save_upload


SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}


def build_import_customs_session(
    *,
    order_management_file: UploadFile | None,
    customs_bill_file: UploadFile | None,
    source_files: Sequence[UploadFile],
) -> str:
    from app.modules.import_customs.legacy_adapter import reconcile_customs

    session_id = uuid.uuid4().hex[:12]
    order_management_path = (
        save_upload(session_id, order_management_file, "order_management", allowed_suffixes=SPREADSHEET_SUFFIXES)
        if order_management_file and order_management_file.filename
        else None
    )
    customs_bill_path = (
        save_upload(session_id, customs_bill_file, "customs_bill", allowed_suffixes=SPREADSHEET_SUFFIXES)
        if customs_bill_file and customs_bill_file.filename
        else None
    )
    source_paths: list[Path] = [
        save_upload(session_id, item, f"source_{idx:03d}", allowed_suffixes=SPREADSHEET_SUFFIXES)
        for idx, item in enumerate(source_files, start=1)
        if item.filename
    ]
    if not order_management_path or not source_paths:
        raise ValueError("香港进口清关至少需要订单管理和真实数据源。")

    customs_preview_path = OUTPUT_DIR / f"customs_preview_{session_id}.xlsx"
    customs_bill_output_path = OUTPUT_DIR / f"customs_bill_{session_id}.xls" if customs_bill_path else None
    with timed_step("import_customs.reconcile"):
        customs_result = reconcile_customs(
            order_management_path=order_management_path,
            source_paths=source_paths,
            bill_template_path=customs_bill_path,
            preview_output_path=customs_preview_path,
            bill_output_path=customs_bill_output_path,
        )
    SESSION_STORE[session_id] = {
        "source_count": len(source_paths),
        "order_management_name": order_management_file.filename if order_management_file else "",
        "customs_bill_name": customs_bill_file.filename if customs_bill_file else "",
        "customs_result": customs_result,
    }
    return session_id
