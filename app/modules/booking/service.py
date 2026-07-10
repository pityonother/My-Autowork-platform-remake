from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR, UPLOAD_DIR
from app.modules.booking.mail_builder import generate_flex_texas_booking_reply_eml, generate_sil_fuca_warehouse_eml
from app.shared.performance import timed_step
from app.shared.uploads import save_upload
from app.modules.booking.rules.registry import SUPPLIER_RULES
from app.modules.booking.schemas import BookingPreview


class BookingInputError(ValueError):
    pass


EML_SUFFIXES = {".eml"}
SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}
PDF_SUFFIXES = {".pdf"}
WAREHOUSE_SUFFIXES = SPREADSHEET_SUFFIXES | PDF_SUFFIXES


@dataclass
class BookingPreviewSession:
    session_id: str
    preview: BookingPreview
    customer_eml_path: Path | None
    warehouse_mail_ready: bool


def _supplier_uses_eml_pdf_source(supplier: str) -> bool:
    rule = SUPPLIER_RULES.get(supplier)
    return bool(rule and getattr(rule, "SOURCE_KIND", "") == "eml_pdf")


def eml_pdf_suppliers() -> set[str]:
    return {
        supplier
        for supplier, rule in SUPPLIER_RULES.items()
        if getattr(rule, "SOURCE_KIND", "") == "eml_pdf"
    }


def available_suppliers() -> list[str]:
    from app.modules.booking.legacy_adapter import available_suppliers as legacy_available_suppliers

    return legacy_available_suppliers()


def build_preview_session(
    *,
    supplier: str,
    customer_eml: UploadFile | None,
    source_file: UploadFile | None,
    packadc_file: UploadFile | None,
) -> BookingPreviewSession:
    from app.modules.booking.legacy_adapter import build_booking_preview, extract_booking_attachments_from_eml

    session_id = uuid.uuid4().hex[:12]
    warnings: list[str] = []
    email_subject = ""
    source_path: Path | None = None
    packadc_path: Path | None = None
    eml_path: Path | None = None

    if customer_eml and customer_eml.filename:
        eml_path = save_upload(session_id, customer_eml, "booking_customer", allowed_suffixes=EML_SUFFIXES)
        if _supplier_uses_eml_pdf_source(supplier):
            source_path = eml_path
        else:
            source_path, packadc_path, warnings, email_subject = extract_booking_attachments_from_eml(
                eml_path,
                UPLOAD_DIR / session_id / "booking_attachments",
            )
    if source_path is None and source_file and source_file.filename:
        source_path = save_upload(session_id, source_file, "booking_source", allowed_suffixes=SPREADSHEET_SUFFIXES)
    if packadc_path is None and packadc_file and packadc_file.filename:
        packadc_path = save_upload(session_id, packadc_file, "booking_packadc", allowed_suffixes=SPREADSHEET_SUFFIXES)
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
    from app.modules.booking.legacy_adapter import write_booking_workbook

    with timed_step("booking.write_workbook"):
        return write_booking_workbook(preview, OUTPUT_DIR)


def write_warehouse_mail(
    *,
    session_id: str,
    preview: BookingPreview,
    customer_eml_path: Path,
    warehouse_file: UploadFile,
) -> Path:
    warehouse_path = save_upload(session_id, warehouse_file, "booking_warehouse", allowed_suffixes=WAREHOUSE_SUFFIXES)
    output_path = OUTPUT_DIR / f"booking_warehouse_mail_{session_id}.eml"
    with timed_step("booking.write_warehouse_mail"):
        generate_sil_fuca_warehouse_eml(
            preview=preview,
            customer_eml_path=customer_eml_path,
            warehouse_file_path=warehouse_path,
            output_path=output_path,
        )
    return output_path


def write_flex_texas_reply_mail(
    *,
    session_id: str,
    preview: BookingPreview,
    customer_eml_path: Path,
    tms_pdf_file: UploadFile,
    body_text: str = "",
) -> Path:
    tms_pdf_path = save_upload(session_id, tms_pdf_file, "booking_flex_texas_tms_pdf", allowed_suffixes=PDF_SUFFIXES)
    output_path = OUTPUT_DIR / f"flex_texas_booking_reply_{session_id}.eml"
    with timed_step("booking.write_flex_texas_reply_mail"):
        generate_flex_texas_booking_reply_eml(
            preview=preview,
            customer_eml_path=customer_eml_path,
            tms_pdf_path=tms_pdf_path,
            output_path=output_path,
            body_text=body_text,
        )
    return output_path
