from __future__ import annotations

from app.modules.booking.flex_texas import FLEX_TEXAS_BOOKING_COLUMNS, SUPPLIER_NAME
from app_paths import RESOURCE_DIR, RUNTIME_DIR


SOURCE_KIND = "eml_pdf"

SOURCE_SHEETS = {
    "detail": [],
    "packadc": [],
}

FLEX_TEXAS_TEMPLATE_NAME = "smooth booking template.xlsx"
REQUIRE_TEMPLATE_CANDIDATE = True
TEMPLATE_CANDIDATES = [
    RUNTIME_DIR / "booking" / FLEX_TEXAS_TEMPLATE_NAME,
    RUNTIME_DIR / FLEX_TEXAS_TEMPLATE_NAME,
    RESOURCE_DIR / FLEX_TEXAS_TEMPLATE_NAME,
    RESOURCE_DIR / "samples" / "booking" / FLEX_TEXAS_TEMPLATE_NAME,
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
