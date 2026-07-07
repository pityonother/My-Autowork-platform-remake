from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.modules.billing.schemas import ReconcileOutput
from app.modules.billing.service import build_billing_session, get_sorted_invoice_previews, slt_sort_key
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()

FEE_QUICK_FILTERS = [
    ("派送费", "派送"),
    ("无缝", "无缝"),
    ("中港运费", "中港"),
    ("机场附加费", "机场"),
    ("快递费", "快递"),
    ("装卸费", "装卸"),
]


def get_session(session_id: str) -> dict[str, Any]:
    return SESSION_STORE.get_required(session_id)


@router.get("/modules/billing", response_class=HTMLResponse)
async def billing_import_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "billing_import.html", {})


@router.post("/process")
async def process_files(
    request: Request,
    master_file: UploadFile | None = File(default=None),
    invoice_files: list[UploadFile] | None = File(default=None),
    delivery_note_files: list[UploadFile] | None = File(default=None),
    source_files: list[UploadFile] | None = File(default=None),
):
    try:
        session_id = build_billing_session(
            master_file=master_file,
            invoice_files=invoice_files or [],
            delivery_note_files=delivery_note_files or [],
            source_files=source_files or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/session/{session_id}", status_code=303)


@router.get("/session/{session_id}", response_class=HTMLResponse)
async def session_overview(request: Request, session_id: str) -> HTMLResponse:
    session = get_session(session_id)
    result: ReconcileOutput | None = session.get("result")
    if not result:
        return RedirectResponse(url=f"/session/{session_id}/customs", status_code=303)
    invoice_previews = get_sorted_invoice_previews(session)
    applied_sorted = sorted(
        [item.to_preview() for item in result.applied],
        key=lambda item: slt_sort_key(item.get("customer_order_no", "")),
    )
    return templates.TemplateResponse(
        request,
        "session.html",
        {
            "session_id": session_id,
            "master_name": session["master_name"],
            "invoice_count": session["invoice_count"],
            "delivery_note_count": session.get("delivery_note_count", 0),
            "source_count": session.get("source_count", 0),
            "has_customs": False,
            "applied": applied_sorted,
            "errors": result.errors,
            "master_headers": result.master_preview_headers,
            "master_rows": result.master_preview_rows,
            "invoice_previews": invoice_previews,
        },
    )


@router.get("/session/{session_id}/invoice/{invoice_index}", response_class=HTMLResponse)
async def invoice_detail(
    request: Request,
    session_id: str,
    invoice_index: int,
    fee_filter: str = Query(default=""),
) -> HTMLResponse:
    session = get_session(session_id)
    invoices = get_sorted_invoice_previews(session)
    if invoice_index < 0 or invoice_index >= len(invoices):
        raise HTTPException(status_code=404, detail="未找到这张单页账单。")
    invoice = invoices[invoice_index]
    fee_items = invoice["fee_items"]
    normalized_filter = fee_filter.strip().lower()
    if normalized_filter:
        fee_items = [
            item
            for item in fee_items
            if normalized_filter in item["fee_name"].lower()
            or normalized_filter in item["normalized_fee_name"].lower()
            or normalized_filter in item["description"].lower()
        ]
    grouped_totals: dict[str, float] = {}
    for item in fee_items:
        grouped_totals.setdefault(item["fee_name"], 0.0)
        grouped_totals[item["fee_name"]] += float(item["amount"])
    total_rows = [{"fee_name": name, "amount": f"{amount:.2f}"} for name, amount in sorted(grouped_totals.items())]
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {
            "session_id": session_id,
            "invoice_index": invoice_index,
            "invoice": invoice,
            "fee_items": fee_items,
            "fee_filter": fee_filter,
            "fee_totals": total_rows,
            "quick_filters": FEE_QUICK_FILTERS,
        },
    )


@router.get("/download/{session_id}")
async def download_output(session_id: str):
    session = get_session(session_id)
    result: ReconcileOutput | None = session.get("result")
    if not result or not result.output_path or not result.output_path.exists():
        raise HTTPException(status_code=404, detail="总账输出文件不存在。")
    return FileResponse(
        result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=result.output_path.name,
    )
