from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile

from app.core.paths import OUTPUT_DIR
from app.modules.ufo_mail.rules import detect_ufo_no
from app.shared.uploads import save_upload
from app.modules.ufo_mail.legacy_adapter import (
    UfoAttachment,
    UfoMailInput,
    generate_ufo_eml,
    import_ufo_signature_from_eml,
)


def safe_ufo_output_stem(value: str) -> str:
    text = (value or "").strip()
    match = re.search(r"\bUFO\d{6,}\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe[:80] or "ufo_mail"


def import_signature(signature_file: UploadFile, marker: str) -> None:
    session_id = uuid.uuid4().hex[:12]
    signature_path = save_upload(session_id, signature_file, "signature")
    import_ufo_signature_from_eml(signature_path, source_name=signature_file.filename, marker=marker)


def generate_mail(
    *,
    issue_ids: Sequence[int],
    attachments: Sequence[UploadFile],
    ufo_no: str,
    to_email: str,
    cc_email: str,
    from_email: str,
) -> Path:
    session_id = uuid.uuid4().hex[:12]
    saved_attachments: list[UfoAttachment] = []
    for idx, attachment in enumerate(attachments, start=1):
        if not attachment.filename:
            continue
        saved_path = save_upload(session_id, attachment, f"ufo_attachment_{idx:03d}")
        saved_attachments.append(UfoAttachment(path=saved_path, filename=attachment.filename))

    detected_ufo_no = ufo_no.strip() or detect_ufo_no([item.filename for item in saved_attachments])
    output_stem = safe_ufo_output_stem(detected_ufo_no)
    output_name = f"{output_stem}_{session_id}.eml"
    output_path = OUTPUT_DIR / output_name
    if not output_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
        raise ValueError("输出文件名不合法。")
    generate_ufo_eml(
        UfoMailInput(
            ufo_no=detected_ufo_no,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
            issue_ids=issue_ids,
            attachments=saved_attachments,
        ),
        output_path,
    )
    return output_path
