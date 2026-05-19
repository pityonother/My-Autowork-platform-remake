from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.modules.mail_classifier import repository
from app.modules.mail_classifier.schemas import (
    BUSINESS_LABELS,
    DEFAULT_IMAP_HOST,
    DEFAULT_IMAP_PORT,
    DEFAULT_MAILBOX,
    DEFAULT_SYNC_DAYS,
    RISK_LABEL_MAP,
    STATUS_LABELS,
)
from app.modules.mail_classifier.service import sync_mail_account
from app.web.templates import templates


router = APIRouter()


def build_mail_classifier_context(
    *,
    account_email: str = "",
    business_label: str = "",
    status_label: str = "",
    error: str = "",
    sync_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accounts = repository.list_mail_accounts()
    account_form = repository.get_default_account_form()
    if account_email:
        for account in accounts:
            if account["account_email"] == account_email:
                account_form = account
                break
    return {
        "accounts": accounts,
        "account_form": account_form,
        "messages": repository.list_mail_messages(
            account_email=account_email,
            business_label=business_label,
            status_label=status_label,
        ),
        "summary": repository.get_mail_summary(),
        "business_labels": BUSINESS_LABELS,
        "status_labels": STATUS_LABELS,
        "risk_label_map": RISK_LABEL_MAP,
        "selected_account": account_email,
        "selected_business_label": business_label,
        "selected_status_label": status_label,
        "default_imap_host": DEFAULT_IMAP_HOST,
        "default_imap_port": DEFAULT_IMAP_PORT,
        "default_mailbox": DEFAULT_MAILBOX,
        "default_sync_days": DEFAULT_SYNC_DAYS,
        "error": error,
        "sync_result": sync_result,
    }


@router.get("/modules/mail-classifier", response_class=HTMLResponse)
async def mail_classifier_page(
    request: Request,
    account_email: str = Query(default=""),
    business_label: str = Query(default=""),
    status_label: str = Query(default=""),
    synced: int = Query(default=0),
    imported: int = Query(default=0),
    updated: int = Query(default=0),
    skipped: int = Query(default=0),
    mailbox: str = Query(default=""),
) -> HTMLResponse:
    sync_result = None
    if synced:
        sync_result = {
            "scanned": synced,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "mailbox": mailbox,
        }
    return templates.TemplateResponse(
        request,
        "mail_classifier.html",
        build_mail_classifier_context(
            account_email=account_email,
            business_label=business_label,
            status_label=status_label,
            sync_result=sync_result,
        ),
    )


@router.post("/modules/mail-classifier/sync", response_class=HTMLResponse)
async def sync_mail_classifier(
    request: Request,
    account_email: str = Form(...),
    imap_host: str = Form(default=DEFAULT_IMAP_HOST),
    imap_port: int = Form(default=DEFAULT_IMAP_PORT),
    password: str = Form(default=""),
    mailbox: str = Form(default=DEFAULT_MAILBOX),
    sync_days: int = Form(default=DEFAULT_SYNC_DAYS),
) -> Response:
    normalized_account = account_email.strip().lower()
    try:
        repository.save_mail_account_settings(
            account_email=normalized_account,
            imap_host=imap_host,
            imap_port=imap_port,
            password=password,
            default_mailbox=mailbox,
            sync_days=sync_days,
            use_ssl=True,
        )
        result = sync_mail_account(normalized_account, mailbox=mailbox, sync_days=sync_days)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "mail_classifier.html",
            build_mail_classifier_context(account_email=normalized_account, error=str(exc)),
            status_code=400,
        )
    query = urlencode(
        {
            "account_email": normalized_account,
            "synced": result.scanned,
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
            "mailbox": result.mailbox,
        }
    )
    return RedirectResponse(url=f"/modules/mail-classifier?{query}", status_code=303)


@router.post("/modules/mail-classifier/messages/{message_id}/labels")
async def update_mail_classifier_message_labels(
    request: Request,
    message_id: int,
    business_labels: list[str] = Form(default=[]),
    status_label: str = Form(default="needs_review"),
) -> RedirectResponse:
    repository.update_mail_message_labels(
        message_id,
        business_labels=business_labels,
        status_label=status_label,
    )
    return RedirectResponse(url=request.headers.get("referer", "/modules/mail-classifier"), status_code=303)
