from __future__ import annotations

import re
import ast
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from app.modules.booking.sil_fuca_delivery import (
    SilFucaDeliveryClient,
    SilFucaDeliveryQuery,
    SilFucaDeliveryRecord,
)
from app.modules.booking.legacy_adapter import _country_lookup_key, load_country_abbr_lookup
from app.shared.lazy_imports import lazy_module


openpyxl = lazy_module("openpyxl")


@dataclass(frozen=True)
class BookingBodyField:
    code: str
    label: str
    column_letter: str


@dataclass
class BookingBodyIssue:
    row_number: int | None
    field_code: str
    field_label: str
    message: str
    suggestion: str = ""
    correction_options: tuple[str, ...] = ()
    correction_kind: str = ""


@dataclass(frozen=True)
class BookingBodyFix:
    value: str
    suggestion: str = ""
    kind: str = ""
    options: tuple[str, ...] = ()


@dataclass
class BookingBodyRow:
    excel_row: int
    values: dict[str, str]
    source_values: dict[str, str] = field(default_factory=dict)
    cell_formats: dict[str, str] = field(default_factory=dict)
    date_cells: set[str] = field(default_factory=set)
    issue_fields: set[str] = field(default_factory=set)
    fixed_fields: set[str] = field(default_factory=set)
    source_issue_fields: set[str] = field(default_factory=set)
    issue_messages: dict[str, list[str]] = field(default_factory=dict)
    source_issue_messages: dict[str, list[str]] = field(default_factory=dict)
    correction_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    correction_kinds: dict[str, str] = field(default_factory=dict)
    delivery_match_status: str = ""
    delivery_match_message: str = ""
    delivery_match_options: tuple[str, ...] = ()

    def issue_text(self, field_code: str) -> str:
        return "；".join(self.issue_messages.get(field_code, []))

    def source_issue_text(self, field_code: str) -> str:
        return "；".join(self.source_issue_messages.get(field_code, []))

    def correction_options_for(self, field_code: str) -> tuple[str, ...]:
        return self.correction_options.get(field_code, ())

    def correction_kind_for(self, field_code: str) -> str:
        return self.correction_kinds.get(field_code, "")


@dataclass
class BookingBodyValidationPreview:
    filename: str
    rows: list[BookingBodyRow]
    issues: list[BookingBodyIssue]
    fields: list[BookingBodyField]
    applied_fixes: bool = False
    fix_count: int = 0
    purchaser: str = ""
    warnings: list[str] = field(default_factory=list)
    source_issues: list[BookingBodyIssue] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def source_issue_count(self) -> int:
        return len(self.source_issues)

    @property
    def display_issues(self) -> list[BookingBodyIssue]:
        def issue_priority(issue: BookingBodyIssue) -> tuple[int, int, str]:
            if issue.correction_kind == "date_choice":
                priority = 0
            elif not issue.correction_kind:
                priority = 1
            else:
                priority = 2
            return (priority, issue.row_number or 999999, issue.field_code)

        issues = self.source_issues if self.applied_fixes and self.source_issues else self.issues
        return sorted(issues, key=issue_priority)

    @property
    def display_issue_count(self) -> int:
        return len(self.display_issues)

    @property
    def blocking_row_count(self) -> int:
        return len({issue.row_number for issue in self.issues if issue.row_number is not None})

    @property
    def display_blocking_row_count(self) -> int:
        return len({issue.row_number for issue in self.display_issues if issue.row_number is not None})


