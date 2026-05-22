from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app.modules.ufo_mail import repository
from app.modules.ufo_mail.schemas import UfoIssueInput
from app.modules.ufo_mail.service import clear_output_cache, generate_mail, import_signature
from app.web.templates import templates


router = APIRouter()


def build_ufo_context(error: str = "", notice: str = "") -> dict[str, Any]:
    issues = repository.list_ufo_issues(include_inactive=True)
    return {
        "issues": issues,
        "active_issues": [issue for issue in issues if issue["is_active"]],
        "mail_settings": repository.get_ufo_mail_settings(),
        "signature_settings": repository.get_ufo_signature_settings(),
        "error": error,
        "notice": notice,
    }


@router.get("/modules/ufo-mail", response_class=HTMLResponse)
async def ufo_mail_page(request: Request) -> HTMLResponse:
    notice = ""
    if request.query_params.get("cache_cleared") == "1":
        notice = "输出缓存已清理。"
    return templates.TemplateResponse(request, "ufo_mail.html", build_ufo_context(notice=notice))


@router.post("/modules/ufo-mail/cache/clear")
async def clear_ufo_mail_output_cache() -> dict[str, int | bool]:
    result = clear_output_cache()
    return {"ok": True, **result}


@router.post("/modules/ufo-mail/issues")
async def create_ufo_mail_issue(
    short_cn: str = Form(...),
    short_en: str = Form(...),
    detail_en: str = Form(...),
) -> RedirectResponse:
    repository.create_ufo_issue(UfoIssueInput(short_cn=short_cn, short_en=short_en, detail_en=detail_en))
    return RedirectResponse(url="/modules/ufo-mail#issue-library", status_code=303)


@router.post("/modules/ufo-mail/issues/{issue_id}/update")
async def update_ufo_mail_issue(
    issue_id: int,
    short_cn: str = Form(...),
    short_en: str = Form(...),
    detail_en: str = Form(...),
) -> RedirectResponse:
    repository.update_ufo_issue(issue_id, UfoIssueInput(short_cn=short_cn, short_en=short_en, detail_en=detail_en))
    return RedirectResponse(url="/modules/ufo-mail#issue-library", status_code=303)


@router.post("/modules/ufo-mail/issues/{issue_id}/active")
async def toggle_ufo_mail_issue(issue_id: int, is_active: bool = Form(default=False)) -> RedirectResponse:
    repository.set_ufo_issue_active(issue_id, is_active)
    return RedirectResponse(url="/modules/ufo-mail#issue-library", status_code=303)


@router.post("/modules/ufo-mail/settings")
async def save_ufo_mail_recipient_settings(
    to_email: str = Form(default=""),
    cc_email: str = Form(default=""),
    from_email: str = Form(default=""),
) -> RedirectResponse:
    repository.save_ufo_mail_settings(to_email=to_email, cc_email=cc_email, from_email=from_email)
    return RedirectResponse(url="/modules/ufo-mail#generate", status_code=303)


@router.post("/modules/ufo-mail/signature/import")
async def import_ufo_mail_signature(
    signature_file: UploadFile = File(...),
    marker: str = Form(default="Thanks & Best regards"),
) -> RedirectResponse:
    if not signature_file.filename:
        raise HTTPException(status_code=400, detail="请上传一封带签名的 eml 文件。")
    import_signature(signature_file, marker)
    return RedirectResponse(url="/modules/ufo-mail#signature-settings", status_code=303)


@router.post("/modules/ufo-mail/signature/enabled")
async def toggle_ufo_mail_signature(enabled: bool = Form(default=False)) -> RedirectResponse:
    repository.set_ufo_signature_enabled(enabled)
    return RedirectResponse(url="/modules/ufo-mail#signature-settings", status_code=303)


@router.post("/modules/ufo-mail/generate", response_model=None)
async def generate_ufo_mail(
    request: Request,
    issue_ids: list[int] = Form(default=[]),
    attachments: list[UploadFile] = File(default=[]),
    ufo_no: str = Form(default=""),
    to_email: str = Form(default=""),
    cc_email: str = Form(default=""),
    from_email: str = Form(default=""),
) -> Response:
    repository.save_ufo_mail_settings(to_email=to_email, cc_email=cc_email, from_email=from_email)
    try:
        output_path = generate_mail(
            issue_ids=issue_ids,
            attachments=attachments,
            ufo_no=ufo_no,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "ufo_mail.html",
            build_ufo_context(str(exc)),
            status_code=400,
        )
    return FileResponse(output_path, media_type="message/rfc822", filename=output_path.name)
