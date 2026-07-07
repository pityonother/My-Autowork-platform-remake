from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile

from app.shared.performance import timed_step
from app.shared.uploads import save_upload


SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}


def import_clearance_batch(
    *,
    tracker: str,
    manifest_code: str,
    shipment_date: date,
    trip_sequence: int,
    source_files: Sequence[UploadFile],
) -> dict:
    from app.modules.export_clearance.legacy_adapter import ExportClearanceImportInput, import_export_clearance_batch

    session_id = uuid.uuid4().hex[:12]
    source_paths: list[Path] = [
        save_upload(session_id, item, f"export_source_{idx:03d}", allowed_suffixes=SPREADSHEET_SUFFIXES)
        for idx, item in enumerate(source_files, start=1)
        if item.filename
    ]
    if not source_paths:
        raise ValueError("请至少上传一个出口清关数据文件。")
    with timed_step("export_clearance.import_batch"):
        return import_export_clearance_batch(
            ExportClearanceImportInput(
                tracker=tracker.strip(),
                manifest_code=manifest_code.strip(),
                shipment_date=shipment_date,
                trip_sequence=trip_sequence,
                source_files=source_paths,
            )
        )
