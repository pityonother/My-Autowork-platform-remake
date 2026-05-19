from __future__ import annotations

from typing import Any

from .common import PURCHASER_BY_PO_PREFIX

SUPPLIER_NAME = "SIL-WEIKENG"

SOURCE_SHEETS = {
    "detail": ["packing", "packinglist", "PL"],
    "packadc": [],
}

PURCHASER_PO_COLUMN = "採購商訂單號"

HEADER_ROW = 8
DATA_START_ROW = 9
DATA_END_ROW = 19

TEMPLATE_CANDIDATES = [
    r"C:/Users/ac/Desktop/1/booking_template_zh.xlsx",
]

COLUMN_MAP = {
    "订单号": ("detail", ("採購商訂單號", "訂單項次"), "join_dash_zfill4"),
    "产地 (made in)": ("detail", "產地", None),
    "品牌": ("detail", "品牌", None),
    "发票号": ("detail", "供應商發票號", "as_text"),
    "纸箱数": ("row_extra", "Total Box Count", "as_number"),
    "箱号": ("detail", "箱號", "as_text"),
    "数量": ("detail", "數量", "as_number"),
    "单位": ("detail", "數量單位", None),
    "毛重": ("detail", "毛重", "as_number"),
    "净重": ("detail", "淨重", "as_number"),
    "体积": ("detail", "材積", "volume_cm_to_m3"),
    "生产日期": ("detail", "DATECODE", "as_text"),
    "启益料号": ("detail", "採購商物料號", "as_text"),
    "批次": ("detail", "LOTNO", None),
    "商品名称": ("detail", "IC屬性", None),
    "最小包装数": ("detail", "最小包装数量", "as_number"),
    "每箱标准数": ("detail", "每箱数量", "as_number"),
}

CONSTANTS = {
    "LEDBinCode": "无",
}

QUANTITY_COPY_COLUMNS = []
OPTIONAL_SOURCE_COLUMNS = {"最小包装数量", "每箱数量"}
FALLBACK_TO_QUANTITY_COLUMNS = ["最小包装数", "每箱标准数"]
TEXT_TARGET_COLUMNS = {"订单号", "启益料号", "发票号", "生产日期", "批次"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_data_row(row: dict[str, Any]) -> bool:
    return bool(_text(row.get("採購商訂單號")) and _text(row.get("採購商物料號")))


def prepare_rows(detail_rows: list[dict[str, Any]]):
    summary_box_count = ""
    data_rows: list[dict[str, Any]] = []
    for row in detail_rows:
        if _is_data_row(row):
            data_rows.append(dict(row))
        elif _text(row.get("總箱數")):
            summary_box_count = row.get("總箱數")

    if not summary_box_count:
        for row in data_rows:
            if _text(row.get("總箱數")):
                summary_box_count = row.get("總箱數")
                break

    warnings: list[str] = []
    if not data_rows:
        warnings.append("WEIKENG 表格未识别到有效明细行。")
    if not summary_box_count:
        warnings.append("WEIKENG 表格未识别到总结行的总箱数，纸箱数将留空。")

    for row in data_rows:
        row["_summary_box_count"] = summary_box_count
    return data_rows, warnings


def post_process(detail_rows: list[dict[str, Any]], packadc_rows: list[dict[str, Any]]):
    extras: list[dict[str, Any]] = []
    for index, row in enumerate(detail_rows):
        extras.append({"Total Box Count": row.get("_summary_box_count") if index == 0 else 0})
    return extras, []
