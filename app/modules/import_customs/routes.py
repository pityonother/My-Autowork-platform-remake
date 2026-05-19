from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.modules.import_customs.legacy_adapter import CustomsOutput
from app.modules.import_customs.service import build_import_customs_session
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()


def get_session(session_id: str) -> dict[str, Any]:
    return SESSION_STORE.get_required(session_id)


@router.get("/modules/import-customs", response_class=HTMLResponse)
async def import_customs_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "import_customs_import.html", {})


@router.post("/process/customs")
async def process_customs_files(
    request: Request,
    order_management_file: UploadFile | None = File(default=None),
    customs_bill_file: UploadFile | None = File(default=None),
    source_files: list[UploadFile] = File(default=[]),
):
    try:
        session_id = build_import_customs_session(
            order_management_file=order_management_file,
            customs_bill_file=customs_bill_file,
            source_files=source_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/session/{session_id}/customs", status_code=303)


@router.get("/session/{session_id}/customs", response_class=HTMLResponse)
async def customs_overview(request: Request, session_id: str) -> HTMLResponse:
    session = get_session(session_id)
    customs_result: CustomsOutput | None = session.get("customs_result")
    if not customs_result:
        raise HTTPException(status_code=404, detail="未找到这次清关预览。")
    return templates.TemplateResponse(
        request,
        "customs.html",
        {
            "session_id": session_id,
            "has_billing": False,
            "order_management_name": session.get("order_management_name", ""),
            "customs_bill_name": session.get("customs_bill_name", ""),
            "source_count": session.get("source_count", 0),
            "rows": customs_result.preview_rows,
            "errors": customs_result.errors,
            "has_customs_preview_output": bool(
                customs_result.preview_export_path and customs_result.preview_export_path.exists()
            ),
            "has_customs_bill_output": bool(
                customs_result.bill_output_path and customs_result.bill_output_path.exists()
            ),
        },
    )


@router.get("/download/customs-preview/{session_id}")
async def download_customs_preview(session_id: str):
    session = get_session(session_id)
    customs_result: CustomsOutput | None = session.get("customs_result")
    if not customs_result or not customs_result.preview_export_path or not customs_result.preview_export_path.exists():
        raise HTTPException(status_code=404, detail="清关预览导出文件不存在。")
    return FileResponse(
        customs_result.preview_export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=customs_result.preview_export_path.name,
    )


@router.get("/download/customs-bill/{session_id}")
async def download_customs_bill(session_id: str):
    session = get_session(session_id)
    customs_result: CustomsOutput | None = session.get("customs_result")
    if not customs_result or not customs_result.bill_output_path or not customs_result.bill_output_path.exists():
        raise HTTPException(status_code=404, detail="清关 bill 输出文件不存在。")
    return FileResponse(
        customs_result.bill_output_path,
        media_type="application/vnd.ms-excel",
        filename=customs_result.bill_output_path.name,
    )
