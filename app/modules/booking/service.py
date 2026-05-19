from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR, UPLOAD_DIR
from app.modules.booking.mail_builder import generate_sil_fuca_warehouse_eml
from app.shared.performance import timed_step
from app.shared.uploads import save_upload
from app.modules.booking.legacy_adapter import (
    BookingPreview,
    available_suppliers,
    build_booking_preview,
    extract_booking_attachments_from_eml,
    write_booking_workbook,
)


class BookingInputError(ValueError):
    pass


@dataclass
class BookingPreviewSession:
    session_id: str
    preview: BookingPreview
    customer_eml_path: Path | None
    warehouse_mail_ready: bool


def build_preview_session(
    *,
    supplier: str,
    customer_eml: UploadFile | None,
    source_file: UploadFile | None,
    packadc_file: UploadFile | None,
) -> BookingPreviewSession:
    session_id = uuid.uuid4().hex[:12]
    warnings: list[str] = []
    email_subject = ""
    source_path: Path | None = None
    packadc_path: Path | None = None
    eml_path: Path | None = None

    if customer_eml and customer_eml.filename:
        eml_path = save_upload(session_id, customer_eml, "booking_customer")
        source_path, packadc_path, warnings, email_subject = extract_booking_attachments_from_eml(
            eml_path,
            UPLOAD_DIR / session_id / "booking_attachments",
        )
    if source_path is None and source_file and source_file.filename:
        source_path = save_upload(session_id, source_file, "booking_source")
    if packadc_path is None and packadc_file and packadc_file.filename:
        packadc_path = save_upload(session_id, packadc_file, "booking_packadc")
    if source_path is None:
        raise BookingInputError("请上传客户原始 eml，或手动上传 CCIXLS 文件。")

    with timed_step("booking.build_preview"):
        preview = build_booking_preview(
            session_id=session_id,
            supplier=supplier,
            source_path=source_path,
            packadc_path=packadc_path,
            email_subject=email_subject,
        )
    preview.warnings = warnings + preview.warnings
    return BookingPreviewSession(
        session_id=session_id,
        preview=preview,
        customer_eml_path=eml_path,
        warehouse_mail_ready=bool(eml_path and supplier == "SIL-FUCA"),
    )


def write_booking_output(preview: BookingPreview) -> Path:
    with timed_step("booking.write_workbook"):
        return write_booking_workbook(preview, OUTPUT_DIR)


def write_warehouse_mail(
    *,
    session_id: str,
    preview: BookingPreview,
    customer_eml_path: Path,
    warehouse_file: UploadFile,
) -> Path:
    warehouse_path = save_upload(session_id, warehouse_file, "booking_warehouse")
    output_path = OUTPUT_DIR / f"booking_warehouse_mail_{session_id}.eml"
    with timed_step("booking.write_warehouse_mail"):
        generate_sil_fuca_warehouse_eml(
            preview=preview,
            customer_eml_path=customer_eml_path,
            warehouse_file_path=warehouse_path,
            output_path=output_path,
        )
    return output_path
