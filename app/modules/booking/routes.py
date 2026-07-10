from __future__ import annotations

import os
import base64
import hashlib
import hmac
import re
import secrets
import uuid
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from app.core.paths import OUTPUT_DIR, RUNTIME_DIR
from app.modules.booking.body_validation import (
    BODY_FIELDS,
    ManualBodyValues,
    build_body_validation_preview,
    build_corrected_body_validation_workbook,
)
from app.modules.booking.flex_texas import export_flex_texas_source_pdf_tiff
from app.modules.booking.schemas import BookingPreview
from app.modules.booking.sil_fuca_delivery import (
    SilFucaDeliveryClient,
    get_all_delivery_list_cache_status,
    refresh_all_delivery_list_if_needed,
)
from app.modules.booking.service import (
    BookingInputError,
    build_preview_session,
    eml_pdf_suppliers,
    write_flex_texas_reply_mail,
    write_booking_output,
    write_warehouse_mail,
)
from app.modules.booking.service import available_suppliers
from app.shared.uploads import UploadValidationError, read_upload_limited
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()
LOCK_SUPPLIER_ENV_VAR = "BOOKING_LOCK_SUPPLIER"
BOOKING_SESSION_DIR = RUNTIME_DIR / "booking_sessions"
BOOKING_SESSION_SECRET_ENV = "MY_AUTOWORK_BOOKING_SESSION_SECRET"
BOOKING_SESSION_SECRET_FILENAME = ".booking_session_secret"
BODY_VALIDATION_EXPORT_DIR = RUNTIME_DIR / "booking_body_validation_exports"
BODY_VALIDATION_UPLOAD_DIR = RUNTIME_DIR / "booking_body_validation_uploads"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,80}$")
BODY_VALIDATION_EXPORT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+\.xlsx$")
BODY_VALIDATION_UPLOAD_PATTERN = re.compile(r"^[0-9a-f]{32}$")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EML_MEDIA_TYPE = "message/rfc822"
BODY_VALIDATION_SUFFIXES = {".xlsx"}


def open_review_tiff(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    raise RuntimeError("当前系统不是 Windows，无法调用 Windows 照片查看器。")


def tiff_review_url(preview: BookingPreview | None) -> str:
    if preview is None or preview.supplier not in eml_pdf_suppliers():
        return ""
    session = SESSION_STORE.get(preview.session_id, {})
    tiff_path = Path(str(session.get("booking_pdf_tiff_path") or ""))
    if not tiff_path.is_file():
        return ""
    return f"/modules/booking/flex-texas-review-tiff/{preview.session_id}"


def locked_supplier() -> str:
    supplier = os.environ.get(LOCK_SUPPLIER_ENV_VAR, "").strip()
    return supplier if supplier in available_suppliers() else ""


def resolve_selected_supplier(supplier: str) -> str:
    locked = locked_supplier()
    if locked:
        return locked
    return supplier if supplier in available_suppliers() else "SIL-FUCA"


def booking_session_path(session_id: str) -> Path:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status_code=404, detail="未找到这次导入记录。")
    return BOOKING_SESSION_DIR / f"{session_id}.json"


