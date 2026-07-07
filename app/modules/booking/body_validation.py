from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from app.modules.booking.body_validation_models import (
    BookingBodyFix,
    BookingBodyIssue,
    BookingBodyRow,
    BookingBodyValidationPreview,
    _field_label,
    _issue,
    _source_issue,
)
from app.modules.booking.body_validation_numeric import (
    _decimal,
    _format_decimal,
    _normalize_numeric_text,
    _parse_per_box_expression,
    _parse_simple_numeric_expression,
    _per_box_number_satisfies_rule,
)
from app.modules.booking.body_validation_delivery import (
    _SilFucaDeliveryGroup,
    _delivery_candidates,
    _delivery_record_detail,
    _delivery_record_problem,
    _delivery_records_for_group,
    _matching_delivery_record,
    _sil_fuca_delivery_groups,
    _valid_po_base,
    _valid_po_no,
)
from app.modules.booking.sil_fuca_delivery import (
    SilFucaDeliveryClient,
    SilFucaDeliveryQuery,
    SilFucaDeliveryRecord,
)
from app.modules.booking.body_validation_fields import (
    ALLOW_ZERO_NUMERIC_FIELDS,
    BODY_FIELDS,
    FALLBACK_COUNTRY_KEYS,
    FIELDS_BY_CODE,
    INTEGER_FIELDS,
    POSITIVE_WEIGHT_PO_PREFIXES,
    REQUIRED_FIELDS,
    SPECIAL_COUNTRY_KEYS,
    UNIT_NORMALIZABLE_NUMERIC_FIELDS,
    WEIGHT_AVERAGE_SCALE,
)
from app.shared.lazy_imports import lazy_module


openpyxl = lazy_module("openpyxl")


def _country_lookup_key(value: str) -> str:
    from app.modules.booking.legacy_adapter import _country_lookup_key as legacy_country_lookup_key

    return legacy_country_lookup_key(value)


def load_country_abbr_lookup() -> tuple[dict[str, str], str]:
    from app.modules.booking.legacy_adapter import load_country_abbr_lookup as legacy_load_country_abbr_lookup

    return legacy_load_country_abbr_lookup()


AMBIGUOUS_NA_CASE_MANUAL_FIELDS = {
    "Pkgs",
    "FJZ",
    "G_Wt",
    "CBM",
    "Pallet",
    "Batch_No",
    "madeDate",
    "min_package",
}


def _valid_excel_date_number_format(number_format: str) -> bool:
    fmt = (number_format or "").lower().split(";")[0]
    fmt = re.sub(r"\[\$-[^\]]+\]", "", fmt)
    fmt = fmt.replace("\\", "").replace('"', "").replace(" ", "")
    return fmt == "yyyy-mm-dd"


def _needs_excel_date_format_fix(row: BookingBodyRow) -> bool:
    value = row.values.get("madeDate", "")
    if "madeDate" not in row.date_cells or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    return not _valid_excel_date_number_format(row.cell_formats.get("madeDate", ""))


def _example_date_display(value: str, number_format: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    fmt = (number_format or "").lower().split(";")[0]
    if fmt in {"mm-dd-yy", "mm/dd/yy", "m/d/yy", "m-d-yy"}:
        return f"{parsed.year}/{parsed.month}/{parsed.day}"
    separator = "/" if "/" in fmt else "-"
    year = f"{parsed.year:04d}" if "yyyy" in fmt else f"{parsed.year % 100:02d}"
    month = f"{parsed.month:02d}" if "mm" in fmt else str(parsed.month)
    day = f"{parsed.day:02d}" if "dd" in fmt else str(parsed.day)
    if fmt.startswith("yyyy"):
        return separator.join([year, month, day])
    return separator.join([month, day, year])


def _date_format_issue_message(row: BookingBodyRow) -> str:
    value = row.values.get("madeDate", "")
    number_format = row.cell_formats.get("madeDate", "") or "未设置"
    original_display = _example_date_display(value, number_format)
    return (
        f"Production date 原 Excel 格式是 {number_format}，原显示类似 {original_display}；"
        f"系统要求统一为 yyyy-mm-dd，建议显示为 {value}。"
    )


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:.0f}"
        return format(value, "f").rstrip("0").rstrip(".")
    text = str(value).strip()
    try:
        dec = Decimal(text.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return text
    if dec == dec.to_integral_value():
        return f"{dec:.0f}"
    return format(dec, "f").rstrip("0").rstrip(".")


def _normalize_import_value(field_code: str, value: Any) -> str:
    text = _cell_text(value).upper()
    if field_code != "brand":
        text = re.sub(r"\s+", "", text)
    return text.strip()


def _is_empty_row(values: dict[str, str]) -> bool:
    return all(not value for code, value in values.items() if code != "Line")


def _is_missing(value: str) -> bool:
    return value != "0" and not value


def _is_no_value(value: str, *, include_zero: bool = False) -> bool:
    normalized = (value or "").strip().upper()
    return not normalized or normalized == "NA" or (include_zero and normalized == "0")


def _suggest_po_no(value: str) -> str | None:
    raw = (value or "").strip().upper()
    if not raw:
        return None
    normalized = re.sub(r"[\s_／/－—–]+", "-", raw)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if _valid_po_no(normalized) and normalized != value:
        return normalized
    compact = re.sub(r"[^A-Z0-9]", "", raw)
    match = re.fullmatch(r"([A-Z0-9]{4})(\d{8})(\d{4})", compact)
    if not match:
        return None
    suggested = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return suggested if suggested != value else None


def _clean_customer_part_no(value: str) -> str | None:
    cleaned = re.sub(r"[\s\-/\\／－—–]+", "", value or "")
    if cleaned and cleaned != value and re.fullmatch(r"[A-Za-z0-9]+", cleaned):
        return cleaned
    return None


def _suggest_made_in(value: str) -> str | None:
    key = _country_lookup_key(value)
    if key == "TW":
        return "TW,CN"
    if key == "TAIWAN":
        return "Taiwan,China"
    return None


def _format_date_candidate(year: str, month: str, day: str) -> str | None:
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d")


def _extract_date_candidates(value: str) -> tuple[str, ...]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", value):
        add(_format_date_candidate(match.group(1), match.group(2), match.group(3)))

    for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)", value):
        add(_format_date_candidate(match.group(1), match.group(2), match.group(3)))

    return tuple(candidates)


