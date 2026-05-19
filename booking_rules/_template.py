from __future__ import annotations

SUPPLIER_NAME = "NEW_SUPPLIER"

SOURCE_SHEETS = {
    "detail": ["detail"],
    "packadc": ["PACKADCXLS"],
}

HEADER_ROW = 8
DATA_START_ROW = 9
DATA_END_ROW = 19

COLUMN_MAP = {
    # "booking form target header": ("source_alias", "source column header", "cleaner_name")
}

CONSTANTS = {
    # "booking form target header": "fixed value"
}

TEXT_TARGET_COLUMNS = set()


def post_process(detail_rows, packadc_rows):
    return [{} for _ in detail_rows], []

