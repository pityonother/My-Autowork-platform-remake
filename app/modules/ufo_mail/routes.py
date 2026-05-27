from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app.modules.ufo_mail import repository
from app.modules.ufo_mail.schemas import UfoIssueInput
from app.modules.ufo_mail.service import (
    LowConfidenceReviewRequired,
    clear_output_cache,
    generate_mail,
    generate_mail_from_saved_session,
    import_signature,
)
from app.web.templates import templates


router = APIRouter()


def build_ufo_context(
    error: str = "",
    notice: str = "",
    form_state: dict[str, Any] | None = None,
    review_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = repository.list_ufo_issues(include_inactive=True)
    form_state = form_state or {}
    return {
        "issues": issues,
        "active_issues": [issue for issue in issues if issue["is_active"]],
        "mail_settings": repository.get_ufo_mail_settings(),
        "signature_settings": repository.get_ufo_signature_settings(),
        "error": error,
        "notice": notice,
        "form_state": form_state,
        "selected_issue_ids": form_state.get("issue_ids", []),
        "review_context": review_context,
    }


def build_form_state(
    *,
    issue_ids: list[int],
    ufo_no: str,
    to_email: str,
    cc_email: str,
    from_email: str,
) -> dict[str, Any]:
    return {
        "issue_ids": issue_ids,
        "ufo_no": ufo_no,
        "to_email": to_email,
        "cc_email": cc_email,
        "from_email": from_email,
    }


def build_review_context(exc: LowConfidenceReviewRequired, form_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": exc.session_id,
        "review_reports": exc.review_reports,
        **form_state,
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
    form_state = build_form_state(
        issue_ids=issue_ids,
        ufo_no=ufo_no,
        to_email=to_email,
        cc_email=cc_email,
        from_email=from_email,
    )
    try:
        output_path = generate_mail(
            issue_ids=issue_ids,
            attachments=attachments,
            ufo_no=ufo_no,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
        )
    except LowConfidenceReviewRequired as exc:
        return templates.TemplateResponse(
            request,
            "ufo_mail.html",
            build_ufo_context(
                str(exc),
                form_state=form_state,
                review_context=build_review_context(exc, form_state),
            ),
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "ufo_mail.html",
            build_ufo_context(str(exc), form_state=form_state),
            status_code=400,
        )
    return FileResponse(output_path, media_type="message/rfc822", filename=output_path.name)


@router.post("/modules/ufo-mail/generate/confirm-review", response_model=None)
async def confirm_ufo_mail_low_confidence_review(
    request: Request,
    session_id: str = Form(...),
    issue_ids: list[int] = Form(default=[]),
    ufo_no: str = Form(default=""),
    to_email: str = Form(default=""),
    cc_email: str = Form(default=""),
    from_email: str = Form(default=""),
) -> Response:
    repository.save_ufo_mail_settings(to_email=to_email, cc_email=cc_email, from_email=from_email)
    form_state = build_form_state(
        issue_ids=issue_ids,
        ufo_no=ufo_no,
        to_email=to_email,
        cc_email=cc_email,
        from_email=from_email,
    )
    try:
        output_path = generate_mail_from_saved_session(
            session_id=session_id,
            issue_ids=issue_ids,
            ufo_no=ufo_no,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
            allow_low_confidence=True,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "ufo_mail.html",
            build_ufo_context(str(exc), form_state=form_state),
            status_code=400,
        )
    return FileResponse(output_path, media_type="message/rfc822", filename=output_path.name)