BODY_FIELDS = [
    BookingBodyField("Line", "Line", "A"),
    BookingBodyField("case_number", "Case number", "B"),
    BookingBodyField("PO_No", "PO No.", "C"),
    BookingBodyField("Customer_Part_No", "PN / Customer Part No.", "D"),
    BookingBodyField("Part_Description", "Part Description", "E"),
    BookingBodyField("Quantity", "Quantity", "F"),
    BookingBodyField("unit", "Unit", "G"),
    BookingBodyField("Pkgs", "Cartons", "H"),
    BookingBodyField("FJZ", "N.Wt", "I"),
    BookingBodyField("G_Wt", "G.Wt", "J"),
    BookingBodyField("CBM", "CBM", "K"),
    BookingBodyField("Pallet", "Pallet", "L"),
    BookingBodyField("Invoice_No", "Invoice No.", "M"),
    BookingBodyField("madeDate", "Production date", "N"),
    BookingBodyField("Invoice_Date", "Invoice Date", "O"),
    BookingBodyField("Made_In", "Made In", "P"),
    BookingBodyField("Batch_No", "Batch No.", "Q"),
    BookingBodyField("ASN", "Delivery Schedule Number", "R"),
    BookingBodyField("gyskbh", "Supplier card number", "S"),
    BookingBodyField("packing", "Supplier delivery note number", "T"),
    BookingBodyField("Tray_Type", "Tray Type", "U"),
    BookingBodyField("brand", "Brand", "V"),
    BookingBodyField("LEDBinCode", "LEDBinCode", "W"),
    BookingBodyField("min_package", "Min package", "X"),
    BookingBodyField("per_box", "Standard quantity per box", "Y"),
    BookingBodyField("IPPC", "IPPC", "Z"),
    BookingBodyField("Remark", "Remark", "AA"),
]

FIELDS_BY_CODE = {field.code: field for field in BODY_FIELDS}
REQUIRED_FIELDS = {
    "case_number",
    "PO_No",
    "Customer_Part_No",
    "Part_Description",
    "Quantity",
    "unit",
    "Pkgs",
    "FJZ",
    "G_Wt",
    "CBM",
    "Pallet",
    "Invoice_No",
    "madeDate",
    "Made_In",
    "Batch_No",
    "packing",
    "brand",
    "LEDBinCode",
    "min_package",
    "per_box",
}
ALLOW_ZERO_NUMERIC_FIELDS = {"Pkgs", "FJZ", "G_Wt", "CBM", "Pallet", "min_package"}
INTEGER_FIELDS = {"Pkgs", "Pallet"}
POSITIVE_WEIGHT_PO_PREFIXES = {
    "W33D",
    "V33D",
    "K33U",
    "V33U",
    "C33C",
    "E33J",
    "V33J",
    "E330",
    "V33C",
    "T33U",
    "M33U",
    "C33E",
    "M33E",
    "E33L",
}
FALLBACK_COUNTRY_KEYS = {
    "CN",
    "CHINA",
    "HK",
    "HONGKONG",
    "US",
    "USA",
    "UNITEDSTATES",
    "JP",
    "JAPAN",
    "KR",
    "KOREA",
    "REPUBLICOFKOREA",
    "MY",
    "MALAYSIA",
    "PH",
    "PHILIPPINES",
    "SG",
    "SINGAPORE",
    "TH",
    "THAILAND",
    "TW",
    "TAIWAN",
    "VN",
    "VIETNAM",
}
SPECIAL_COUNTRY_KEYS = {"TW,CN", "TAIWAN,CHINA"}
NUMERIC_FIELD_CODES = {"Quantity", "Pkgs", "FJZ", "G_Wt", "CBM", "Pallet", "min_package", "per_box"}
UNIT_NORMALIZABLE_NUMERIC_FIELDS = NUMERIC_FIELD_CODES - {"per_box"}
MANUAL_REVIEW_NA_FIELDS = {"Pkgs", "FJZ", "G_Wt", "CBM", "min_package"}
WEIGHT_AVERAGE_SCALE = Decimal("0.001")
SIL_FUCA_DYNAMIC_PO_PREFIXES = {"T33U", "K33U"}


@dataclass
class _SilFucaDeliveryGroup:
    po: str
    po_base: str
    is_complete_po: bool
    pn: str
    quantity: Decimal
    rows: list[BookingBodyRow] = field(default_factory=list)


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


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{value:.0f}"
    return format(value, "f").rstrip("0").rstrip(".")