def _extract_week_code_candidate(value: str) -> str | None:
    match = re.fullmatch(r"((?:\d{4})|(?:\d{6}))[A-Z]+", (value or "").strip().upper())
    return match.group(1) if match else None


def _per_box_fallback_fix(values: dict[str, str]) -> BookingBodyFix | None:
    min_package_number = _decimal(values.get("min_package", ""))
    if min_package_number is not None and min_package_number > 0:
        fixed = _format_decimal(min_package_number)
        return BookingBodyFix(fixed, f"按 Min package 默认补为 {fixed}", "per_box_from_min_package")
    quantity_number = _decimal(values.get("Quantity", ""))
    if quantity_number is not None and quantity_number > 0:
        fixed = _format_decimal(quantity_number)
        return BookingBodyFix(fixed, f"Min package 为空，按 Quantity 默认补为 {fixed}", "per_box_from_quantity")
    return None

def _set_delivery_match(
    group: _SilFucaDeliveryGroup,
    status: str,
    message: str,
    *,
    options: tuple[str, ...] = (),
) -> None:
    for row in group.rows:
        row.delivery_match_status = status
        row.delivery_match_message = message
        row.delivery_match_options = options


def _append_delivery_issue(
    *,
    group: _SilFucaDeliveryGroup,
    field_code: str,
    message: str,
    issues: list[BookingBodyIssue],
    source_issues: list[BookingBodyIssue],
    suggestion: str = "",
    correction_options: tuple[str, ...] = (),
    correction_kind: str = "sil_fuca_delivery",
) -> None:
    for row in group.rows:
        issues.append(
            _issue(
                row,
                field_code,
                message,
                suggestion,
                correction_options=correction_options,
                correction_kind=correction_kind,
            )
        )
        source_issues.append(
            _source_issue(
                row,
                field_code,
                message,
                suggestion,
                correction_options=correction_options,
                correction_kind=correction_kind,
            )
        )


