from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.modules.finance import repository
from app.modules.finance.schemas import TASK_STATUS_OPTIONS
from app.modules.finance.service import export_outbound_bill, import_payment_file, preview_export_rows
from app.web.templates import templates


router = APIRouter()

FINANCE_CATEGORY_OPTIONS = [
    ("", "全部分类"),
    ("fy_export", "福永伟创力代垫"),
    ("ft_export", "福田伟创力代垫"),
    ("other", "其他代支"),
]


def parse_optional_int(value: str, field_name: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是数字。") from exc


@router.get("/modules/finance-records", response_class=HTMLResponse)
async def finance_records_dashboard(
    request: Request,
    batch_id: str = Query(default=""),
    currency: str = Query(default=""),
    category: str = Query(default=""),
    task_status: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    only_exportable: bool = Query(default=False),
    only_invoice_required: bool = Query(default=False),
    exchange_rate: str = Query(default=""),
    imported_batch: str = Query(default=""),
    import_parsed: int = Query(default=0),
    import_inserted: int = Query(default=0),
    import_duplicates: int = Query(default=0),
    import_merged: int = Query(default=0),
) -> HTMLResponse:
    normalized_batch_id = parse_optional_int(batch_id, "batch_id")
    records = repository.list_finance_records(
        batch_id=normalized_batch_id,
        currency=currency or None,
        category=category or None,
        task_status=task_status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        only_exportable=only_exportable,
        only_invoice_required=only_invoice_required,
    )
    export_rows, export_error = preview_export_rows(
        exchange_rate=exchange_rate,
        category=category,
        batch_id=normalized_batch_id,
        currency=currency or None,
        task_status=task_status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        only_exportable=only_exportable,
        only_invoice_required=only_invoice_required,
    )
    return templates.TemplateResponse(
        request,
        "finance_records.html",
        {
            "batches": repository.list_finance_batches(),
            "records": records,
            "export_rows": export_rows,
            "export_error": export_error,
            "batch_id": batch_id,
            "currency": currency,
            "category": category,
            "task_status": task_status,
            "date_from": date_from,
            "date_to": date_to,
            "only_exportable": only_exportable,
            "only_invoice_required": only_invoice_required,
            "exchange_rate": exchange_rate,
            "record_summary": repository.summarize_finance_records(records),
            "export_append_count": len(export_rows),
            "category_options": FINANCE_CATEGORY_OPTIONS,
            "task_status_options": TASK_STATUS_OPTIONS,
            "imported_batch": imported_batch,
            "import_parsed": import_parsed,
            "import_inserted": import_inserted,
            "import_duplicates": import_duplicates,
            "import_merged": import_merged,
            "import_skipped": max(import_duplicates - import_merged, 0),
        },
    )


@router.post("/modules/finance-records/import")
async def import_finance_records(request: Request, payment_file: UploadFile = File(...)) -> RedirectResponse:
    batch = import_payment_file(payment_file)
    stats = batch.get("import_stats", {})
    return RedirectResponse(
        url=(
            f"/modules/finance-records?batch_id={batch['batch']['id']}"
            f"&imported_batch={batch['batch']['batch_code']}"
            f"&import_parsed={stats.get('parsed_count', 0)}"
            f"&import_inserted={stats.get('inserted_count', 0)}"
            f"&import_duplicates={stats.get('duplicate_count', 0)}"
            f"&import_merged={stats.get('merged_count', 0)}"
        ),
        status_code=303,
    )


@router.post("/modules/finance-records/records/{record_id}/task-status")
async def update_finance_record_status(
    request: Request,
    record_id: int,
    task_status: str = Form(...),
) -> RedirectResponse:
    repository.update_finance_task_status(record_id, task_status)
    return RedirectResponse(url=request.headers.get("referer", "/modules/finance-records"), status_code=303)


@router.post("/modules/finance-records/records/{record_id}/export-status")
async def update_finance_record_export_status(
    request: Request,
    record_id: int,
    export_status: str = Form(...),
) -> RedirectResponse:
    repository.update_finance_export_status(record_id, export_status == "exported")
    return RedirectResponse(url=request.headers.get("referer", "/modules/finance-records"), status_code=303)


@router.post("/modules/finance-records/export")
async def export_finance_bill(
    request: Request,
    bill_file: UploadFile = File(...),
    exchange_rate: str = Form(...),
    batch_id: int | None = Form(default=None),
    currency: str = Form(default=""),
    category: str = Form(default=""),
    task_status: str = Form(default=""),
    date_from: str = Form(default=""),
    date_to: str = Form(default=""),
    only_exportable: bool = Form(default=False),
    only_invoice_required: bool = Form(default=False),
) -> FileResponse:
    try:
        output_path = export_outbound_bill(
            bill_file=bill_file,
            exchange_rate=exchange_rate,
            batch_id=batch_id,
            currency=currency or None,
            category=category,
            task_status=task_status or None,
            date_from=date_from or None,
            date_to=date_to or None,
            only_exportable=only_exportable,
            only_invoice_required=only_invoice_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(output_path, media_type="application/vnd.ms-excel", filename=output_path.name)


@router.get("/modules/finance-records/batches/{batch_id}", response_class=HTMLResponse)
async def finance_batch_detail(request: Request, batch_id: int) -> HTMLResponse:
    detail = repository.get_finance_batch_detail(batch_id)
    return templates.TemplateResponse(
        request,
        "finance_batch.html",
        {"batch": detail["batch"], "records": detail["records"]},
    )
