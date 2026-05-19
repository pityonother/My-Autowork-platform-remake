from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.shared.lazy_imports import lazy_module


pd = lazy_module("pandas")


def normalize_header_name(value: object) -> str:
    return str(value or "").strip().replace("\n", "").replace(" ", "").lower()


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text.lower() == "nan":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def quantized(value: Decimal | None, places: str = "0.01") -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(places))


def load_excel_file(path: Path) -> tuple[pd.ExcelFile, str]:
    last_error: Exception | None = None
    for engine in ["openpyxl", "xlrd"]:
        try:
            return pd.ExcelFile(path, engine=engine), engine
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    raise last_error