def _apply_sil_fuca_delivery_checks(
    rows: list[BookingBodyRow],
    *,
    client: SilFucaDeliveryClient,
    query_date: date,
    apply_fixes: bool,
) -> tuple[int, list[BookingBodyIssue], list[BookingBodyIssue], list[str]]:
    groups = _sil_fuca_delivery_groups(rows)
    issues: list[BookingBodyIssue] = []
    source_issues: list[BookingBodyIssue] = []
    warnings: list[str] = []
    fix_count = 0
    if not groups:
        return fix_count, issues, source_issues, warnings

    all_records: tuple[SilFucaDeliveryRecord, ...] | None = None

    def load_all_records() -> tuple[SilFucaDeliveryRecord, ...]:
        nonlocal all_records
        if all_records is None:
            all_records = client.get_all_delivery_list()
        return all_records

    for group in groups:
        query = SilFucaDeliveryQuery(po=group.po, pn=group.pn, qty=group.quantity)
        response: Any = None

        if group.is_complete_po:
            response_errors: tuple[str, ...] = ()
            try:
                response = client.get_delivery_list_new(query)
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                response = None

            if response is not None:
                response_errors = tuple(getattr(response, "errors", ()) or ())
                record = _matching_delivery_record(response.records, query)
                if record is not None:
                    problem = _delivery_record_problem(record, query, query_date)
                    if problem is not None:
                        _set_delivery_match(group, "error", problem[1])
                        _append_delivery_issue(
                            group=group,
                            field_code=problem[0],
                            message=problem[1],
                            issues=issues,
                            source_issues=source_issues,
                            correction_kind="sil_fuca_delivery_invalid",
                        )
                    else:
                        _set_delivery_match(group, "ok", f"周期 {record.po} 匹配成功。")
                    continue

            try:
                records_for_group = _delivery_records_for_group(load_all_records(), group)
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                message = "；".join(response_errors) if response_errors else "完整 PO 周期查询失败，需人工确认。"
                _set_delivery_match(group, "error", message)
                _append_delivery_issue(
                    group=group,
                    field_code="ASN",
                    message=message,
                    issues=issues,
                    source_issues=source_issues,
                    correction_kind="sil_fuca_delivery_missing",
                )
                continue

            candidate_records = _delivery_candidates(records_for_group, query, query_date)
            if candidate_records:
                options = tuple(record.po for record in candidate_records)
                details = tuple(_delivery_record_detail(record, query, query_date) for record in candidate_records)
                if len(candidate_records) == 1:
                    message = (
                        f"当前完整 PO {group.po} 未匹配成功；周期清单存在可用项次 {options[0]}，"
                        "请人工确认后再修改 PO No.。"
                    )
                else:
                    message = (
                        f"当前完整 PO {group.po} 未匹配成功；周期清单存在多个可用项次："
                        f"{'、'.join(options)}，请人工确认。"
                    )
                _set_delivery_match(group, "warning", message, options=details)
                _append_delivery_issue(
                    group=group,
                    field_code="ASN",
                    message=message,
                    issues=issues,
                    source_issues=source_issues,
                    suggestion=options[0],
                    correction_options=options,
                    correction_kind="sil_fuca_delivery_candidates",
                )
                for row in group.rows:
                    row.correction_options["PO_No"] = options
                    row.correction_kinds["PO_No"] = "sil_fuca_delivery_candidates"
                continue

            if records_for_group:
                details = tuple(_delivery_record_detail(record, query, query_date) for record in records_for_group)
                message = (
                    f"当前完整 PO {group.po} 未匹配成功；找到同 PO 基础号和 PN 的周期记录，"
                    "但没有可用周期：" + "；".join(details)
                )
                _set_delivery_match(group, "error", message, options=details)
            else:
                message = (
                    "；".join(response_errors)
                    if response_errors
                    else f"当前完整 PO {group.po} 匹配不上周期交货清单，请检查是否有上传。"
                )
                _set_delivery_match(group, "error", message)
            _append_delivery_issue(
                group=group,
                field_code="ASN",
                message=message,
                issues=issues,
                source_issues=source_issues,
                correction_kind="sil_fuca_delivery_missing",
            )
            continue

        try:
            records_for_group = _delivery_records_for_group(load_all_records(), group)
        except Exception as exc:  # noqa: BLE001
            warnings.append(str(exc))
            continue

        candidate_records = _delivery_candidates(records_for_group, query, query_date)

        if len(candidate_records) == 1:
            candidate = candidate_records[0]
            message = f"周期清单匹配到可用项次，建议 PO No. 改为 {candidate.po}。"
            _set_delivery_match(group, "ok", f"周期 {candidate.po} 匹配成功。")
            for row in group.rows:
                if row.values.get("PO_No") != candidate.po:
                    source_issues.append(
                        _source_issue(
                            row,
                            "PO_No",
                            message,
                            candidate.po,
                            correction_options=(candidate.po,),
                            correction_kind="sil_fuca_delivery_po",
                        )
                    )
                    row.values["PO_No"] = candidate.po
                    row.fixed_fields.add("PO_No")
                    row.correction_options["PO_No"] = (candidate.po,)
                    row.correction_kinds["PO_No"] = "sil_fuca_delivery_po"
                    fix_count += 1
            continue

        if len(candidate_records) > 1:
            options = tuple(record.po for record in candidate_records)
            details = tuple(_delivery_record_detail(record, query, query_date) for record in candidate_records)
            message = f"周期清单匹配到多个可用项次：{'、'.join(options)}，需要人工确认。"
            _set_delivery_match(group, "warning", message, options=details)
            _append_delivery_issue(
                group=group,
                field_code="ASN",
                message=message,
                issues=issues,
                source_issues=source_issues,
                suggestion=options[0],
                correction_options=options,
                correction_kind="sil_fuca_delivery_candidates",
            )
            for row in group.rows:
                row.correction_options["PO_No"] = options
                row.correction_kinds["PO_No"] = "sil_fuca_delivery_candidates"
            continue

        if records_for_group:
            details = tuple(_delivery_record_detail(record, query, query_date) for record in records_for_group)
            message = "找到了同 PO 基础号和 PN 的周期记录，但没有可用周期：" + "；".join(details)
            _set_delivery_match(group, "error", message, options=details)
        else:
            message = "匹配不上周期交货清单，请检查是否有上传。"
            if response is not None and getattr(response, "errors", ()):
                message = "；".join(response.errors)
            _set_delivery_match(group, "error", message)
        _append_delivery_issue(
            group=group,
            field_code="ASN",
            message=message,
            issues=issues,
            source_issues=source_issues,
            correction_kind="sil_fuca_delivery_missing",
        )

    return fix_count, issues, source_issues, warnings


def _valid_delivery_note(value: str) -> bool:
    if len(value) == 15:
        return True
    last10 = value[-10:]
    if len(last10) < 10:
        return False
    if last10[0] != "-" or last10[7] != "-":
        return False
    return bool(re.fullmatch(r"\d{8}", last10[1:7] + last10[8:]))


def _country_keys() -> tuple[set[str], str]:
    lookup, warning = load_country_abbr_lookup()
    if lookup:
        keys = set(lookup)
        keys.update(_country_lookup_key(value) for value in lookup.values())
        keys.update(SPECIAL_COUNTRY_KEYS)
        return keys, warning
    return set(FALLBACK_COUNTRY_KEYS) | SPECIAL_COUNTRY_KEYS, warning


def _sheet_end_row(ws: Any, start_row: int) -> int:
    for row_index in range(start_row, ws.max_row + 1):
        for col_index in range(1, 28):
            text = _cell_text(ws.cell(row_index, col_index).value).upper()
            if "TOTAL" in text:
                return row_index
    return ws.max_row + 1


