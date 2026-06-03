from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from app.modules.dispatch_mail import repository
from app.modules.dispatch_mail.schemas import DispatchParseResult
from app.modules.dispatch_mail.service import (
    display_number,
    dispatch_load_label,
    generate_dispatch_mail_file,
    parse_customer_email,
    read_docx_text_preview,
    read_dispatch_attachment_preview,
    render_word_preview_pdf,
    resolve_assignments,
    update_ticket_compose_fields,
)
from app.shared.state import SESSION_STORE
from app.web.templates import templates


router = APIRouter()


def get_session(session_id: str) -> dict[str, Any]:
    return SESSION_STORE.get_required(session_id)


@router.get("/modules/dispatch-mail", response_class=HTMLResponse)
async def dispatch_mail_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dispatch_mail.html", {"error": ""})


@router.post("/modules/dispatch-mail/parse")
async def parse_dispatch_mail(
    request: Request,
    customer_eml: UploadFile = File(...),
    rule_profile: str = Form("auto"),
) -> Response:
    if not customer_eml.filename:
        return templates.TemplateResponse(
            request,
            "dispatch_mail.html",
            {"error": "请上传客户原始 eml 邮件。"},
            status_code=400,
        )
    try:
        session_id = parse_customer_email(customer_eml, rule_profile=rule_profile)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(request, "dispatch_mail.html", {"error": str(exc)}, status_code=400)
    return RedirectResponse(url=f"/modules/dispatch-mail/preview/{session_id}", status_code=303)


def get_dispatch_session(session_id: str) -> DispatchParseResult:
    session = get_session(session_id)
    result = session.get("dispatch_result")
    if not result:
        raise HTTPException(status_code=404, detail="未找到派送邮件解析记录。")
    return result


def get_dispatch_attachment_by_role(result: DispatchParseResult, role: str, item_index: int):
    if role == "master":
        if item_index != 0 or not result.master:
            raise HTTPException(status_code=404, detail="未找到原始文件。")
        return result.master
    if role == "dqth":
        if item_index < 0 or item_index >= len(result.dqths):
            raise HTTPException(status_code=404, detail="未找到原始文件。")
        return result.dqths[item_index].attachment
    if role == "so":
        if item_index < 0 or item_index >= len(result.sos):
            raise HTTPException(status_code=404, detail="未找到原始文件。")
        return result.sos[item_index].attachment
    raise HTTPException(status_code=404, detail="未找到原始文件。")


def get_dispatch_attachment_rendered_preview_path(
    result: DispatchParseResult,
    role: str,
    item_index: int,
) -> Path:
    preview_dir = result.output_dir / "source_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir / f"{role}_{item_index}.pdf"


def build_dispatch_attachment_preview_context(
    result: DispatchParseResult,
    role: str,
    item_index: int,
) -> dict[str, Any]:
    attachment = get_dispatch_attachment_by_role(result, role, item_index)
    download_href = f"/modules/dispatch-mail/source-file/{result.session_id}/{role}/{item_index}"
    preview = read_dispatch_attachment_preview(attachment)
    if preview is not None:
        sheet_name, rows = preview
        return {
            "attachment": attachment,
            "preview_mode": "sheet",
            "preview_note": "这里展示首个工作表预览，适合快速核对表格内容；完整格式以原文件为准。",
            "sheet_name": sheet_name,
            "rows": rows,
            "download_href": download_href,
            "open_href": download_href,
        }

    suffix = attachment.stored_path.suffix.lower()
    if suffix == ".pdf":
        rendered_href = f"/modules/dispatch-mail/source-rendered/{result.session_id}/{role}/{item_index}"
        return {
            "attachment": attachment,
            "preview_mode": "pdf",
            "preview_note": "PDF 使用原文件直接预览，版式就是原版，准确性最高。",
            "rendered_href": rendered_href,
            "download_href": download_href,
            "open_href": download_href,
        }

    if suffix in {".doc", ".docx"}:
        rendered_path = get_dispatch_attachment_rendered_preview_path(result, role, item_index)
        rendered_pdf = rendered_path if rendered_path.exists() else render_word_preview_pdf(attachment.stored_path, rendered_path)
        if rendered_pdf and rendered_pdf.exists():
            rendered_href = f"/modules/dispatch-mail/source-rendered/{result.session_id}/{role}/{item_index}"
            return {
                "attachment": attachment,
                "preview_mode": "pdf",
                "preview_note": "已转成 PDF 预览，版式会尽量贴近原 Word 文件；如有细微差异，请再打开原文件确认。",
                "rendered_href": rendered_href,
                "download_href": download_href,
                "open_href": download_href,
            }
        if suffix == ".docx":
            paragraphs = read_docx_text_preview(attachment.stored_path)
            return {
                "attachment": attachment,
                "preview_mode": "docx_text",
                "preview_note": "当前显示的是 DOCX 文本预览，便于快速看内容；段落文字准确，但版式仍以原文件为准。",
                "paragraphs": paragraphs,
                "download_href": download_href,
                "open_href": download_href,
            }
        return {
            "attachment": attachment,
            "preview_mode": "binary",
            "preview_note": "这份 .doc 文件当前无法稳定做版式预览，请直接打开原文件核对内容。",
            "download_href": download_href,
            "open_href": download_href,
        }

    return {
        "attachment": attachment,
        "preview_mode": "binary",
        "preview_note": "当前文件类型暂不支持内嵌预览，请直接打开原文件查看。",
        "download_href": download_href,
        "open_href": download_href,
    }


