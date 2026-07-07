from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.booking.body_validation_fields import SIL_FUCA_DYNAMIC_PO_PREFIXES
from app.modules.booking.body_validation_numeric import _decimal, _format_decimal
from app.modules.booking.sil_fuca_delivery import SilFucaDeliveryQuery, SilFucaDeliveryRecord


@dataclass
class _SilFucaDeliveryGroup:
    po: str
    po_base: str
    is_complete_po: bool
    pn: str
    quantity: Decimal
    rows: list[Any] = field(default_factory=list)


def _po_base(value: str) -> str:
    parts = (value or "").upper().split("-")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}-{parts[1]}"


def _valid_po_base(value: str) -> bool:
    parts = (value or "").upper().split("-")
    return len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 8 and parts[1].isdigit()


def _valid_po_no(value: str) -> bool:
    parts = value.split("-")
    return (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1]) == 8
        and parts[1].isdigit()
        and len(parts[2]) == 4
        and parts[2].isdigit()
    )


def _sil_fuca_delivery_groups(rows: list[Any]) -> list[_SilFucaDeliveryGroup]:
    groups: dict[tuple[str, str, bool], _SilFucaDeliveryGroup] = {}
    for row in rows:
        po = row.values.get("PO_No", "").upper()
        pn = row.values.get("Customer_Part_No", "").upper()
        quantity = _decimal(row.values.get("Quantity", ""))
        is_complete_po = _valid_po_no(po)
        po_base = _po_base(po)
        if (
            not (is_complete_po or _valid_po_base(po))
            or not po_base
            or po_base[:4] not in SIL_FUCA_DYNAMIC_PO_PREFIXES
            or not pn
            or quantity is None
            or quantity <= 0
        ):
            continue
        key = (po if is_complete_po else po_base, pn, is_complete_po)
        if key not in groups:
            groups[key] = _SilFucaDeliveryGroup(
                po=po if is_complete_po else po_base,
                po_base=po_base,
                is_complete_po=is_complete_po,
                pn=pn,
                quantity=Decimal("0"),
            )
        groups[key].quantity += quantity
        groups[key].rows.append(row)
    return list(groups.values())


def _matching_delivery_record(
    records: tuple[SilFucaDeliveryRecord, ...],
    query: SilFucaDeliveryQuery,
) -> SilFucaDeliveryRecord | None:
    for record in records:
        if record.po == query.po and record.product_code == query.pn:
            return record
    return None


def _delivery_record_problem(
    record: SilFucaDeliveryRecord,
    query: SilFucaDeliveryQuery,
    query_date: date,
) -> tuple[str, str] | None:
    if record.allocation_status == "已分配并使用":
        return "ASN", f"周期 {record.po} 已分配并使用。"
    if record.delivery_quantity is None:
        return "ASN", "周期清单接口没有返回 delivery_quantity，需人工确认。"
    if query.qty > record.delivery_quantity:
        return (
            "ASN",
            f"周期 {record.po} 数量不足：booking 合计 {_format_decimal(query.qty)} "
            f"> 周期数量 {_format_decimal(record.delivery_quantity)}。",
        )
    if record.delivery_date is None:
        return "ASN", "周期清单接口没有返回 delivery_date，需人工确认。"
    if query_date >= record.delivery_date:
        return (
            "ASN",
            f"周期 {record.po} 交货日期 {record.delivery_date:%Y-%m-%d} 不晚于当前查询日期 {query_date:%Y-%m-%d}。",
        )
    return None


def _delivery_record_detail(record: SilFucaDeliveryRecord, query: SilFucaDeliveryQuery, query_date: date) -> str:
    problem = _delivery_record_problem(record, query, query_date)
    status = "可用" if problem is None else problem[1]
    qty = _format_decimal(record.delivery_quantity) if record.delivery_quantity is not None else "未知"
    delivery_date = record.delivery_date.strftime("%Y-%m-%d") if record.delivery_date else "未知"
    allocation_status = record.allocation_status or "未使用"
    return f"{record.po}｜数量 {qty}｜日期 {delivery_date}｜{allocation_status}｜{status}"


def _delivery_candidates(
    records: tuple[SilFucaDeliveryRecord, ...],
    query: SilFucaDeliveryQuery,
    query_date: date,
) -> tuple[SilFucaDeliveryRecord, ...]:
    base = _po_base(query.po)
    candidates = [
        record
        for record in records
        if _po_base(record.po) == base
        and record.product_code == query.pn
        and _delivery_record_problem(record, query, query_date) is None
    ]
    return tuple(sorted(candidates, key=lambda item: item.po))


def _delivery_records_for_group(
    records: tuple[SilFucaDeliveryRecord, ...],
    group: _SilFucaDeliveryGroup,
) -> tuple[SilFucaDeliveryRecord, ...]:
    return tuple(
        sorted(
            (
                record
                for record in records
                if _po_base(record.po) == group.po_base and record.product_code == group.pn
            ),
            key=lambda item: item.po,
        )
    )