def _load_rows(workbook_bytes: bytes) -> tuple[list[BookingBodyRow], str]:
    wb = openpyxl.load_workbook(BytesIO(workbook_bytes), data_only=True)
    ws = wb[wb.sheetnames[0]]
    start_row = 10 if _cell_text(ws["A9"].value).upper() == "SAMPLE" else 9
    end_row = _sheet_end_row(ws, start_row)
    purchaser = _cell_text(ws["K4"].value)
    rows: list[BookingBodyRow] = []
    for excel_row in range(start_row, end_row):
        values: dict[str, str] = {}
        cell_formats: dict[str, str] = {}
        date_cells: set[str] = set()
        for body_field in BODY_FIELDS:
            cell = ws[f"{body_field.column_letter}{excel_row}"]
            values[body_field.code] = _normalize_import_value(body_field.code, cell.value)
            cell_formats[body_field.code] = cell.number_format or ""
            if isinstance(cell.value, (datetime, date)):
                date_cells.add(body_field.code)
        if _is_empty_row(values):
            continue
        rows.append(
            BookingBodyRow(
                excel_row=excel_row,
                values=values,
                source_values=values.copy(),
                cell_formats=cell_formats,
                date_cells=date_cells,
            )
        )
    return rows, purchaser


def _auto_fix_value(field_code: str, values: dict[str, str]) -> BookingBodyFix | None:
    value = values.get(field_code, "")
    if field_code == "case_number" and _is_missing(value):
        return BookingBodyFix("0", "箱号为空时补 0", "default_zero")
    if field_code == "Invoice_No":
        fixed = re.sub(r"[^0-9A-Za-z]", "", value)
        return BookingBodyFix(fixed, f"清理为 {fixed}", "text_clean") if fixed and fixed != value else None
    if field_code == "Customer_Part_No":
        fixed = _clean_customer_part_no(value)
        if fixed:
            return BookingBodyFix(fixed, f"去除空格、横杠、斜杠后为 {fixed}", "text_clean")
    if field_code == "PO_No":
        fixed = _suggest_po_no(value)
        if fixed:
            return BookingBodyFix(fixed, f"PO 格式建议为 {fixed}", "po_format_suggestion")
    if field_code in {"Batch_No"} and _is_missing(value):
        return BookingBodyFix("0", "空值补 0", "default_zero")
    if field_code == "brand" and (not value.strip() or value.strip().upper() == "NA"):
        return BookingBodyFix("无", "无品牌时填写“无”", "default_text")
    if field_code == "LEDBinCode" and _is_no_value(value):
        return BookingBodyFix("无", "空值补“无”", "default_text")
    if field_code == "unit" and _is_missing(value):
        return BookingBodyFix("PCS", "空单位补 PCS", "default_text")
    if field_code == "Made_In":
        fixed = _suggest_made_in(value)
        if fixed:
            return BookingBodyFix(fixed, f"台湾产地按系统要求写为 {fixed}", "made_in_tw")
    if field_code == "Pallet" and _is_no_value(value):
        return BookingBodyFix("0", "Pallet 为空或 NA 时补 0", "default_zero")
    if field_code in UNIT_NORMALIZABLE_NUMERIC_FIELDS and value:
        fixed_number = _normalize_numeric_text(value)
        if fixed_number is not None and fixed_number != value:
            return BookingBodyFix(fixed_number, f"去掉单位或千分位后为 {fixed_number}", "normalize_number")
        calculated = _parse_simple_numeric_expression(value)
        if calculated is not None and calculated != value:
            return BookingBodyFix(calculated, f"算式计算为 {calculated}", "calculate_number")
    if field_code in INTEGER_FIELDS:
        number = _decimal(value)
        if number is not None and number == number.to_integral_value() and value != f"{number:.0f}":
            fixed = f"{number:.0f}"
            return BookingBodyFix(fixed, f"整数格式统一为 {fixed}", "integer")
    if field_code == "madeDate" and value:
        week_code = _extract_week_code_candidate(value)
        if week_code:
            return BookingBodyFix(week_code, f"周数去掉字母后为 {week_code}", "date_week_normalize", (week_code,))
        candidates = _extract_date_candidates(value)
        if len(candidates) >= 2:
            return BookingBodyFix(
                candidates[0],
                "识别到多个生产日期，默认先取第一个；页面可人工选择或手填覆盖",
                "date_choice",
                candidates,
            )
        if len(candidates) == 1 and candidates[0] != value:
            return BookingBodyFix(candidates[0], f"日期格式统一为 {candidates[0]}", "date_normalize", candidates)
    if field_code == "per_box":
        fallback_fix = _per_box_fallback_fix(values)
        if _is_missing(value):
            return fallback_fix
        parsed_expression = _parse_per_box_expression(value)
        if (
            parsed_expression is not None
            and parsed_expression != value
            and _per_box_number_satisfies_rule(_decimal(parsed_expression), values.get("min_package", ""))
        ):
            return BookingBodyFix(parsed_expression, f"表达式换算为 {parsed_expression}", "per_box_expression")
        calculated = _parse_simple_numeric_expression(value)
        if (
            calculated is not None
            and calculated != value
            and _per_box_number_satisfies_rule(_decimal(calculated), values.get("min_package", ""))
        ):
            return BookingBodyFix(calculated, f"算式计算为 {calculated}", "calculate_number")
        if not _per_box_number_satisfies_rule(_decimal(value), values.get("min_package", "")):
            return fallback_fix
    return None


def _apply_packaging_quantity_fallback(row: BookingBodyRow) -> int:
    min_package = row.source_values.get("min_package", row.values.get("min_package", ""))
    per_box = row.source_values.get("per_box", row.values.get("per_box", ""))
    quantity = row.values.get("Quantity", "")
    quantity_number = _decimal(quantity) if quantity else None
    if not (
        _is_no_value(min_package)
        and _is_no_value(per_box)
        and quantity_number is not None
        and quantity_number > 0
    ):
        return 0

    fixed_quantity = _format_decimal(quantity_number)
    fix_count = 0
    for field_code in ("min_package", "per_box"):
        if row.values.get(field_code, "") == fixed_quantity:
            continue
        row.values[field_code] = fixed_quantity
        row.fixed_fields.add(field_code)
        row.correction_kinds[field_code] = "fallback_quantity"
        fix_count += 1
    return fix_count