@router.get("/modules/dispatch-mail/preview/{session_id}", response_class=HTMLResponse)
async def dispatch_mail_preview(request: Request, session_id: str, saved: int = Query(0)) -> HTMLResponse:
    result = get_dispatch_session(session_id)
    return templates.TemplateResponse(
        request,
        "dispatch_mail_preview.html",
        {
            "session_id": session_id,
            "result": result,
            "active_tickets": [ticket for ticket in result.tickets if ticket.include_in_dispatch],
            "saved": bool(saved),
            "dispatch_load_label": dispatch_load_label,
            "display_number": display_number,
        },
    )


@router.post("/modules/dispatch-mail/preview/{session_id}/update")
async def update_dispatch_mail_preview(request: Request, session_id: str) -> RedirectResponse:
    result = get_dispatch_session(session_id)
    form = await request.form()
    form_dict = dict(form)
    resolve_assignments(result, form)
    action = str(form_dict.get("action", "next")).strip().lower()
    if action == "save":
        return RedirectResponse(url=f"/modules/dispatch-mail/preview/{session_id}?saved=1", status_code=303)
    return RedirectResponse(url=f"/modules/dispatch-mail/compose/{session_id}", status_code=303)


@router.get("/modules/dispatch-mail/source/{session_id}/{role}/{item_index}")
async def dispatch_attachment_source_preview(request: Request, session_id: str, role: str, item_index: int) -> Response:
    result = get_dispatch_session(session_id)
    context = build_dispatch_attachment_preview_context(result, role, item_index)
    return templates.TemplateResponse(
        request,
        "dispatch_attachment_preview.html",
        {
            "role": role,
            **context,
        },
    )


@router.get("/modules/dispatch-mail/source-rendered/{session_id}/{role}/{item_index}")
async def dispatch_attachment_source_rendered(session_id: str, role: str, item_index: int) -> FileResponse:
    result = get_dispatch_session(session_id)
    attachment = get_dispatch_attachment_by_role(result, role, item_index)
    suffix = attachment.stored_path.suffix.lower()
    if suffix == ".pdf":
        return FileResponse(
            attachment.stored_path,
            media_type=attachment.content_type or "application/pdf",
            filename=attachment.original_name,
        )
    if suffix not in {".doc", ".docx"}:
        raise HTTPException(status_code=404, detail="当前文件没有可渲染预览。")
    rendered_path = get_dispatch_attachment_rendered_preview_path(result, role, item_index)
    if not rendered_path.exists():
        rendered_pdf = render_word_preview_pdf(attachment.stored_path, rendered_path)
        if rendered_pdf is None or not rendered_pdf.exists():
            raise HTTPException(status_code=404, detail="当前文件暂时无法生成预览。")
    return FileResponse(
        rendered_path,
        media_type="application/pdf",
        filename=f"{attachment.stored_path.stem}.pdf",
    )


@router.get("/modules/dispatch-mail/source-file/{session_id}/{role}/{item_index}")
async def dispatch_attachment_source_file(session_id: str, role: str, item_index: int) -> FileResponse:
    result = get_dispatch_session(session_id)
    attachment = get_dispatch_attachment_by_role(result, role, item_index)
    return FileResponse(
        attachment.stored_path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
    )


@router.get("/modules/dispatch-mail/compose/{session_id}", response_class=HTMLResponse)
async def dispatch_mail_compose(request: Request, session_id: str) -> HTMLResponse:
    result = get_dispatch_session(session_id)
    return templates.TemplateResponse(
        request,
        "dispatch_mail_compose.html",
        {
            "session_id": session_id,
            "result": result,
            "active_tickets": [ticket for ticket in result.tickets if ticket.include_in_dispatch],
            "settings": repository.get_dispatch_settings(),
            "error": "",
        },
    )


@router.post("/modules/dispatch-mail/settings")
async def save_dispatch_mail_common_settings(request: Request) -> JSONResponse:
    form = await request.form()
    repository.save_dispatch_settings(
        to_email=str(form.get("to_email", "")).strip(),
        cc_email=str(form.get("cc_email", "")).strip(),
        from_email=str(form.get("from_email", "")).strip(),
    )
    return JSONResponse({"ok": True, "message": "已保存常用收件人"})


@router.get("/modules/dispatch-mail/image/{session_id}/{ticket_index}")
async def dispatch_ticket_image(session_id: str, ticket_index: int) -> FileResponse:
    result = get_dispatch_session(session_id)
    for ticket in result.tickets:
        if ticket.index == ticket_index and ticket.table_image_path and ticket.table_image_path.exists():
            return FileResponse(ticket.table_image_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="未找到该票截图。")


@router.post("/modules/dispatch-mail/generate/{session_id}", response_model=None)
async def generate_dispatch_mail(request: Request, session_id: str) -> Response:
    result = get_dispatch_session(session_id)
    form = await request.form()
    form_dict = dict(form)
    update_ticket_compose_fields(result, form_dict)
    try:
        output_path = generate_dispatch_mail_file(
            result,
            session_id=session_id,
            tracking_no=form_dict.get("tracking_no", "").strip(),
            arrival_day=form_dict.get("arrival_day", "").strip(),
            arrival_hour=form_dict.get("arrival_hour", "").strip(),
            truck_plate=form_dict.get("truck_plate", "").strip(),
            to_email=form_dict.get("to_email", "").strip(),
            cc_email=form_dict.get("cc_email", "").strip(),
            from_email=form_dict.get("from_email", "").strip(),
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "dispatch_mail_compose.html",
            {
                "session_id": session_id,
                "result": result,
                "active_tickets": [ticket for ticket in result.tickets if ticket.include_in_dispatch],
                "settings": repository.get_dispatch_settings(),
                "error": str(exc),
            },
            status_code=400,
        )
    return FileResponse(output_path, media_type="message/rfc822", filename=output_path.name)
