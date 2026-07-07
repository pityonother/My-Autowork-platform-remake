from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR, UPLOAD_DIR
from app.shared.performance import timed_step
from app.shared.state import SESSION_STORE
from app.shared.uploads import save_upload


EML_SUFFIXES = {".eml"}


def display_number(value: Any) -> str:
    from app.modules.dispatch_mail.legacy_adapter import display_number as legacy_display_number

    return legacy_display_number(value)


def dispatch_load_label(ticket: Any) -> str:
    from app.modules.dispatch_mail.legacy_adapter import dispatch_load_label as legacy_dispatch_load_label

    return legacy_dispatch_load_label(ticket)


def read_docx_text_preview(*args: Any, **kwargs: Any) -> Any:
    from app.modules.dispatch_mail.legacy_adapter import read_docx_text_preview as legacy_read_docx_text_preview

    return legacy_read_docx_text_preview(*args, **kwargs)


def read_dispatch_attachment_preview(*args: Any, **kwargs: Any) -> Any:
    from app.modules.dispatch_mail.legacy_adapter import (
        read_dispatch_attachment_preview as legacy_read_dispatch_attachment_preview,
    )

    return legacy_read_dispatch_attachment_preview(*args, **kwargs)


def render_word_preview_pdf(*args: Any, **kwargs: Any) -> Any:
    from app.modules.dispatch_mail.legacy_adapter import render_word_preview_pdf as legacy_render_word_preview_pdf

    return legacy_render_word_preview_pdf(*args, **kwargs)


def resolve_assignments(result: Any, form_data: dict[str, Any]) -> None:
    from app.modules.dispatch_mail.legacy_adapter import resolve_assignments as legacy_resolve_assignments

    legacy_resolve_assignments(result, form_data)


def update_ticket_compose_fields(result: Any, form_data: dict[str, Any]) -> None:
    from app.modules.dispatch_mail.legacy_adapter import update_ticket_compose_fields as legacy_update_ticket_compose_fields

    legacy_update_ticket_compose_fields(result, form_data)


def parse_customer_email(customer_eml: UploadFile, *, rule_profile: str = "auto") -> str:
    from app.modules.dispatch_mail.legacy_adapter import parse_dispatch_eml

    session_id = uuid.uuid4().hex[:12]
    eml_path = save_upload(session_id, customer_eml, "dispatch_customer", allowed_suffixes=EML_SUFFIXES)
    with timed_step("dispatch_mail.parse_customer_email"):
        result = parse_dispatch_eml(session_id, eml_path, UPLOAD_DIR, OUTPUT_DIR, rule_profile=rule_profile)
    SESSION_STORE[session_id] = {"dispatch_result": result}
    return session_id


def generate_dispatch_mail_file(
    result: Any,
    *,
    session_id: str,
    tracking_no: str,
    arrival_day: str,
    arrival_hour: str,
    truck_plate: str,
    to_email: str,
    cc_email: str,
    from_email: str,
) -> Path:
    from app.modules.dispatch_mail.legacy_adapter import generate_dispatch_eml

    output_path = OUTPUT_DIR / f"dispatch_mail_{session_id}.eml"
    with timed_step("dispatch_mail.generate_mail"):
        generate_dispatch_eml(
            result,
            output_path,
            tracking_no=tracking_no,
            arrival_day=arrival_day,
            arrival_hour=arrival_hour,
            truck_plate=truck_plate,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
        )
    return output_path