def _split_decimal_total(total: Decimal, count: int) -> list[Decimal]:
    if count <= 1:
        return [total]
    share = (total / Decimal(count)).quantize(WEIGHT_AVERAGE_SCALE)
    values = [share for _ in range(count - 1)]
    values.append(total - sum(values, Decimal("0")))
    return values


def _is_ambiguous_na_case_missing_line(row: BookingBodyRow) -> bool:
    if row.values.get("case_number", "").strip().upper() != "NA":
        return False
    return any(_is_no_value(row.values.get(field_code, ""), include_zero=True) for field_code in ("Pkgs", "FJZ", "G_Wt"))


def _same_po_pn(first: BookingBodyRow, second: BookingBodyRow) -> bool:
    return (
        first.values.get("PO_No", "").strip().upper() == second.values.get("PO_No", "").strip().upper()
        and first.values.get("Customer_Part_No", "").strip().upper()
        == second.values.get("Customer_Part_No", "").strip().upper()
    )


def _apply_previous_line_weight_average_for_na_case(rows: list[BookingBodyRow]) -> int:
    fix_count = 0
    for index, row in enumerate(rows):
        if index == 0 or not _is_ambiguous_na_case_missing_line(row):
            continue
        previous = rows[index - 1]
        if not _same_po_pn(previous, row):
            continue
        for field_code in ("FJZ", "G_Wt"):
            previous_value = _decimal(previous.values.get(field_code, ""))
            current_value = _decimal(row.values.get(field_code, ""))
            if previous_value is None or previous_value <= 0:
                continue
            if current_value is not None and current_value > 0:
                continue
            total = previous_value + (current_value or Decimal("0"))
            averaged_values = _split_decimal_total(total, 2)
            for target_row, averaged in zip((previous, row), averaged_values):
                fixed = _format_decimal(averaged)
                if target_row.values.get(field_code, "") != fixed:
                    target_row.values[field_code] = fixed
                    fix_count += 1
                target_row.fixed_fields.add(field_code)
                target_row.correction_kinds[field_code] = "weight_average_previous_line"
    return fix_count


def _apply_weight_average_by_case(rows: list[BookingBodyRow]) -> int:
    groups: dict[str, list[BookingBodyRow]] = {}
    for row in rows:
        case_number = row.values.get("case_number", "")
        if case_number and case_number.strip().upper() != "NA":
            groups.setdefault(case_number, []).append(row)

    fix_count = 0
    for group in groups.values():
        if len(group) <= 1:
            continue
        for field_code in ("FJZ", "G_Wt"):
            values = [_decimal(row.values.get(field_code, "")) for row in group]
            if any(value is None or value < 0 for value in values):
                continue
            needs_average = any(
                value == 0 and row.values.get("PO_No", "")[:4] in POSITIVE_WEIGHT_PO_PREFIXES
                for row, value in zip(group, values)
            )
            if not needs_average:
                continue
            total = sum((value for value in values if value is not None), Decimal("0"))
            if total <= 0:
                continue
            for row, averaged in zip(group, _split_decimal_total(total, len(group))):
                fixed = _format_decimal(averaged)
                if row.values.get(field_code, "") == fixed:
                    continue
                row.values[field_code] = fixed
                row.fixed_fields.add(field_code)
                row.correction_kinds[field_code] = "weight_average_by_case"
                fix_count += 1
    return fix_count


def _apply_static_fixes(rows: list[BookingBodyRow]) -> int:
    fix_count = 0
    for row in rows:
        ambiguous_na_case = _is_ambiguous_na_case_missing_line(row)
        if not ambiguous_na_case:
            fix_count += _apply_packaging_quantity_fallback(row)
        for body_field in BODY_FIELDS:
            if ambiguous_na_case and body_field.code in AMBIGUOUS_NA_CASE_MANUAL_FIELDS:
                continue
            if body_field.code == "madeDate" and _needs_excel_date_format_fix(row):
                row.fixed_fields.add(body_field.code)
                row.correction_options[body_field.code] = (row.values.get(body_field.code, ""),)
                row.correction_kinds[body_field.code] = "date_format"
                row.cell_formats[body_field.code] = "yyyy-mm-dd"
                fix_count += 1
                continue
            fixed = _auto_fix_value(body_field.code, row.values)
            if fixed is None:
                continue
            row.values[body_field.code] = fixed.value
            row.fixed_fields.add(body_field.code)
            if fixed.options:
                row.correction_options[body_field.code] = fixed.options
            if fixed.kind:
                row.correction_kinds[body_field.code] = fixed.kind
            fix_count += 1
    fix_count += _apply_previous_line_weight_average_for_na_case(rows)
    fix_count += _apply_weight_average_by_case(rows)
    return fix_count


def _reset_row_issues(rows: list[BookingBodyRow]) -> None:
    for row in rows:
        row.issue_fields.clear()
        row.issue_messages.clear()


def _snapshot_source_issues(rows: list[BookingBodyRow]) -> None:
    for row in rows:
        row.source_issue_fields = set(row.issue_fields)
        row.source_issue_messages = {key: list(value) for key, value in row.issue_messages.items()}


