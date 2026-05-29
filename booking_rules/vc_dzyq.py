from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.shared.lazy_imports import lazy_module
from app_paths import RESOURCE_DIR, RUNTIME_DIR

from .common import PURCHASER_BY_PO_PREFIX

xlrd = lazy_module("xlrd")

SUPPLIER_NAME = "VC_DZYQ"
MIN_PACK_ENV_VAR = "VC_DZYQ_MIN_PACK_WORKBOOK"
MIN_PACK_WORKBOOK_NAME = "最小包装.xls"
MIN_PACK_WORKBOOK_CANDIDATES = [
    RUNTIME_DIR / "booking" / MIN_PACK_WORKBOOK_NAME,
    RUNTIME_DIR / MIN_PACK_WORKBOOK_NAME,
    RESOURCE_DIR / MIN_PACK_WORKBOOK_NAME,
    Path.cwd() / MIN_PACK_WORKBOOK_NAME,
    Path(r"C:/Users/ac/Documents/WeChat Files/wxid_u0o877oywf4k22/FileStorage/Temp/Copy/最小包装.xls"),
]
MIN_PACK_VALUE_HEADERS = ("最低补量", "最小包装数量", "最小包装数", "最小包装")

SOURCE_SHEETS = {
    "detail": ["清单", "packing", "packinglist", "PL"],
    "packadc": [],
}

HEADER_ROW = 8
DATA_START_ROW = 9
DATA_END_ROW = 19

COLUMN_MAP = {
    "订单号": ("detail", ("Customer_PO", "Customer_PO右侧一列"), "join_dash_zfill4"),
    "启益料号": ("detail", "PO Item", "as_text"),
    "数量": ("detail", "TI_MATERIAL", "as_number"),
    "纸箱数": ("detail", "Total Wght Unit", "as_number"),
    "净重": ("detail", ("BoxQty", "Net"), "weight_to_kg"),
    "毛重": ("detail", ("Net Wght Unit", "Total Wght"), "weight_to_kg"),
    "体积": ("row_extra", "Volume", "as_number"),
    "生产日期": ("row_extra", "Production Date", "as_text"),
    "产地 (made in)": ("detail", "PLS", None),
    "最小包装数": ("row_extra", "Min Pack Quantity", None),
    "每箱标准数": ("detail", "TI_MATERIAL", "as_number"),
}

CONSTANTS = {
    "商品名称": "IC",
    "单位": "PCS",
    "批次": "0",
    "品牌": "无",
    "LEDBinCode": "无",
}
TEXT_TARGET_COLUMNS = {"订单号", "启益料号", "生产日期", "批次"}
PURCHASER_PO_COLUMN = "Customer_PO"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return f"{value:.0f}"
    return str(value).strip()


def _min_pack_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _iter_min_pack_workbook_candidates():
    env_path = os.environ.get(MIN_PACK_ENV_VAR, "").strip()
    if env_path:
        yield Path(env_path).expanduser()
    yield from MIN_PACK_WORKBOOK_CANDIDATES


def _first_existing_min_pack_workbook() -> Path | None:
    for candidate in _iter_min_pack_workbook_candidates():
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=4)
def _load_min_pack_lookup(path_text: str, mtime_ns: int) -> dict[str, Any]:
    _ = mtime_ns
    book = xlrd.open_workbook(path_text, formatting_info=False)
    sheet = book.sheet_by_index(0)
    if sheet.nrows == 0:
        return {}
    headers = [_text(sheet.cell_value(0, col)) for col in range(sheet.ncols)]
    try:
        item_col = headers.index("品号")
    except ValueError:
        return {}
    min_pack_col = next((headers.index(header) for header in MIN_PACK_VALUE_HEADERS if header in headers), None)
    if min_pack_col is None:
        return {}
    lookup: dict[str, Any] = {}
    for row_index in range(1, sheet.nrows):
        item = _text(sheet.cell_value(row_index, item_col))
        if not item:
            continue
        lookup[item] = _min_pack_value(sheet.cell_value(row_index, min_pack_col))
    return lookup


def load_min_pack_lookup() -> tuple[dict[str, Any], str]:
    workbook = _first_existing_min_pack_workbook()
    if workbook is None:
        return {}, "未找到 VC_DZYQ 最小包装参考表：最小包装.xls。"
    lookup = _load_min_pack_lookup(str(workbook), workbook.stat().st_mtime_ns)
    if not lookup:
        return {}, f"VC_DZYQ 最小包装参考表缺少 品号/最低补量 数据：{workbook}"
    return lookup, ""


def _is_data_row(row: dict[str, Any]) -> bool:
    return _text(row.get("厂商编号")) == SUPPLIER_NAME and bool(_text(row.get("Customer_PO")))


def prepare_rows(detail_rows: list[dict[str, Any]]):
    data_rows = [dict(row) for row in detail_rows if _is_data_row(row)]
    warnings: list[str] = []
    if not data_rows:
        warnings.append("VC_DZYQ 表格未识别到有效明细行。")
    return data_rows, warnings


def post_process(detail_rows: list[dict[str, Any]], packadc_rows: list[dict[str, Any]]):
    today_text = date.today().strftime("%Y-%m-%d")
    min_pack_lookup, min_pack_warning = load_min_pack_lookup()
    warnings = [min_pack_warning] if min_pack_warning else []
    missing_items: set[str] = set()
    extras = []
    for index, row in enumerate(detail_rows):
        item = _text(row.get("PO Item"))
        min_pack_quantity = min_pack_lookup.get(item, "")
        if item and min_pack_lookup and min_pack_quantity == "":
            missing_items.add(item)
        extras.append(
            {
                "Production Date": today_text,
                "Volume": Decimal("0.01") if index == 0 else 0,
                "Min Pack Quantity": min_pack_quantity,
            }
        )
    if missing_items:
        warnings.append(f"VC_DZYQ 最小包装参考表未找到以下 PO Item：{', '.join(sorted(missing_items))}")
    return extras, warnings