def _is_no_value(value: str, *, include_zero: bool = False) -> bool:
    normalized = (value or "").strip().upper()
    return not normalized or normalized == "NA" or (include_zero and normalized == "0")


def _normalize_numeric_text(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw or raw.upper() in {"NA", "NAN"}:
        return None
    normalized = re.sub(r"\s+", "", raw.upper().replace(",", ""))
    match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)(箱|件|PCS?|PICES?|CARTONS?|CTNS?|PALLETS?|PLTS?|KGS?|CBM)?",
        normalized,
    )
    if not match:
        return None
    return _format_decimal(Decimal(match.group(1)))


def _decimal_from_number_node(node: ast.AST) -> Decimal | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _decimal_from_number_node(node.operand)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _decimal_from_number_node(node.left)
        right = _decimal_from_number_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            return None
        return left / right
    return None


def _parse_simple_numeric_expression(value: str) -> str | None:
    expression = re.sub(r"\s+", "", (value or "").replace(",", "").replace("×", "*"))
    if not expression or not any(operator in expression for operator in "+-*/()"):
        return None
    if not re.fullmatch(r"[0-9+\-*/().]+", expression):
        return None
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    result = _decimal_from_number_node(parsed.body)
    if result is None or result <= 0:
        return None
    return _format_decimal(result)


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


def _parse_per_box_expression(value: str) -> str | None:
    raw = re.sub(r"\s+", "", value.upper().replace(",", ""))
    has_expression_signal = any(part in raw for part in ("K", "CARTON", "CTN", "+", "*"))
    if not raw or not has_expression_signal:
        return None

    expression = raw.replace("×", "*")
    expression = re.sub(r"CARTONS?|CTNS?", "", expression)
    if not re.fullmatch(r"[0-9K+*.]+", expression):
        return None

    total = Decimal("0")
    for term in expression.split("+"):
        if not term:
            return None
        product = Decimal("1")
        for factor in term.split("*"):
            factor_match = re.fullmatch(r"(\d+(?:\.\d+)?)(K?)", factor)
            if not factor_match:
                return None
            number = Decimal(factor_match.group(1))
            if factor_match.group(2):
                number *= Decimal("1000")
            product *= number
        total += product

    if total <= 0:
        return None
    return _format_decimal(total)


def _field_label(field_code: str) -> str:
    field = FIELDS_BY_CODE.get(field_code)
    return field.label if field else field_code


def _issue(
    row: BookingBodyRow | None,
    field_code: str,
    message: str,
    suggestion: str = "",
    *,
    correction_options: tuple[str, ...] = (),
    correction_kind: str = "",
) -> BookingBodyIssue:
    if row is not None and field_code:
        row.issue_fields.add(field_code)
        row.issue_messages.setdefault(field_code, []).append(message)
    return BookingBodyIssue(
        row_number=row.excel_row if row is not None else None,
        field_code=field_code,
        field_label=_field_label(field_code),
        message=message,
        suggestion=suggestion,
        correction_options=correction_options,
        correction_kind=correction_kind,
    )


def _source_issue(
    row: BookingBodyRow,
    field_code: str,
    message: str,
    suggestion: str = "",
    *,
    correction_options: tuple[str, ...] = (),
    correction_kind: str = "",
) -> BookingBodyIssue:
    row.source_issue_fields.add(field_code)
    row.source_issue_messages.setdefault(field_code, []).append(message)
    return BookingBodyIssue(
        row_number=row.excel_row,
        field_code=field_code,
        field_label=_field_label(field_code),
        message=message,
        suggestion=suggestion,
        correction_options=correction_options,
        correction_kind=correction_kind,
    )


def _po_base(value: str) -> str:
    parts = (value or "").upper().split("-")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}-{parts[1]}"


def _valid_po_base(value: str) -> bool:
    parts = (value or "").upper().split("-")
    return len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 8 and parts[1].isdigit()


