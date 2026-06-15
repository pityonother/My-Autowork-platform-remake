from __future__ import annotations

from app.modules.booking.flex_texas import FLEX_TEXAS_BOOKING_COLUMNS, SUPPLIER_NAME


SOURCE_KIND = "eml_pdf"

SOURCE_SHEETS = {
    "detail": [],
    "packadc": [],
}

TEMPLATE_CANDIDATES = [
    r"C:/Users/ac/Desktop/新建文件夹/smooth booking template.xlsx",
]

HEADER_ROW = 8
DATA_START_ROW = 10
DATA_END_ROW = 19

COLUMN_MAP = {column: ("flex_texas", column, None) for column in FLEX_TEXAS_BOOKING_COLUMNS}
CONSTANTS = {}
TEXT_TARGET_COLUMNS = {"PO No. *", "Invoice No.*", "Customer Part No. *", "Tray Type"}


def post_process(detail_rows, packadc_rows):
    return [{} for _row in detail_rows], []

