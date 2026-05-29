from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from .common import PURCHASER_BY_PO_PREFIX

SUPPLIER_NAME = "VC_DZYQ"

SOURCE_SHEETS = {
    "detail": ["清单", "packing", "packinglist", "PL"],
    "packadc": [],
}

HEADER_ROW = 8
DATA_START_ROW = 9
DATA_END_ROW = 19

COLUMN_MAP = {
    "订单号": ("detail", "PO Item", "as_text"),
    "启益料号": ("detail", ("Customer_PO", "Customer_PO右侧一列"), "join_dash_zfill4"),
    "数量": ("detail", "TI_MATERIAL", "as_number"),
    "纸箱数": ("detail", "Total Wght Unit", "as_number"),
    "净重": ("detail", ("BoxQty", "Net"), "weight_to_kg"),
    "毛重": ("detail", ("Net Wght Unit", "Total Wght"), "weight_to_kg"),
    "体积": ("row_extra", "Volume", "as_number"),
    "生产日期": ("row_extra", "Production Date", "as_text"),
    "产地 (made in)": ("detail", "PLS", None),
    "最小包装数": ("detail", "TI_MATERIAL", "as_number"),
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
    return "" if value is None else str(value).strip()


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
    extras = [
        {
            "Production Date": today_text,
            "Volume": Decimal("0.01") if index == 0 else 0,
        }
        for index, _row in enumerate(detail_rows)
    ]
    return extras, []