def booking_session_secret() -> bytes:
    env_secret = os.environ.get(BOOKING_SESSION_SECRET_ENV, "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    BOOKING_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = BOOKING_SESSION_DIR / BOOKING_SESSION_SECRET_FILENAME
    if not secret_path.is_file():
        secret_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return secret_path.read_text(encoding="utf-8").strip().encode("utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, SimpleNamespace):
        return _json_safe(vars(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _namespace_tree(value: Any) -> Any:
    if isinstance(value, list):
        return [_namespace_tree(item) for item in value]
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _namespace_tree(item) for key, item in value.items()})
    return value


def _booking_preview_to_payload(preview: BookingPreview) -> dict[str, Any]:
    return _json_safe(preview)


def _booking_preview_from_payload(payload: Any) -> BookingPreview | None:
    if not isinstance(payload, dict):
        return None
    data = dict(payload)
    output_path = str(data.get("output_path") or "").strip()
    data["output_path"] = Path(output_path) if output_path else None
    data["validation_sections"] = _namespace_tree(data.get("validation_sections", []))
    try:
        return BookingPreview(**data)
    except TypeError:
        return None


def _normalize_booking_preview(value: Any) -> BookingPreview | None:
    if isinstance(value, BookingPreview):
        return value
    return _booking_preview_from_payload(_json_safe(value))


def _booking_session_to_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in data.items():
        if key == "booking_preview":
            preview = _normalize_booking_preview(value)
            payload[key] = _booking_preview_to_payload(preview) if preview is not None else _json_safe(value)
        else:
            payload[key] = _json_safe(value)
    return payload


def _booking_session_from_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = dict(payload)
    if "booking_preview" in data:
        preview = _booking_preview_from_payload(data.get("booking_preview"))
        if preview is None:
            return None
        data["booking_preview"] = preview
    return data


def signed_booking_session_bytes(data: dict[str, Any]) -> bytes:
    payload = json.dumps(_booking_session_to_payload(data), ensure_ascii=False).encode("utf-8")
    digest = hmac.new(booking_session_secret(), payload, hashlib.sha256).hexdigest()
    envelope = {
        "version": 1,
        "payload": base64.b64encode(payload).decode("ascii"),
        "hmac": digest,
    }
    return json.dumps(envelope, ensure_ascii=False).encode("utf-8")


def load_signed_booking_session(raw: bytes) -> dict[str, Any] | None:
    try:
        envelope = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict):
            return None
        payload_text = str(envelope.get("payload", ""))
        supplied_digest = str(envelope.get("hmac", ""))
        payload = base64.b64decode(payload_text.encode("ascii"), validate=True)
        expected_digest = hmac.new(booking_session_secret(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_digest, expected_digest):
            return None
        data = _booking_session_from_payload(json.loads(payload.decode("utf-8")))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def persist_booking_session(session_id: str, data: dict[str, Any]) -> None:
    BOOKING_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    target_path = booking_session_path(session_id)
    temp_path = target_path.with_suffix(".tmp")
    temp_path.write_bytes(signed_booking_session_bytes(data))
    temp_path.replace(target_path)


def restore_booking_session(session_id: str) -> dict[str, Any] | None:
    path = booking_session_path(session_id)
    if not path.is_file():
        return None
    data = load_signed_booking_session(path.read_bytes())
    if data is None:
        return None
    SESSION_STORE[session_id] = data
    return data


def get_booking_session(session_id: str) -> dict[str, Any]:
    if session_id in SESSION_STORE and SESSION_STORE[session_id]:
        return SESSION_STORE[session_id]
    restored = restore_booking_session(session_id)
    if restored:
        return restored
    raise HTTPException(status_code=404, detail="未找到 Booking 预览记录。")


def attachment_response(path: Path, *, filename: str, media_type: str) -> FileResponse:
    return FileResponse(
        path,
        filename=filename,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def safe_body_validation_export_name(filename: str, export_id: str) -> str:
    stem = Path(filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-") or "booking"
    return f"{safe_stem}_corrected_{export_id}.xlsx"


def body_validation_export_path(export_name: str) -> Path:
    if not BODY_VALIDATION_EXPORT_PATTERN.fullmatch(export_name):
        raise HTTPException(status_code=404, detail="未找到主体数据修正版文件。")
    return BODY_VALIDATION_EXPORT_DIR / export_name


def build_sil_fuca_delivery_client(*, force_refresh_all: bool = False) -> SilFucaDeliveryClient:
    return SilFucaDeliveryClient(force_refresh_all=force_refresh_all)


def write_body_validation_export(
    workbook_bytes: bytes,
    *,
    filename: str,
    enable_dynamic_checks: bool = False,
    sil_fuca_delivery_client: SilFucaDeliveryClient | None = None,
    manual_values: ManualBodyValues | None = None,
) -> Path:
    BODY_VALIDATION_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_id = uuid.uuid4().hex[:12]
    output_path = body_validation_export_path(safe_body_validation_export_name(filename, export_id))
    output_path.write_bytes(
        build_corrected_body_validation_workbook(
            workbook_bytes,
            filename=filename,
            enable_dynamic_checks=enable_dynamic_checks,
            sil_fuca_delivery_client=sil_fuca_delivery_client,
            manual_values=manual_values,
        )
    )
    return output_path


def parse_body_validation_manual_values(raw: str) -> ManualBodyValues:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("人工确认值格式错误，请重新确认修正建议。") from exc
    if not isinstance(payload, dict):
        raise ValueError("人工确认值格式错误，请重新确认修正建议。")
    allowed_fields = {field.code for field in BODY_FIELDS}
    values: ManualBodyValues = {}
    for row_key, row_values in payload.items():
        try:
            excel_row = int(row_key)
        except (TypeError, ValueError) as exc:
            raise ValueError("人工确认值包含无效行号。") from exc
        if not isinstance(row_values, dict):
            raise ValueError("人工确认值格式错误，请重新确认修正建议。")
        for field_code, value in row_values.items():
            if field_code in allowed_fields:
                values[(excel_row, field_code)] = str(value or "").strip()
    return values


def body_validation_upload_paths(session_id: str) -> tuple[Path, Path]:
    if not BODY_VALIDATION_UPLOAD_PATTERN.fullmatch(session_id):
        raise FileNotFoundError("未找到上传文件缓存。")
    return BODY_VALIDATION_UPLOAD_DIR / f"{session_id}.xlsx", BODY_VALIDATION_UPLOAD_DIR / f"{session_id}.json"


def write_body_validation_upload(
    content: bytes,
    *,
    filename: str,
    origin_booking_session_id: str = "",
) -> str:
    BODY_VALIDATION_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex
    workbook_path, meta_path = body_validation_upload_paths(session_id)
    workbook_path.write_bytes(content)
    metadata = {"filename": filename}
    origin_session_id = origin_booking_session_id.strip()
    if origin_session_id and SESSION_ID_PATTERN.fullmatch(origin_session_id):
        metadata["origin_booking_session_id"] = origin_session_id
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return session_id


def read_body_validation_upload_metadata(session_id: str) -> dict[str, Any]:
    _, meta_path = body_validation_upload_paths(session_id)
    if not meta_path.is_file():
        raise FileNotFoundError("未找到上传文件缓存，请重新选择 booking form。")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("上传文件缓存信息无效，请重新选择 booking form。")
    return metadata


def read_body_validation_upload(session_id: str) -> tuple[bytes, str]:
    workbook_path, meta_path = body_validation_upload_paths(session_id)
    if not workbook_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError("未找到上传文件缓存，请重新选择 booking form。")
    metadata = read_body_validation_upload_metadata(session_id)
    return workbook_path.read_bytes(), str(metadata.get("filename") or workbook_path.name)


def sil_fuca_warehouse_mail_ready(session: dict[str, Any], preview: BookingPreview) -> bool:
    if preview.supplier != "SIL-FUCA":
        return False
    customer_eml_text = str(session.get("booking_customer_eml_path") or "").strip()
    return bool(customer_eml_text and Path(customer_eml_text).is_file())


def body_validation_booking_return_url(validation_session_id: str) -> str:
    try:
        metadata = read_body_validation_upload_metadata(validation_session_id)
        origin_session_id = str(metadata.get("origin_booking_session_id") or "").strip()
        if not SESSION_ID_PATTERN.fullmatch(origin_session_id):
            return ""
        session = get_booking_session(origin_session_id)
        preview = get_booking_preview(origin_session_id)
    except (HTTPException, OSError, ValueError, json.JSONDecodeError):
        return ""
    if preview.session_id != origin_session_id or not sil_fuca_warehouse_mail_ready(session, preview):
        return ""
    return f"/modules/booking/preview/{origin_session_id}"


def body_validation_context(
    *,
    preview: Any = None,
    suggestion_preview: Any = None,
    export_url: str = "",
    error: str = "",
    validation_session_id: str = "",
    booking_return_url: str = "",
    delivery_cache_status: Any = None,
) -> dict[str, Any]:
    return {
        "preview": preview,
        "suggestion_preview": suggestion_preview,
        "export_url": export_url,
        "error": error,
        "validation_session_id": validation_session_id,
        "booking_return_url": booking_return_url,
        "delivery_cache_status": delivery_cache_status or get_all_delivery_list_cache_status(),
    }


def booking_page_context(
    *,
    selected_supplier: str = "SIL-FUCA",
    preview: BookingPreview | None = None,
    error: str = "",
    warehouse_mail_ready: bool = False,
) -> dict[str, Any]:
    eml_pdf_supplier_names = eml_pdf_suppliers()
    supplier_options = [
        supplier for supplier in available_suppliers()
        if supplier not in eml_pdf_supplier_names
    ]
    locked = locked_supplier()
    if locked:
        selected_supplier = locked
        supplier_options = [locked]
    elif selected_supplier in eml_pdf_supplier_names:
        supplier_options = [selected_supplier]
    return {
        "suppliers": supplier_options,
        "eml_pdf_suppliers": eml_pdf_supplier_names,
        "selected_supplier": selected_supplier,
        "preview": preview,
        "error": error,
        "warehouse_mail_ready": warehouse_mail_ready,
        "tiff_review_url": tiff_review_url(preview),
    }


@router.get("/modules/booking", response_class=HTMLResponse)
async def booking_page(request: Request, supplier: str = "SIL-FUCA") -> HTMLResponse:
    selected_supplier = resolve_selected_supplier(supplier)
    return templates.TemplateResponse(request, "booking.html", booking_page_context(selected_supplier=selected_supplier))


@router.get("/modules/booking/body-validation", response_class=HTMLResponse)
async def booking_body_validation_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "booking_body_validation.html",
        body_validation_context(),
    )


@router.get("/modules/booking/body-validation/from-preview/{session_id}", response_class=HTMLResponse)
async def booking_body_validation_from_preview(request: Request, session_id: str) -> HTMLResponse:
    booking_return_url = ""
    try:
        preview = get_booking_preview(session_id)
        if not preview.can_generate:
            raise BookingInputError("当前 Booking 预览存在错误，无法生成 booking form 进入质检。")
        output_path = write_booking_output(preview)
        content = output_path.read_bytes()
        validation_session_id = write_body_validation_upload(
            content,
            filename=output_path.name,
            origin_booking_session_id=session_id if preview.supplier == "SIL-FUCA" else "",
        )
        booking_return_url = body_validation_booking_return_url(validation_session_id)
        body_preview = build_body_validation_preview(
            content,
            filename=output_path.name,
            apply_fixes=False,
            enable_dynamic_checks=False,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "booking_body_validation.html",
            body_validation_context(error=str(exc), booking_return_url=booking_return_url),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "booking_body_validation.html",
        body_validation_context(
            preview=body_preview,
            validation_session_id=validation_session_id,
            booking_return_url=booking_return_url,
        ),
    )


@router.get("/modules/booking/body-validation/session/{session_id}", response_class=HTMLResponse)
async def booking_body_validation_session_page(request: Request, session_id: str) -> HTMLResponse:
    booking_return_url = body_validation_booking_return_url(session_id)
    try:
        content, filename = read_body_validation_upload(session_id)
        preview = build_body_validation_preview(
            content,
            filename=filename,
            apply_fixes=False,
            enable_dynamic_checks=False,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "booking_body_validation.html",
            body_validation_context(
                error=str(exc),
                validation_session_id=session_id,
                booking_return_url=booking_return_url,
            ),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "booking_body_validation.html",
        body_validation_context(
            preview=preview,
            validation_session_id=session_id,
            booking_return_url=booking_return_url,
        ),
    )


@router.post("/modules/booking/body-validation/extension-upload")
async def booking_body_validation_extension_upload(
    request: Request,
    booking_file: UploadFile = File(...),
) -> Response:
    if not booking_file.filename:
        raise HTTPException(status_code=400, detail="请上传 booking form xlsx 文件。")
    filename = booking_file.filename
    try:
        content = await read_upload_limited(booking_file, allowed_suffixes=BODY_VALIDATION_SUFFIXES)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_id = write_body_validation_upload(content, filename=filename)
    session_url = f"/modules/booking/body-validation/session/{session_id}"
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"url": session_url})
    return RedirectResponse(
        url=session_url,
        status_code=303,
    )


@router.post("/modules/booking/body-validation", response_class=HTMLResponse)
async def preview_booking_body_validation(
    request: Request,
    booking_file: UploadFile | None = File(None),
    apply_fixes: str = Form("0"),
    validation_session_id: str = Form(""),
    refresh_delivery_list: str = Form("0"),
    confirm_export: str = Form("0"),
    manual_values_json: str = Form(""),
) -> HTMLResponse:
    session_id = validation_session_id.strip()
    booking_return_url = ""
    if not booking_file and not session_id:
        return templates.TemplateResponse(
            request,
            "booking_body_validation.html",
            body_validation_context(error="请上传 booking form xlsx 文件。"),
            status_code=400,
        )
    try:
        if booking_file and booking_file.filename:
            filename = booking_file.filename
            content = await read_upload_limited(booking_file, allowed_suffixes=BODY_VALIDATION_SUFFIXES)
            session_id = write_body_validation_upload(content, filename=filename)
        else:
            content, filename = read_body_validation_upload(session_id)
        booking_return_url = body_validation_booking_return_url(session_id)

        use_fixes = apply_fixes == "1"
        if use_fixes and refresh_delivery_list == "1":
            refresh_all_delivery_list_if_needed(force=True)
        sil_fuca_delivery_client = (
            build_sil_fuca_delivery_client(force_refresh_all=refresh_delivery_list == "1") if use_fixes else None
        )
        preview = build_body_validation_preview(
            content,
            filename=filename,
            apply_fixes=use_fixes,
            enable_dynamic_checks=use_fixes,
            sil_fuca_delivery_client=sil_fuca_delivery_client,
        )
        suggestion_preview = preview if use_fixes else None
        export_url = ""
        if use_fixes and confirm_export == "1":
            manual_values = parse_body_validation_manual_values(manual_values_json)
            export_path = write_body_validation_export(
                content,
                filename=filename,
                enable_dynamic_checks=True,
                sil_fuca_delivery_client=sil_fuca_delivery_client,
                manual_values=manual_values,
            )
            export_url = f"/modules/booking/body-validation/export/{export_path.name}"
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "booking_body_validation.html",
            body_validation_context(
                error=str(exc),
                validation_session_id=session_id,
                booking_return_url=booking_return_url,
            ),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "booking_body_validation.html",
        body_validation_context(
            preview=preview,
            suggestion_preview=suggestion_preview,
            export_url=export_url,
            validation_session_id=session_id,
            booking_return_url=booking_return_url,
        ),
    )


