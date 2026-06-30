from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .common import PURCHASER_BY_PO_PREFIX

SUPPLIER_NAME = "SIL-FUCA"

SOURCE_SHEETS = {
    "detail": ["detail"],
    "packadc": ["PACKADCXLS", "detail"],
}

HEADER_ROW = 8
DATA_START_ROW = 9
DATA_END_ROW = 19

COLUMN_MAP = {
    "订单号": ("detail", "Customer PO", "as_text"),
    "启益料号": ("detail", "Customer Part Number", "as_text"),
    "商品名称": ("detail", "HS Desc", None),
    "数量": ("detail", "Quantity", "as_number"),
    "净重": ("detail", "Net Weight", "as_number"),
    "毛重": ("detail", "Gross Weight", "as_number"),
    "生产日期": ("packadc_match", "DC", None),
    "产地 (made in)": ("detail", "CofO", "letters_only"),
    "批次": ("packadc_match", "Lot #", None),
    "品牌": ("detail", "MFR Name", None),
    "发票号": ("packadc_match", "Inv. Ref. No.", "as_text"),
}

CONSTANTS = {
    "单位": "PCS",
    "箱号": "0",
    "LEDBinCode": "无",
}

QUANTITY_COPY_COLUMNS = ["最小包装数", "每箱标准数"]
ZERO_AFTER_FIRST_COLUMNS = ["体积", "板数", "纸箱数"]
TEXT_TARGET_COLUMNS = {"启益料号", "发票号"}


def _as_key_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:.0f}"
        return format(value, "f").rstrip("0").rstrip(".")
    text = str(value).strip()
    if not text:
        return ""
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return text
    if dec == dec.to_integral_value():
        return f"{dec:.0f}"
    return format(dec, "f").rstrip("0").rstrip(".")


def _quantity_key(value: Any) -> str:
    text = _as_key_text(value)
    if not text:
        return "0"
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return text
    if dec == dec.to_integral_value():
        return f"{dec:.0f}"
    return format(dec.normalize(), "f")


def build_match_key(po: Any, part: Any, quantity: Any) -> tuple[str, str, str]:
    return (_as_key_text(po), _as_key_text(part), _quantity_key(quantity))


def post_process(detail_rows: list[dict[str, Any]], packadc_rows: list[dict[str, Any]]):
    if not packadc_rows:
        return [{} for _ in detail_rows], ["未找到 PACKADCXLS 数据，发票号、生产日期、批次将留空。"]

    warnings: list[str] = []
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []

    for row in packadc_rows:
        po = _as_key_text(row.get("Cust P/O"))
        part = _as_key_text(row.get("Cust Part"))
        inv = _as_key_text(row.get("Inv. Ref. No."))
        if not po or not part:
            continue
        base_key = (po, part, inv)
        if base_key not in grouped:
            grouped[base_key] = {
                "Cust P/O": po,
                "Cust Part": part,
                "Inv. Ref. No.": inv,
                "Quantity": Decimal("0"),
                "DC": row.get("DC"),
                "Lot #": row.get("Lot #"),
            }
            order.append(base_key)
        else:
            if not grouped[base_key].get("DC") and row.get("DC"):
                grouped[base_key]["DC"] = row.get("DC")
            if not grouped[base_key].get("Lot #") and row.get("Lot #"):
                grouped[base_key]["Lot #"] = row.get("Lot #")
        qty_text = _quantity_key(row.get("Quantity"))
        try:
            grouped[base_key]["Quantity"] += Decimal(qty_text or "0")
        except InvalidOperation:
            warnings.append(f"PACKADCXLS 数量无法识别：{qty_text}")

    deduped = [grouped[key] for key in order]
    match_by_key = {
        build_match_key(item["Cust P/O"], item["Cust Part"], item["Quantity"]): item
        for item in deduped
    }

    box_count = sum(1 for row in packadc_rows if _as_key_text(row.get("Box #")))
    extras: list[dict[str, Any]] = []
    unmatched = 0
    for row in detail_rows:
        key = build_match_key(row.get("Customer PO"), row.get("Customer Part Number"), row.get("Quantity"))
        match = match_by_key.get(key)
        if not match:
            unmatched += 1
            extras.append({"Box Count": box_count})
            continue
        extras.append(
            {
                "Inv. Ref. No.": match.get("Inv. Ref. No."),
                "DC": match.get("DC"),
                "Lot #": match.get("Lot #"),
                "Box Count": box_count,
            }
        )

    if len(deduped) != len(detail_rows):
        warnings.append(f"PACKADCXLS 汇总去重后 {len(deduped)} 条，detail 有 {len(detail_rows)} 条，请人工确认。")
    if unmatched:
        warnings.append(f"有 {unmatched} 条 detail 未能匹配到 PACKADCXLS 的发票号/生产日期/批次。")

    return extras, warnings
