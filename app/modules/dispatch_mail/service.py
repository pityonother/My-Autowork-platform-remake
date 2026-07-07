from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR, UPLOAD_DIR
from app.shared.performance import timed_step
from app.shared.state import SESSION_STORE
from app.shared.uploads import save_upload
from app.modules.dispatch_mail.legacy_adapter import (
    DispatchParseResult,
    display_number as display_number,
    dispatch_load_label as dispatch_load_label,
    generate_dispatch_eml,
    parse_dispatch_eml,
    read_docx_text_preview as read_docx_text_preview,
    read_dispatch_attachment_preview as read_dispatch_attachment_preview,
    render_word_preview_pdf as render_word_preview_pdf,
    resolve_assignments as resolve_assignments,
    update_ticket_compose_fields as update_ticket_compose_fields,
)


EML_SUFFIXES = {".eml"}


def parse_customer_email(customer_eml: UploadFile, *, rule_profile: str = "auto") -> str:
    session_id = uuid.uuid4().hex[:12]
    eml_path = save_upload(session_id, customer_eml, "dispatch_customer", allowed_suffixes=EML_SUFFIXES)
    with timed_step("dispatch_mail.parse_customer_email"):
        result = parse_dispatch_eml(session_id, eml_path, UPLOAD_DIR, OUTPUT_DIR, rule_profile=rule_profile)
    SESSION_STORE[session_id] = {"dispatch_result": result}
    return session_id


def generate_dispatch_mail_file(
    result: DispatchParseResult,
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
