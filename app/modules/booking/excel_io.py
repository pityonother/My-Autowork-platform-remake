from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.shared.lazy_imports import lazy_module
from app.shared.performance import cached_file_result


openpyxl = lazy_module("openpyxl")
xlrd = lazy_module("xlrd")


def normalize_key(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = re.sub(r"[\s\r\n\t*．.。:：()（）/#\\-]+", "", text)
    return text


def _cell_to_value(cell: Any) -> Any:
    if cell.ctype == xlrd.XL_CELL_EMPTY:
        return ""
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        value = cell.value
        if isinstance(value, float) and value.is_integer():
            return f"{value:.0f}"
        return value
    return cell.value


def find_sheet(book: Any, candidates: list[str]) -> Any | None:
    normalized_candidates = [normalize_key(item) for item in candidates]
    for sheet_name in book.sheet_names():
        sheet_key = normalize_key(sheet_name)
        if any(candidate and candidate in sheet_key for candidate in normalized_candidates):
            return book.sheet_by_name(sheet_name)
    return None


def find_openpyxl_sheet(wb: Any, candidates: list[str]) -> Any | None:
    normalized_candidates = [normalize_key(item) for item in candidates]
    for sheet_name in wb.sheetnames:
        sheet_key = normalize_key(sheet_name)
        if any(candidate and candidate in sheet_key for candidate in normalized_candidates):
            return wb[sheet_name]
    return None


def sheet_to_rows(sheet: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if sheet.nrows == 0:
        return [], []
    raw_headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    headers = build_headers_with_blank_aliases(raw_headers)
    rows: list[dict[str, Any]] = []
    for row_index in range(1, sheet.nrows):
        row: dict[str, Any] = {}
        empty = True
        for col_index, header in enumerate(headers):
            if not header:
                continue
            value = _cell_to_value(sheet.cell(row_index, col_index))
            if value not in ("", None):
                empty = False
            row[header] = value
        if not empty:
            rows.append(row)
    return rows, headers


def openpyxl_sheet_to_rows(sheet: Any) -> tuple[list[dict[str, Any]], list[str]]:
    values = list(sheet.iter_rows(values_only=True))
    if not values:
        return [], []
    raw_headers = [str(value).strip() if value is not None else "" for value in values[0]]
    headers = build_headers_with_blank_aliases(raw_headers)
    rows: list[dict[str, Any]] = []
    for raw_row in values[1:]:
        row: dict[str, Any] = {}
        empty = True
        for header, value in zip(headers, raw_row):
            if not header:
                continue
            if value not in ("", None):
                empty = False
            row[header] = value if value is not None else ""
        if not empty:
            rows.append(row)
    return rows, headers


def build_headers_with_blank_aliases(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    last_named = ""
    blank_after_named_count = 0
    for index, header in enumerate(raw_headers, start=1):
        if header:
            headers.append(header)
            last_named = header
            blank_after_named_count = 0
            continue
        if last_named and blank_after_named_count == 0:
            headers.append(f"{last_named}右侧一列")
        else:
            headers.append(f"__blank_col_{index}")
        blank_after_named_count += 1
    return headers


def load_rows_from_workbook(path: Path, candidates: list[str]) -> tuple[list[dict[str, Any]], list[str], str] | None:
    return cached_file_result(
        "booking.load_rows_from_workbook",
        path,
        lambda: _load_rows_from_workbook_uncached(path, candidates),
        extra_key=tuple(candidates),
    )


def _load_rows_from_workbook_uncached(path: Path, candidates: list[str]) -> tuple[list[dict[str, Any]], list[str], str] | None:
    suffix = path.suffix.lower()
    if suffix == ".xls":
        book = xlrd.open_workbook(str(path), formatting_info=False)
        sheet = find_sheet(book, candidates)
        if sheet is None:
            return None
        rows, headers = sheet_to_rows(sheet)
        return rows, headers, sheet.name
    if suffix == ".xlsx":
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = find_openpyxl_sheet(wb, candidates)
        if sheet is None:
            return None
        rows, headers = openpyxl_sheet_to_rows(sheet)
        return rows, headers, sheet.title
    return None


__all__ = ["load_rows_from_workbook"]
