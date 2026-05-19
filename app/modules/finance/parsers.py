from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.shared.lazy_imports import lazy_module


pd = lazy_module("pandas")


def quantized(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) and pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def parse_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, str) and pd.isna(value):
        return Decimal("0.00")
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan":
        return Decimal("0.00")
    try:
        return quantized(Decimal(text))
    except Exception:  # noqa: BLE001
        return Decimal("0.00")


def parse_exchange_rate(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return quantized(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def parse_date_text(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, (int, float)) and 20000 <= float(value) <= 80000:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.replace(".", "", 1).isdigit():
            serial_value = float(stripped)
            if 20000 <= serial_value <= 80000:
                return (datetime(1899, 12, 30) + timedelta(days=serial_value)).date().isoformat()
    parsed = pd.to_datetime(value)
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def split_so_customer(raw_value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in raw_value.split("\\") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    if len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


PAYMENT_AMOUNT_RE = re.compile(r"(RMB|HKD)\s*([+-]?\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
PAYMENT_DESCRIPTION_DATE_RE = re.compile(
    r"(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"
)


def parse_payment_amount_text(value: object) -> tuple[str, Decimal, Decimal]:
    text = clean_text(value)
    if not text:
        return "", Decimal("0.00"), Decimal("0.00")
    match = PAYMENT_AMOUNT_RE.search(text.replace(" ", ""))
    if not match:
        return "", Decimal("0.00"), Decimal("0.00")
    currency = match.group(1).upper()
    amount = parse_decimal(match.group(2))
    if currency == "RMB":
        return currency, amount, Decimal("0.00")
    return currency, Decimal("0.00"), amount


def parse_payment_description_date(value: str, fallback_date: str) -> str:
    text = clean_text(value)
    if not text or not PAYMENT_DESCRIPTION_DATE_RE.fullmatch(text):
        return ""
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}", text):
        year = int(fallback_date[:4]) if fallback_date else datetime.now().year
        month_text, day_text = re.split(r"[/-]", text)
        try:
            return date(year, int(month_text), int(day_text)).isoformat()
        except ValueError:
            return ""
    return parse_date_text(text)


def split_invoice_payment_description(raw_value: str, fallback_date: str) -> tuple[str, str, str, str, str]:
    parts = [part.strip() for part in raw_value.split("\\") if part.strip()]
    reimbursement_date = fallback_date
    if parts:
        parsed_date = parse_payment_description_date(parts[-1], fallback_date)
        if parsed_date:
            reimbursement_date = parsed_date
            parts = parts[:-1]
    business_raw = "\\".join(parts)
    so_no, hawb_ref, forwarder = split_so_customer(business_raw)
    return business_raw, so_no, hawb_ref, forwarder, reimbursement_date


__all__ = ["parse_exchange_rate", "parse_payment_amount_text", "split_invoice_payment_description"]