def _sil_fuca_delivery_groups(rows: list[BookingBodyRow]) -> list[_SilFucaDeliveryGroup]:
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
    return records[0] if records else None


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
            try:
                response = client.get_delivery_list_new(query)
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
                response = None

            if response is not None:
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
        for field in BODY_FIELDS:
            cell = ws[f"{field.column_letter}{excel_row}"]
            values[field.code] = _normalize_import_value(field.code, cell.value)
            cell_formats[field.code] = cell.number_format or ""
            if isinstance(cell.value, (datetime, date)):
                date_cells.add(field.code)
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
        parsed_expression = _parse_per_box_expression(value)
        if parsed_expression is not None and parsed_expression != value:
            return BookingBodyFix(parsed_expression, f"表达式换算为 {parsed_expression}", "per_box_expression")
        calculated = _parse_simple_numeric_expression(value)
        if calculated is not None and calculated != value:
            return BookingBodyFix(calculated, f"算式计算为 {calculated}", "calculate_number")
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


def _apply_weight_average_by_case(rows: list[BookingBodyRow]) -> int:
    groups: dict[str, list[BookingBodyRow]] = {}
    for row in rows:
        case_number = row.values.get("case_number", "")
        if case_number:
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
        fix_count += _apply_packaging_quantity_fallback(row)
        for field in BODY_FIELDS:
            if field.code == "madeDate" and _needs_excel_date_format_fix(row):
                row.fixed_fields.add(field.code)
                row.correction_options[field.code] = (row.values.get(field.code, ""),)
                row.correction_kinds[field.code] = "date_format"
                row.cell_formats[field.code] = "yyyy-mm-dd"
                fix_count += 1
                continue
            fixed = _auto_fix_value(field.code, row.values)
            if fixed is None:
                continue
            row.values[field.code] = fixed.value
            row.fixed_fields.add(field.code)
            if fixed.options:
                row.correction_options[field.code] = fixed.options
            if fixed.kind:
                row.correction_kinds[field.code] = fixed.kind
            fix_count += 1
    fix_count += _apply_weight_average_by_case(rows)
    return fix_count


def _validate_required(row: BookingBodyRow) -> list[BookingBodyIssue]:
    issues: list[BookingBodyIssue] = []
    for field_code in REQUIRED_FIELDS:
        if _is_missing(row.values.get(field_code, "")):
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 是必填字段。"))
    return issues


