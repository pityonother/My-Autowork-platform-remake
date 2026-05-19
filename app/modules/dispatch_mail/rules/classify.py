from __future__ import annotations

import re
from typing import Any


SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}
WORD_SUFFIXES = {".doc", ".docx"}
CONTENT_MATCH_SUFFIXES = SPREADSHEET_SUFFIXES | WORD_SUFFIXES | {".pdf"}


def _ensure_attachment_text(attachment: Any) -> None:
    from app.modules.dispatch_mail.legacy_adapter import ensure_attachment_text

    ensure_attachment_text(attachment)


def looks_like_tan_master_attachment(attachment: Any) -> bool:
    name = attachment.original_name
    if "交仓单" in name:
        return True
    if attachment.stored_path.suffix.lower() not in SPREADSHEET_SUFFIXES:
        return False
    _ensure_attachment_text(attachment)
    text = attachment.text
    lower = text.lower()
    tan_count = len(re.findall(r"\bTAN\s*#\s*\d+\b", text, flags=re.IGNORECASE))
    has_po_header = "customer po" in lower
    has_load_header = "卡板数" in text or ("卡板" in text and "箱数" in text)
    has_pcs_header = "pcs" in lower or "总数量" in text
    return tan_count >= 2 and has_po_header and has_load_header and has_pcs_header


def classify_attachments(attachments: list[Any]) -> tuple[Any | None, list[Any], list[Any], list[str]]:
    warnings: list[str] = []
    master_candidates: list[Any] = []
    dqths: list[Any] = []
    sos: list[Any] = []
    for attachment in attachments:
        name = attachment.original_name
        lower = name.lower()
        if re.search(r"\bDQT[H]?\d+", name, flags=re.IGNORECASE):
            attachment.role = "dqth"
            dqths.append(attachment)
        elif lower.endswith(tuple(SPREADSHEET_SUFFIXES)) and looks_like_tan_master_attachment(attachment):
            attachment.role = "master"
            master_candidates.append(attachment)
        else:
            if attachment.stored_path.suffix.lower() in CONTENT_MATCH_SUFFIXES:
                _ensure_attachment_text(attachment)
            attachment.role = "so"
            sos.append(attachment)
    master = master_candidates[-1] if master_candidates else None
    if not master:
        warnings.append("未识别到 Tan# 总表。")
    return master, dqths, sos, warnings


__all__ = ["classify_attachments", "looks_like_tan_master_attachment"]