@router.get("/modules/booking/body-validation/export/{export_name}")
async def download_booking_body_validation_export(export_name: str) -> FileResponse:
    output_path = body_validation_export_path(export_name)
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="未找到主体数据修正版文件。")
    return attachment_response(output_path, filename=output_path.name, media_type=XLSX_MEDIA_TYPE)


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

    session_data = {
        "booking_preview": preview_session.preview,
        "booking_customer_eml_path": str(preview_session.customer_eml_path or ""),
    }
    SESSION_STORE[preview_session.session_id] = session_data
    if supplier in eml_pdf_suppliers() and preview_session.customer_eml_path:
        try:
            tiff_path = OUTPUT_DIR / f"flex_texas_pdf_review_{preview_session.session_id}.tif"
            export_flex_texas_source_pdf_tiff(preview_session.customer_eml_path, tiff_path)
            session_data["booking_pdf_tiff_path"] = str(tiff_path)
            if os.name == "nt":
                open_review_tiff(tiff_path)
        except Exception as exc:  # noqa: BLE001
            preview_session.preview.warnings.append(f"PDF 转 TIF 或打开 Windows 照片查看器失败：{exc}")
    persist_booking_session(preview_session.session_id, session_data)
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
        return attachment_response(output_path, filename=output_path.name, media_type=XLSX_MEDIA_TYPE)
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
    session = get_booking_session(session_id)
    preview = _normalize_booking_preview(session.get("booking_preview"))
    if preview is None:
        raise HTTPException(status_code=404, detail="未找到 Booking 预览记录。")
    session["booking_preview"] = preview
    return preview


