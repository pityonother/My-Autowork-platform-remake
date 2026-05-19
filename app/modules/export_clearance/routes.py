from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.modules.export_clearance import exports, repository
from app.modules.export_clearance.service import import_clearance_batch
from app.web.templates import templates


router = APIRouter()


@router.get("/modules/export-customs", response_class=HTMLResponse)
async def export_customs_dashboard(
    request: Request,
    clearance_status: str = Query(default="pending"),
    shipment_date_from: str = Query(default=""),
    shipment_date_to: str = Query(default=""),
    tan_number: str = Query(default=""),
    imported_batch: str = Query(default=""),
    sort_by: str = Query(default="urgency"),
) -> HTMLResponse:
    records = repository.list_records(
        clearance_status=clearance_status if clearance_status != "all" else None,
        shipment_date_from=shipment_date_from or None,
        shipment_date_to=shipment_date_to or None,
        tan_number=tan_number or None,
        sort_by=sort_by,
    )
    return templates.TemplateResponse(
        request,
        "export_customs.html",
        {
            "batches": repository.list_batches(),
            "records": records,
            "clearance_status": clearance_status,
            "shipment_date_from": shipment_date_from,
            "shipment_date_to": shipment_date_to,
            "tan_number": tan_number,
            "imported_batch": imported_batch,
            "sort_by": sort_by,
        },
    )


@router.post("/modules/export-customs/import")
async def import_export_customs(
    request: Request,
    tracker: str = Form(...),
    manifest_code: str = Form(...),
    shipment_date: date = Form(...),
    trip_sequence: int = Form(...),
    source_files: list[UploadFile] = File(...),
) -> RedirectResponse:
    try:
        batch = import_clearance_batch(
            tracker=tracker,
            manifest_code=manifest_code,
            shipment_date=shipment_date,
            trip_sequence=trip_sequence,
            source_files=source_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/modules/export-customs?imported_batch={batch['batch']['batch_code']}",
        status_code=303,
    )


@router.post("/modules/export-customs/records/{record_id}/status")
async def update_export_customs_status(record_id: int, status: str = Form(...)) -> RedirectResponse:
    if status not in {"pending", "cleared"}:
        raise HTTPException(status_code=400, detail="不支持的清关状态。")
    repository.mark_record_clearance(record_id, status)
    return RedirectResponse(url="/modules/export-customs", status_code=303)


@router.get("/modules/export-customs/batches/{batch_id}", response_class=HTMLResponse)
async def export_customs_batch_detail(request: Request, batch_id: int) -> HTMLResponse:
    detail = repository.get_batch_detail(batch_id)
    return templates.TemplateResponse(
        request,
        "export_customs_batch.html",
        {"batch": detail["batch"], "records": detail["records"]},
    )


@router.get("/modules/export-customs/download/pending")
async def download_export_customs_pending() -> StreamingResponse:
    output = exports.export_pending_workbook()
    filename = f"pending_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/modules/export-customs/download/cleared")
async def download_export_customs_cleared(clear_date: date | None = Query(default=None)) -> StreamingResponse:
    output = exports.export_cleared_workbook(clear_date=clear_date or date.today())
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="clearance_export.xlsx"'},
    )
