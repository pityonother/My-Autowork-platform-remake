from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.core.paths import OUTPUT_DIR
from app.modules.booking.flex_texas import export_flex_texas_source_pdf_tiff
from app.modules.booking.schemas import BookingPreview
from app.modules.booking.service import (
    BookingInputError,
    build_preview_session,
    eml_pdf_suppliers,
    write_flex_texas_reply_mail,
    write_booking_output,
    write_warehouse_mail,
)
from app.modules.booking.service import available_suppliers
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()
LOCK_SUPPLIER_ENV_VAR = "BOOKING_LOCK_SUPPLIER"


def open_review_tiff(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    raise RuntimeError("当前系统不是 Windows，无法调用 Windows 照片查看器。")


def locked_supplier() -> str:
    supplier = os.environ.get(LOCK_SUPPLIER_ENV_VAR, "").strip()
    return supplier if supplier in available_suppliers() else ""


def resolve_selected_supplier(supplier: str) -> str:
    locked = locked_supplier()
    if locked:
        return locked
    return supplier if supplier in available_suppliers() else "SIL-FUCA"


def booking_page_context(
    *,
    selected_supplier: str = "SIL-FUCA",
    preview: BookingPreview | None = None,
    error: str = "",
    warehouse_mail_ready: bool = False,
) -> dict[str, Any]:
    supplier_options = available_suppliers()
    locked = locked_supplier()
    if locked:
        selected_supplier = locked
        supplier_options = [locked]
    elif selected_supplier in eml_pdf_suppliers():
        supplier_options = [selected_supplier]
    return {
        "suppliers": supplier_options,
        "eml_pdf_suppliers": eml_pdf_suppliers(),
        "selected_supplier": selected_supplier,
        "preview": preview,
        "error": error,
        "warehouse_mail_ready": warehouse_mail_ready,
    }


@router.get("/modules/booking", response_class=HTMLResponse)
async def booking_page(request: Request, supplier: str = "SIL-FUCA") -> HTMLResponse:
    selected_supplier = resolve_selected_supplier(supplier)
    return templates.TemplateResponse(request, "booking.html", booking_page_context(selected_supplier=selected_supplier))


@router.post("/modules/booking/preview", response_class=HTMLResponse)
async def preview_booking(
    request: Request,
    supplier: str = Form(...),
    auto_generate: str = Form("0"),
    customer_eml: UploadFile | None = File(default=None),
    source_file: UploadFile | None = File(default=None),
    packadc_file: UploadFile | None = File(default=None),
) -> Response:
    supplier = resolve_selected_supplier(supplier)
    try:
        preview_session = build_preview_session(
            supplier=supplier,
            customer_eml=customer_eml,
            source_file=source_file,
            packadc_file=packadc_file,
        )
    except BookingInputError as exc:
        return templates.TemplateResponse(
            request,
            "booking.html",
            booking_page_context(selected_supplier=supplier, error=str(exc)),
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "booking.html",
            booking_page_context(selected_supplier=supplier, error=str(exc)),
            status_code=400,
        )

    SESSION_STORE[preview_session.session_id] = {
        "booking_preview": preview_session.preview,
        "booking_customer_eml_path": str(preview_session.customer_eml_path or ""),
    }
    if supplier in eml_pdf_suppliers() and preview_session.customer_eml_path:
        try:
            tiff_path = OUTPUT_DIR / f"flex_texas_pdf_review_{preview_session.session_id}.tif"
            export_flex_texas_source_pdf_tiff(preview_session.customer_eml_path, tiff_path)
            open_review_tiff(tiff_path)
            SESSION_STORE[preview_session.session_id]["booking_pdf_tiff_path"] = str(tiff_path)
        except Exception as exc:  # noqa: BLE001
            preview_session.preview.warnings.append(f"PDF 转 TIF 或打开 Windows 照片查看器失败：{exc}")
    if auto_generate == "1" and supplier not in eml_pdf_suppliers() and preview_session.preview.can_generate:
        try:
            output_path = write_booking_output(preview_session.preview)
        except Exception as exc:  # noqa: BLE001
            return templates.TemplateResponse(
                request,
                "booking.html",
                booking_page_context(selected_supplier=supplier, preview=preview_session.preview, error=str(exc)),
                status_code=400,
            )
        return FileResponse(
            output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return templates.TemplateResponse(
        request,
        "booking.html",
        booking_page_context(
            selected_supplier=supplier,
            preview=preview_session.preview,
            warehouse_mail_ready=preview_session.warehouse_mail_ready,
        ),
    )


def get_booking_preview(session_id: str) -> BookingPreview:
    session = SESSION_STORE.get_required(session_id)
    preview = session.get("booking_preview")
    if not isinstance(preview, BookingPreview):
        raise HTTPException(status_code=404, detail="未找到 Booking 预览记录。")
    return preview


@router.post("/modules/booking/generate/{session_id}")
async def generate_booking(session_id: str) -> FileResponse:
    return generate_booking_file_response(session_id)


@router.get("/modules/booking/generate/{session_id}")
async def download_booking(session_id: str) -> FileResponse:
    return generate_booking_file_response(session_id)


def generate_booking_file_response(session_id: str) -> FileResponse:
    preview = get_booking_preview(session_id)
    try:
        output_path = write_booking_output(preview)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        output_path,
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/modules/booking/warehouse-mail/{session_id}")
async def generate_booking_warehouse_mail(session_id: str, warehouse_file: UploadFile = File(...)) -> FileResponse:
    if not warehouse_file.filename:
        raise HTTPException(status_code=400, detail="请上传做好的入仓文件。")
    session = SESSION_STORE.get_required(session_id)
    preview = get_booking_preview(session_id)
    customer_eml_text = str(session.get("booking_customer_eml_path") or "").strip()
    if not customer_eml_text:
        raise HTTPException(status_code=400, detail="当前预览没有关联客户原始 eml，无法生成入仓邮件。")
    try:
        output_path = write_warehouse_mail(
            session_id=session_id,
            preview=preview,
            customer_eml_path=Path(customer_eml_text),
            warehouse_file=warehouse_file,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(output_path, filename=output_path.name, media_type="message/rfc822")


@router.post("/modules/booking/flex-texas-reply-mail/{session_id}")
async def generate_flex_texas_reply_mail(
    session_id: str,
    tms_pdf_file: UploadFile = File(...),
    body_text: str = Form(""),
) -> FileResponse:
    if not tms_pdf_file.filename:
        raise HTTPException(status_code=400, detail="请上传 TMS 导出的 PDF 文件。")
    session = SESSION_STORE.get_required(session_id)
    preview = get_booking_preview(session_id)
    if preview.supplier != "FLEX-TEXAS":
        raise HTTPException(status_code=400, detail="当前功能只支持 FLEX-TEXAS。")
    customer_eml_text = str(session.get("booking_customer_eml_path") or "").strip()
    if not customer_eml_text:
        raise HTTPException(status_code=400, detail="当前预览没有关联客户原始 eml，无法生成回复邮件。")
    try:
        output_path = write_flex_texas_reply_mail(
            session_id=session_id,
            preview=preview,
            customer_eml_path=Path(customer_eml_text),
            tms_pdf_file=tms_pdf_file,
            body_text=body_text,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(output_path, filename=output_path.name, media_type="message/rfc822")
