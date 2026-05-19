from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.finance.parsers import quantized


def normalize_business_text(value: str) -> str:
    return " ".join((value or "").replace("\u00a0", " ").split())


def finance_business_amount(row: dict[str, Any]) -> float:
    currency = str(row.get("currency") or "").upper()
    if currency == "HKD":
        return float(row.get("amount_hkd") or 0)
    return float(row.get("amount_rmb") or 0)


def finance_business_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_business_text(str(row.get("remark") or "")),
        str(row.get("reimbursement_date") or ""),
        str(row.get("currency") or "").upper(),
        f"{finance_business_amount(row):.2f}",
    )


def finance_record_text_key(value: object) -> str:
    return normalize_business_text(str(value or "")).upper()


def finance_record_business_fields_match(candidate: Any, row: dict[str, Any]) -> bool:
    row_so = finance_record_text_key(row.get("so_no"))
    candidate_so = finance_record_text_key(candidate["so_no"])
    if not row_so or row_so != candidate_so:
        return False

    row_hawb = finance_record_text_key(row.get("hawb_ref"))
    row_forwarder = finance_record_text_key(row.get("forwarder"))
    candidate_hawb = finance_record_text_key(candidate["hawb_ref"])
    candidate_forwarder = finance_record_text_key(candidate["forwarder"])
    if row_hawb and candidate_hawb == row_hawb and row_forwarder and candidate_forwarder == row_forwarder:
        return True
    if row_hawb and row_forwarder and candidate_hawb == f"{row_hawb}/{row_forwarder}":
        return True
    if row_hawb and candidate_hawb == row_hawb:
        return True
    if row_forwarder and candidate_forwarder == row_forwarder:
        return True
    return False


def finance_export_amount_key(value: Decimal | float | int | str | None) -> str:
    return f"{quantized(Decimal(str(value or 0))):.2f}"


def finance_export_text_key(value: object) -> str:
    return normalize_business_text(str(value or "")).upper()


def finance_export_row_key(row: Any) -> tuple[str, str, str, str, str]:
    return (
        finance_export_text_key(row.forwarder_inv_no),
        finance_export_text_key(row.hawb_ref),
        finance_export_text_key(row.forwarder),
        finance_export_amount_key(row.special_handling),
        finance_export_amount_key(row.amount_hkd),
    )


__all__ = [
    "finance_business_amount",
    "finance_business_key",
    "finance_export_amount_key",
    "finance_export_row_key",
    "finance_export_text_key",
    "finance_record_business_fields_match",
    "finance_record_text_key",
    "normalize_business_text",
]