def _validate_row(row: BookingBodyRow, country_keys: set[str]) -> list[BookingBodyIssue]:
    values = row.values
    issues = _validate_required(row)

    quantity = values.get("Quantity", "")
    if quantity.upper() == "NAN":
        issues.append(_issue(row, "Quantity", "Quantity 不能为 NaN。"))
    elif quantity:
        number = _decimal(quantity)
        if number is None:
            issues.append(_issue(row, "Quantity", "Quantity 必须是数字。"))
        elif number == 0:
            issues.append(_issue(row, "Quantity", "Quantity 不能为 0。"))

    for field_code in ALLOW_ZERO_NUMERIC_FIELDS:
        value = values.get(field_code, "")
        if not value:
            continue
        if value.upper() == "NA":
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 不能填 NA；没有请填 0。", "0"))
            continue
        number = _decimal(value)
        if number is None:
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 必须是数字。"))
        elif field_code in INTEGER_FIELDS and number != number.to_integral_value():
            issues.append(_issue(row, field_code, f"{_field_label(field_code)} 不能带小数点。"))

    cbm = values.get("CBM", "")
    if cbm and not re.fullmatch(r"\d+(?:\.\d+)?", cbm):
        issues.append(_issue(row, "CBM", "CBM 应填写为数值形式，例如 1.5。"))

    per_box = values.get("per_box", "")
    min_package = values.get("min_package", "")
    per_box_number = _decimal(per_box) if per_box else None
    min_package_number = _decimal(min_package) if min_package else None
    if per_box.upper() == "NA":
        issues.append(_issue(row, "per_box", "Standard quantity per box 不能填 NA。"))
    elif per_box:
        if per_box_number is None:
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
        issues.append(_issue(row, "Invoice_No", "Invoice No. 只能保留字母和数字。", cleaned_invoice_no))

    customer_part = values.get("Customer_Part_No", "")
    if customer_part and not re.fullmatch(r"[A-Za-z0-9]+", customer_part):
        issues.append(_issue(row, "Customer_Part_No", "PN / Customer Part No. 只能包含英文字母和数字。"))

    production_date = values.get("madeDate", "")
    if production_date and not (
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", production_date)
        or re.fullmatch(r"\d{6}", production_date)
        or re.fullmatch(r"\d{4}", production_date)
    ):
        issues.append(_issue(row, "madeDate", "Production date 需为 YYYY-MM-DD、6 位周别或 4 位周别。"))

    if production_date and _valid_production_date(production_date) and _needs_excel_date_format_fix(row):
        issues.append(
            _issue(
                row,
                "madeDate",
                "Production date 在 Excel 中的显示格式不是 YYYY-MM-DD，需要统一为 yyyy-mm-dd。",
                production_date,
                correction_options=(production_date,),
                correction_kind="date_format",
            )
        )

    made_in = values.get("Made_In", "")
    if made_in and _country_lookup_key(made_in) not in country_keys:
        issues.append(_issue(row, "Made_In", "Made In 需填写合理国家简称或国家全称。"))

    po_no = values.get("PO_No", "")
    if po_no and not _valid_po_no(po_no):
        issues.append(_issue(row, "PO_No", "PO No. 格式应类似 W33D-25040701-0001。"))

    packing = values.get("packing", "")
    if packing and not _valid_delivery_note(packing):
        issues.append(_issue(row, "packing", "Supplier delivery note number 格式不符合系统要求。"))

    tray_type = values.get("Tray_Type", "")
    if tray_type.replace(" ", "") == "WOODENPALLET" and not values.get("IPPC", ""):
        issues.append(_issue(row, "IPPC", "Tray Type 为 WOODEN PALLET 时，IPPC 必填。"))

    po_prefix = po_no[:4]
    if po_prefix in POSITIVE_WEIGHT_PO_PREFIXES:
        if (_decimal(values.get("FJZ", "")) or Decimal("0")) <= 0:
            issues.append(_issue(row, "FJZ", "该 PO 前缀下净重不能小于等于 0。"))
        if (_decimal(values.get("G_Wt", "")) or Decimal("0")) <= 0:
            issues.append(_issue(row, "G_Wt", "该 PO 前缀下毛重不能小于等于 0。"))

    return issues


def _validate_cross_row(rows: list[BookingBodyRow]) -> list[BookingBodyIssue]:
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
        candidates = _extract_date_candidates(production_date)
        if len(candidates) >= 2:
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


def _write_corrected_cell(cell: Any, field_code: str, value: str) -> None:
    if field_code == "madeDate":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            cell.value = datetime.strptime(value, "%Y-%m-%d").date()
            cell.number_format = "yyyy-mm-dd"
            return
        cell.value = value
        cell.number_format = "@"
        return
    cell.value = value


def build_corrected_body_validation_workbook(
    workbook_bytes: bytes,
    *,
    filename: str,
    enable_dynamic_checks: bool = False,
    sil_fuca_delivery_client: SilFucaDeliveryClient | None = None,
    query_date: date | None = None,
) -> bytes:
    preview = build_body_validation_preview(
        workbook_bytes,
        filename=filename,
        apply_fixes=True,
        enable_dynamic_checks=enable_dynamic_checks,
        sil_fuca_delivery_client=sil_fuca_delivery_client,
        query_date=query_date,
    )
    wb = openpyxl.load_workbook(BytesIO(workbook_bytes))
    ws = wb[wb.sheetnames[0]]
    for row in preview.rows:
        for field in BODY_FIELDS:
            value = row.values.get(field.code, "")
            if field.code in row.fixed_fields or (field.code == "madeDate" and value and _valid_production_date(value)):
                _write_corrected_cell(ws[f"{field.column_letter}{row.excel_row}"], field.code, value)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