def _valid_production_date(value: str) -> bool:
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        or re.fullmatch(r"\d{6}", value)
        or re.fullmatch(r"\d{4}", value)
    )


def _validate_body_required(row: BookingBodyRow) -> list[BookingBodyIssue]:
    issues: list[BookingBodyIssue] = []
    for field_code in REQUIRED_FIELDS:
        if _is_missing(row.values.get(field_code, "")):
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 是必填字段。"))
    return issues


def _validate_body_row(row: BookingBodyRow, country_keys: set[str]) -> list[BookingBodyIssue]:
    values = row.values
    issues = _validate_body_required(row)

    quantity = values.get("Quantity", "")
    if quantity.upper() == "NAN":
        issues.append(_issue(row, "Quantity", "Quantity 不能为 NaN。"))
    elif quantity:
        number = _decimal(quantity)
        if number is None:
            fixed_number = _normalize_numeric_text(quantity)
            calculated = _parse_simple_numeric_expression(quantity)
            if fixed_number is not None:
                issues.append(
                    _issue(
                        row,
                        "Quantity",
                        "Quantity 包含单位或千分位符号，需要统一为数字。",
                        fixed_number,
                        correction_kind="normalize_number",
                    )
                )
            elif calculated is not None:
                issues.append(
                    _issue(
                        row,
                        "Quantity",
                        "Quantity 存在算式表达式，需要换算为数字。",
                        calculated,
                        correction_kind="calculate_number",
                    )
                )
            else:
                issues.append(_issue(row, "Quantity", "Quantity 必须是数字。"))
        elif number == 0:
            issues.append(_issue(row, "Quantity", "Quantity 不能为 0。"))

    for field_code in ALLOW_ZERO_NUMERIC_FIELDS:
        value = values.get(field_code, "")
        if not value:
            continue
        if value.upper() == "NA":
            if field_code == "Pallet":
                issues.append(
                    _issue(
                        row,
                        field_code,
                        f"{_field_label(field_code)} 为空或 NA 时建议补 0。",
                        "0",
                        correction_kind="default_zero",
                    )
                )
            else:
                issues.append(_issue(row, field_code, f"{_field_label(field_code)} 不能填 NA，请人工复核补填。"))
            continue
        number = _decimal(value)
        if number is None:
            fixed_number = _normalize_numeric_text(value)
            calculated = _parse_simple_numeric_expression(value)
            if fixed_number is not None:
                issues.append(
                    _issue(
                        row,
                        field_code,
                        f"{_field_label(field_code)} 包含单位或千分位符号，需要统一为数字。",
                        fixed_number,
                        correction_kind="normalize_number",
                    )
                )
            elif calculated is not None:
                issues.append(
                    _issue(
                        row,
                        field_code,
                        f"{_field_label(field_code)} 存在算式表达式，需要换算为数字。",
                        calculated,
                        correction_kind="calculate_number",
                    )
                )
            else:
                issues.append(_issue(row, field_code, f"{_field_label(field_code)} 必须是数字。"))
        elif field_code in INTEGER_FIELDS and number != number.to_integral_value():
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 不能带小数点。"))

    cbm = values.get("CBM", "")
    if cbm and not re.fullmatch(r"\d+(?:\.\d+)?", cbm):
        issues.append(_issue(row, "CBM", "CBM 应填写为数值格式，例如 1.5。"))

    per_box = values.get("per_box", "")
    min_package = values.get("min_package", "")
    per_box_number = _decimal(per_box) if per_box else None
    min_package_number = _decimal(min_package) if min_package else None
    parsed_per_box = _parse_per_box_expression(per_box) if per_box else None
    if per_box.upper() == "NA":
        issues.append(_issue(row, "per_box", "Standard quantity per box 不能填 NA。"))
    elif per_box:
        if per_box_number is None:
            if parsed_per_box is not None:
                issues.append(
                    _issue(
                        row,
                        "per_box",
                        "Standard quantity per box 存在算式表达式，需要换算为数字。",
                        parsed_per_box,
                        correction_kind="per_box_expression",
                    )
                )
            else:
                issues.append(_issue(row, "per_box", "Standard quantity per box 必须是数字。"))
        elif per_box_number == 0:
            issues.append(_issue(row, "per_box", "Standard quantity per box 不能为 0。"))
        elif min_package_number is not None:
            if per_box_number < min_package_number:
                issues.append(_issue(row, "per_box", "Standard quantity per box 必须大于等于 Min package。"))
            elif min_package_number != 0 and per_box_number % min_package_number != 0:
                issues.append(_issue(row, "per_box", "Standard quantity per box 必须是 Min package 的整数倍。"))

    brand = values.get("brand", "")
    if not brand.strip() or brand.strip().upper() == "NA":
        issues.append(_issue(row, "brand", "如果没有品牌，Brand 要填“无”。", "无"))

    invoice_no = values.get("Invoice_No", "")
    cleaned_invoice_no = re.sub(r"[^0-9A-Za-z]", "", invoice_no)
    if invoice_no and cleaned_invoice_no != invoice_no:
        issues.append(_issue(row, "Invoice_No", "Invoice No. 只能保留字母和数字。", cleaned_invoice_no, correction_kind="text_clean"))

    customer_part = values.get("Customer_Part_No", "")
    if customer_part and not re.fullmatch(r"[A-Za-z0-9]+", customer_part):
        cleaned_customer_part = _clean_customer_part_no(customer_part)
        if cleaned_customer_part:
            issues.append(
                _issue(
                    row,
                    "Customer_Part_No",
                    "PN / Customer Part No. 含空格、横杠或斜杠，建议去除。",
                    cleaned_customer_part,
                    correction_kind="text_clean",
                )
            )
        else:
            issues.append(_issue(row, "Customer_Part_No", "PN / Customer Part No. 只能包含英文字母和数字。"))

    production_date = values.get("madeDate", "")
    if production_date and not _valid_production_date(production_date):
        week_code = _extract_week_code_candidate(production_date)
        candidates = _extract_date_candidates(production_date)
        if week_code:
            issues.append(
                _issue(
                    row,
                    "madeDate",
                    "Production date 为周数加字母，系统只保留周数。",
                    week_code,
                    correction_options=(week_code,),
                    correction_kind="date_week_normalize",
                )
            )
        elif len(candidates) >= 2:
            issues.append(
                _issue(
                    row,
                    "madeDate",
                    "Production date 识别到多个日期候选，需要人工选择或手填确认。",
                    candidates[0],
                    correction_options=candidates,
                    correction_kind="date_choice",
                )
            )
        elif len(candidates) == 1:
            issues.append(
                _issue(
                    row,
                    "madeDate",
                    "Production date 格式需要统一为 YYYY-MM-DD。",
                    candidates[0],
                    correction_options=candidates,
                    correction_kind="date_normalize",
                )
            )
        else:
            issues.append(_issue(row, "madeDate", "Production date 需为 YYYY-MM-DD、6 位周别或 4 位周别。"))

    made_in = values.get("Made_In", "")
    made_in_suggestion = _suggest_made_in(made_in)
    if made_in_suggestion:
        issues.append(
            _issue(
                row,
                "Made_In",
                "Made In 为台湾时，需要按系统格式补充中国。",
                made_in_suggestion,
                correction_kind="made_in_tw",
            )
        )
    elif made_in and _country_lookup_key(made_in) not in country_keys:
        issues.append(_issue(row, "Made_In", "Made In 需填写合理国家简称或国家全称。"))

    po_no = values.get("PO_No", "")
    if po_no and _valid_po_base(po_no):
        issues.append(
            _issue(
                row,
                "PO_No",
                "PO No. 缺少 4 位项次，需要通过周期清单匹配补齐。",
                correction_kind="sil_fuca_delivery_incomplete_po",
            )
        )
    elif po_no and not _valid_po_no(po_no):
        po_suggestion = _suggest_po_no(po_no)
        if po_suggestion:
            issues.append(
                _issue(
                    row,
                    "PO_No",
                    "PO No. 格式可由算法补齐横杠，需人工确认。",
                    po_suggestion,
                    correction_kind="po_format_suggestion",
                )
            )
        else:
            issues.append(_issue(row, "PO_No", "PO No. 格式应类似 W33D-25040701-0001。"))

    packing = values.get("packing", "")
    if packing and not _valid_delivery_note(packing):
        issues.append(_issue(row, "packing", "Supplier delivery note number 格式不符合系统要求。"))

    tray_type = values.get("Tray_Type", "")
    if tray_type.replace(" ", "").upper() == "WOODENPALLET" and not values.get("IPPC", ""):
        issues.append(_issue(row, "IPPC", "Tray Type 为 WOODEN PALLET 时，IPPC 必填。"))

    po_prefix = po_no[:4]
    if po_prefix in POSITIVE_WEIGHT_PO_PREFIXES:
        if (_decimal(values.get("FJZ", "")) or Decimal("0")) <= 0:
            issues.append(_issue(row, "FJZ", "该 PO 前缀下净重不能小于等于 0。"))
        if (_decimal(values.get("G_Wt", "")) or Decimal("0")) <= 0:
            issues.append(_issue(row, "G_Wt", "该 PO 前缀下毛重不能小于等于 0。"))

    return issues


