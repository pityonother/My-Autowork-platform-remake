from __future__ import annotations

from typing import Any, Protocol


class BookingSupplierRule(Protocol):
    SUPPLIER_NAME: str
    SOURCE_SHEETS: dict[str, list[str]]
    HEADER_ROW: int
    DATA_START_ROW: int
    DATA_END_ROW: int
    COLUMN_MAP: dict[str, tuple[str, Any, str | None]]
    CONSTANTS: dict[str, Any]
    TEXT_TARGET_COLUMNS: set[str]

    def post_process(
        self,
        detail_rows: list[dict[str, Any]],
        packadc_rows: list[dict[str, Any]],
    ):
        ...
