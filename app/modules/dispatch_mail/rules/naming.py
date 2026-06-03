from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "attachment"


def attachment_extension(name: str) -> str:
    suffix = Path(name).suffix
    return suffix if suffix else ".bin"


def display_number(value: Decimal) -> str:
    value = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if value == value.to_integral_value():
        return str(int(value))
    return str(value.normalize())


def dispatch_load_label(ticket: Any) -> str:
    pallets_text = display_number(ticket.pallets)
    cartons_text = display_number(ticket.cartons)
    if ticket.show_carton_count_in_title and ticket.cartons > 0:
        return f"{pallets_text}板+{cartons_text}箱"
    return f"{pallets_text}板"


def build_dispatch_attachment_name(load_text: str, attachment_kind: str, order: int, extension: str) -> str:
    attachment_label = "装箱单" if attachment_kind == "dqth" else "交仓文件"
    return f"{load_text}{attachment_label}({order}){extension}"


def pick_final_attachment_name(
    *,
    current_name: str,
    original_name: str,
    previous_suggested_name: str,
    new_suggested_name: str,
) -> str:
    normalized_current = current_name.strip()
    if not normalized_current or normalized_current in {original_name, previous_suggested_name}:
        return new_suggested_name
    return normalized_current


def apply_attachment_names(tickets: list[Any], dqths: list[Any], sos: list[Any]) -> None:
    dqth_load_counts: dict[str, int] = {}
    so_load_counts: dict[str, int] = {}
    for ticket in tickets:
        load_text = dispatch_load_label(ticket)
        matched_dqths = getattr(ticket, "dqths", None) or ([ticket.dqth] if getattr(ticket, "dqth", None) else [])
        matched_sos = getattr(ticket, "sos", None) or ([ticket.so] if getattr(ticket, "so", None) else [])
        ticket.dqth_expected_order = dqth_load_counts.get(load_text, 0) + 1
        ticket.so_expected_order = so_load_counts.get(load_text, 0) + 1
        for dqth in matched_dqths:
            order = dqth_load_counts.get(load_text, 0) + 1
            dqth_load_counts[load_text] = order
            name = build_dispatch_attachment_name(
                load_text,
                "dqth",
                order,
                attachment_extension(dqth.attachment.original_name),
            )
            previous_suggested_name = dqth.suggested_name
            dqth.suggested_name = name
            dqth.suggested_order = order
            dqth.final_name = pick_final_attachment_name(
                current_name=dqth.final_name,
                original_name=dqth.attachment.original_name,
                previous_suggested_name=previous_suggested_name,
                new_suggested_name=name,
            )
        for so in matched_sos:
            order = so_load_counts.get(load_text, 0) + 1
            so_load_counts[load_text] = order
            name = build_dispatch_attachment_name(
                load_text,
                "so",
                order,
                attachment_extension(so.attachment.original_name),
            )
            previous_suggested_name = so.suggested_name
            so.suggested_name = name
            so.suggested_order = order
            so.final_name = pick_final_attachment_name(
                current_name=so.final_name,
                original_name=so.attachment.original_name,
                previous_suggested_name=previous_suggested_name,
                new_suggested_name=name,
            )
    for dqth in dqths:
        if dqth.matched_ticket_index is None:
            dqth.suggested_name = ""
            dqth.suggested_order = None
            if not dqth.final_name or dqth.final_name == dqth.suggested_name:
                dqth.final_name = dqth.attachment.original_name
    for so in sos:
        if so.matched_ticket_index is None:
            so.suggested_name = ""
            so.suggested_order = None
            if not so.final_name or so.final_name == so.suggested_name:
                so.final_name = so.attachment.original_name


__all__ = ["apply_attachment_names", "build_dispatch_attachment_name", "pick_final_attachment_name", "unique_filename"]


def unique_filename(filename: str, used_names: set[str]) -> str:
    safe = safe_filename(filename)
    if safe not in used_names:
        used_names.add(safe)
        return safe
    path = Path(safe)
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = f"{stem}({counter}){suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1