def _validate_body_cross_rows(rows: list[BookingBodyRow]) -> list[BookingBodyIssue]:
    issues: list[BookingBodyIssue] = []
    if not rows:
        return issues

    xp_rows = [row for row in rows if row.values.get("Customer_Part_No", "").startswith("XP")]
    if xp_rows and len(xp_rows) != len(rows):
        for row in rows:
            issues.append(_issue(row, "Customer_Part_No", "XP 开头 PN 不能和非 XP PN 混在同一个 booking。"))

    po_prefixes = {row.values.get("PO_No", "")[:4] for row in rows if row.values.get("PO_No", "")}
    if "E330" in po_prefixes and len(po_prefixes) >= 2 and not po_prefixes.issubset({"E330", "E33L"}):
        issues.append(_issue(None, "PO_No", "E330 通常只能单独预约，或只和 E33L 一起预约。"))

    total_cartons = sum(_decimal(row.values.get("Pkgs", "")) or Decimal("0") for row in rows)
    total_net = sum(_decimal(row.values.get("FJZ", "")) or Decimal("0") for row in rows)
    total_gross = sum(_decimal(row.values.get("G_Wt", "")) or Decimal("0") for row in rows)
    if total_cartons == 0:
        issues.append(_issue(None, "Pkgs", "总箱数不能为 0。"))
    if total_net > total_gross:
        issues.append(_issue(None, "FJZ", "总净重不能大于总毛重。"))
    if total_net == 0 or total_gross == 0:
        issues.append(_issue(None, "FJZ", "总净重或总毛重不能为 0。"))
    return issues