@router.get("/modules/booking/preview/{session_id}", response_class=HTMLResponse)
async def restore_sil_fuca_booking_preview(request: Request, session_id: str) -> HTMLResponse:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status_code=404, detail="未找到 SIL-FUCA Booking 预览记录。")
    session = get_booking_session(session_id)
    preview = get_booking_preview(session_id)
    if preview.supplier != "SIL-FUCA" or preview.session_id != session_id:
        raise HTTPException(status_code=404, detail="未找到 SIL-FUCA Booking 预览记录。")
    return templates.TemplateResponse(
        request,
        "booking.html",
        booking_page_context(
            selected_supplier=preview.supplier,
            preview=preview,
            warehouse_mail_ready=sil_fuca_warehouse_mail_ready(session, preview),
        ),
    )


@router.post("/modules/booking/generate/{session_id}")
async def generate_booking(session_id: str) -> FileResponse:
    return generate_booking_file_response(session_id)


@router.get("/modules/booking/generate/{session_id}")
async def download_booking(session_id: str) -> FileResponse:
    return generate_booking_file_response(session_id)


@router.get("/modules/booking/flex-texas-review-tiff/{session_id}")
async def download_flex_texas_review_tiff(session_id: str) -> FileResponse:
    session = get_booking_session(session_id)
    tiff_path = Path(str(session.get("booking_pdf_tiff_path") or ""))
    if not tiff_path.is_file():
        raise HTTPException(status_code=404, detail="未找到 Flex-Texas PDF 转出的 TIF 核对图。")
    return attachment_response(tiff_path, filename=tiff_path.name, media_type="image/tiff")


def generate_booking_file_response(session_id: str) -> FileResponse:
    preview = get_booking_preview(session_id)
    try:
        output_path = write_booking_output(preview)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(output_path, filename=output_path.name, media_type=XLSX_MEDIA_TYPE)


@router.post("/modules/booking/warehouse-mail/{session_id}")
async def generate_booking_warehouse_mail(session_id: str, warehouse_file: UploadFile = File(...)) -> FileResponse:
    if not warehouse_file.filename:
        raise HTTPException(status_code=400, detail="请上传做好的入仓文件。")
    session = get_booking_session(session_id)
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
    return attachment_response(output_path, filename=output_path.name, media_type=EML_MEDIA_TYPE)


@router.post("/modules/booking/flex-texas-reply-mail/{session_id}")
async def generate_flex_texas_reply_mail(
    session_id: str,
    tms_pdf_file: UploadFile = File(...),
    body_text: str = Form(""),
) -> FileResponse:
    if not tms_pdf_file.filename:
        raise HTTPException(status_code=400, detail="请上传 TMS 导出的 PDF 文件。")
    session = get_booking_session(session_id)
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
    return attachment_response(output_path, filename=output_path.name, media_type=EML_MEDIA_TYPE)
