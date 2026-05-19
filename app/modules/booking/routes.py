from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app.modules.booking.schemas import BookingPreview
from app.modules.booking.service import BookingInputError, build_preview_session, write_booking_output, write_warehouse_mail
from app.modules.booking.service import available_suppliers
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()


def booking_page_context(
    *,
    selected_supplier: str = "SIL-FUCA",
    preview: BookingPreview | None = None,
    error: str = "",
    warehouse_mail_ready: bool = False,
) -> dict[str, Any]:
    return {
        "suppliers": available_suppliers(),
        "selected_supplier": selected_supplier,
        "preview": preview,
        "error": error,
        "warehouse_mail_ready": warehouse_mail_ready,
    }


@router.get("/modules/booking", response_class=HTMLResponse)
async def booking_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "booking.html", booking_page_context())


@router.post("/modules/booking/preview", response_class=HTMLResponse)
async def preview_booking(
    request: Request,
    supplier: str = Form(...),
    customer_eml: UploadFile | None = File(default=None),
    source_file: UploadFile | None = File(default=None),
    packadc_file: UploadFile | None = File(default=None),
) -> HTMLResponse:
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