def _validate_body_rows(rows: list[BookingBodyRow], country_keys: set[str]) -> list[BookingBodyIssue]:
    issues: list[BookingBodyIssue] = []
    for row in rows:
        issues.extend(_validate_body_row(row, country_keys))
        if _needs_excel_date_format_fix(row):
            issues.append(
                _issue(
                    row,
                    "madeDate",
                    _date_format_issue_message(row),
                    row.values.get("madeDate", ""),
                    correction_options=(row.values.get("madeDate", ""),),
                    correction_kind="date_format",
                )
            )
    issues.extend(_validate_body_cross_rows(rows))
    return issues


def build_body_validation_preview(
    workbook_bytes: bytes,
    *,
    filename: str,
    apply_fixes: bool = False,
    enable_dynamic_checks: bool = False,
    sil_fuca_delivery_client: SilFucaDeliveryClient | None = None,
    query_date: date | None = None,
) -> BookingBodyValidationPreview:
    rows, purchaser = _load_rows(workbook_bytes)
    country_keys, country_warning = _country_keys()
    fix_count = 0
    dynamic_warnings: list[str] = []
    if apply_fixes:
        source_issues = _validate_body_rows(rows, country_keys)
        _snapshot_source_issues(rows)
        _reset_row_issues(rows)
        fix_count = _apply_static_fixes(rows)
        issues = _validate_body_rows(rows, country_keys)
        if enable_dynamic_checks:
            client = sil_fuca_delivery_client or SilFucaDeliveryClient()
            dynamic_fix_count, dynamic_issues, dynamic_source_issues, dynamic_warnings = (
                _apply_sil_fuca_delivery_checks(
                    rows,
                    client=client,
                    query_date=query_date or date.today(),
                    apply_fixes=True,
                )
            )
            fix_count += dynamic_fix_count
            issues.extend(dynamic_issues)
            source_issues.extend(dynamic_source_issues)
    else:
        source_issues = []
        issues = _validate_body_rows(rows, country_keys)
    warnings = [country_warning] if country_warning else []
    warnings.extend(dynamic_warnings)
    if not rows:
        warnings.append("未识别到主体明细行，请确认上传的是 booking form。")
    return BookingBodyValidationPreview(
        filename=filename,
        rows=rows,
        issues=issues,
        fields=BODY_FIELDS,
        applied_fixes=apply_fixes,
        fix_count=fix_count,
        purchaser=purchaser,
        warnings=warnings,
        source_issues=source_issues,
    )


ManualBodyValues = dict[tuple[int, str], str]


def _merged_cell_anchor(ws: Any, coordinate: str, value: str, *, split_merged: bool) -> Any | None:
    for merged_range in list(ws.merged_cells.ranges):
        if coordinate not in merged_range:
            continue
        min_col, min_row, _max_col, _max_row = merged_range.bounds
        if split_merged:
            ws.unmerge_cells(str(merged_range))
            return ws[coordinate]
        anchor = ws.cell(row=min_row, column=min_col)
        if anchor.coordinate == coordinate:
            return anchor
        anchor_text = _cell_text(anchor.value)
        if anchor_text and anchor_text != value:
            return None
        return anchor
    return ws[coordinate]


def _write_corrected_cell(ws: Any, coordinate: str, field_code: str, value: str, *, split_merged: bool = False) -> bool:
    cell = _merged_cell_anchor(ws, coordinate, value, split_merged=split_merged)
    if cell is None:
        return False
    if field_code == "madeDate":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            cell.value = datetime.strptime(value, "%Y-%m-%d").date()
            cell.number_format = "yyyy-mm-dd"
            return True
        cell.value = value
        cell.number_format = "@"
        return True
    cell.value = value
    return True


def _apply_manual_values(rows: list[BookingBodyRow], manual_values: ManualBodyValues | None) -> None:
    if not manual_values:
        return
    rows_by_excel_row = {row.excel_row: row for row in rows}
    for (excel_row, field_code), value in manual_values.items():
        row = rows_by_excel_row.get(excel_row)
        if row is None or field_code not in FIELDS_BY_CODE:
            continue
        original_value = row.values.get(field_code, "")
        row.values[field_code] = value
        row.fixed_fields.add(field_code)
        if original_value != value or not row.correction_kinds.get(field_code):
            row.correction_kinds[field_code] = "manual_confirmed"


def build_corrected_body_validation_workbook(
    workbook_bytes: bytes,
    *,
    filename: str,
    enable_dynamic_checks: bool = False,
    sil_fuca_delivery_client: SilFucaDeliveryClient | None = None,
    query_date: date | None = None,
    manual_values: ManualBodyValues | None = None,
) -> bytes:
    preview = build_body_validation_preview(
        workbook_bytes,
        filename=filename,
        apply_fixes=True,
        enable_dynamic_checks=enable_dynamic_checks,
        sil_fuca_delivery_client=sil_fuca_delivery_client,
        query_date=query_date,
    )
    _apply_manual_values(preview.rows, manual_values)
    wb = openpyxl.load_workbook(BytesIO(workbook_bytes))
    ws = wb[wb.sheetnames[0]]
    for row in preview.rows:
        for body_field in BODY_FIELDS:
            value = row.values.get(body_field.code, "")
            if body_field.code in row.fixed_fields or (
                body_field.code == "madeDate" and value and _valid_production_date(value)
            ):
                split_merged = row.correction_kind_for(body_field.code) in {
                    "manual_confirmed",
                    "weight_average_previous_line",
                }
                _write_corrected_cell(
                    ws,
                    f"{body_field.column_letter}{row.excel_row}",
                    body_field.code,
                    value,
                    split_merged=split_merged,
                )
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
