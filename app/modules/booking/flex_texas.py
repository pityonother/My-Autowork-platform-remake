from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


SUPPLIER_NAME = "FLEX-TEXAS"
SYSTEM_EXPORT_PDF_NAMES = {"rh2604405 260611.pdf"}
PART_NUMBER_PREFIXES = (
    "CCIJ-",
    "CCIH-",
    "DQTH-",
    "DQTJ-",
    "EPHH-",
    "SNBH-",
    "RTXH-",
    "RHLJ-",
    "GECH-",
    "GECDH-",
    "RHLH-",
    "HITH-",
    "AUCH-",
    "AUC1J-",
    "AUC1H-",
    "XPGDH",
    "HGJDH",
    "LNKH-",
    "LNKDH-",
    "FPS-",
)

FLEX_TEXAS_BOOKING_COLUMNS = [
    "PO No. *",
    "PO Line",
    "Invoice No.*",
    "Invoice Date",
    "Customer Part No. *",
    "Part Description *",
    "Made In *",
    "Cartons*",
    "Pallet*",
    "G.Wt*",
    "CBM * ",
    "Quantity *",
    "Price*",
    "Currency *",
    "Total Amount *",
    "Tray Type",
]

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass
class TexasWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    nx0: float
    ny0: float
    nx1: float
    ny1: float

    @property
    def nx(self) -> float:
        return (self.nx0 + self.nx1) / 2

    @property
    def ny(self) -> float:
        return (self.ny0 + self.ny1) / 2


@dataclass
class TexasPdfPage:
    page_index: int
    page_type: str
    source_file: str
    width: float
    height: float
    text: str
    words: list[TexasWord]


@dataclass
class TexasEmailInfo:
    hbl_no: str = ""
    mbl_no: str = ""
    cartons: int | None = None
    gross_weight: float | None = None
    delivery_to_hub_date: str = ""
    eta_raw: str = ""
    subject_hbl_no: str = ""


@dataclass
class TexasAwbInfo:
    hbl_no: str = ""
    mbl_no: str = ""
    carrier_code: str = ""
    dimensions: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class TexasInvoiceInfo:
    invoice_no: str
    invoice_date: str
    ti_waybill_no: str
    customer_part_no: str = ""
    made_in: str = ""
    quantity: int | float | None = None
    price: int | float | None = None
    currency: str = "USD"
    total_amount: int | float | None = None
    customer_po_raw: str = ""
    shipper: str = ""
    consignee: str = ""
    page_index: int = 0


@dataclass
class TexasContentRow:
    waybill_no: str
    box_number: str = ""
    box_size: str = ""
    gross_weight: int | float | None = None
    po_no: str = ""
    quantity: int | float | None = None
    customer_part_no: str = ""
    cartons: int = 1
    cbm: float = 0.0
    page_index: int = 0


@dataclass
class TexasBookingLine:
    invoice_no: str
    invoice_date: str
    ti_waybill_no: str
    po_no: str
    invoice_customer_po_raw: str
    customer_part_no: str
    made_in: str
    cartons: int
    pallet: int
    gross_weight: int | float
    box_size: str
    cbm: float
    quantity: int | float
    price: int | float
    currency: str
    total_amount: int | float
    part_description: str = "MATERIAL"
    tray_type: str = "0"


@dataclass
class TexasValidationSource:
    label: str
    value: str


@dataclass
class TexasValidationItem:
    field: str
    final_value: str
    status: str
    status_label: str
    message: str
    sources: list[TexasValidationSource] = field(default_factory=list)
    row_no: int | None = None


@dataclass
class TexasValidationSection:
    title: str
    items: list[TexasValidationItem]

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.items if item.status == "ok")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.items if item.status == "warning")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.status == "error")

    @property
    def status(self) -> str:
        if self.error_count:
            return "error"
        if self.warning_count:
            return "warning"
        return "ok"


@dataclass
class TexasExtraction:
    hbl_no: str
    mbl_no: str
    delivery_to_hub_date: str
    transport_company: str
    delivery_party: str
    shipper: str
    source_pdf: str
    pdf_page_count: int
    lines: list[TexasBookingLine]
    warnings: list[str] = field(default_factory=list)
    validation_sections: list[TexasValidationSection] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int | float]:
        return {
            "cartons": _sum_numbers(line.cartons for line in self.lines),
            "pallet": _sum_numbers(line.pallet for line in self.lines),
            "grossWeight": _sum_numbers(line.gross_weight for line in self.lines),
            "cbm": round(_sum_numbers(line.cbm for line in self.lines), 2),
            "quantity": _sum_numbers(line.quantity for line in self.lines),
            "totalAmount": _sum_numbers(line.total_amount for line in self.lines),
        }


def is_system_export_pdf(path_or_name: str | Path) -> bool:
    return Path(path_or_name).name.lower() in SYSTEM_EXPORT_PDF_NAMES


def normalize_mawb(value: Any) -> str:
    return re.sub(r"[\s-]+", "", str(value or "")).upper()


def normalize_po_no(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"-\d+$", "", text)


def _as_decimal(value: Any) -> Decimal:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _number(value: Any) -> int | float:
    number = _as_decimal(value)
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _sum_numbers(values: Any) -> int | float:
    total = sum(_as_decimal(value) for value in values)
    if total == total.to_integral_value():
        return int(total)
    return float(total)


def _parse_email_year(email_date: str | None) -> int:
    if not email_date:
        return date.today().year
    try:
        return parsedate_to_datetime(email_date).year
    except (TypeError, ValueError, IndexError):
        return date.today().year


def parse_texas_date(value: str, default_year: int | None = None) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?", text)
    if not match:
        return ""
    day = int(match.group(1))
    month = MONTHS.get(match.group(2).lower()[:4]) or MONTHS.get(match.group(2).lower()[:3])
    if not month:
        return ""
    year = int(match.group(3) or default_year or date.today().year)
    return f"{year:04d}/{month:02d}/{day:02d}"


def _message_text(message: Message) -> str:
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    text = body.get_content()
    if body.get_content_type() == "text/html":
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def parse_texas_email_body(text: str, email_date: str | None = None, subject: str = "") -> TexasEmailInfo:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    headers = ["HAWB", "File", "MAWB", "Client", "PKG", "Weight", "ETA"]
    values: dict[str, str] = {}
    for index in range(0, max(0, len(lines) - len(headers) * 2 + 1)):
        if [item.upper() for item in lines[index : index + len(headers)]] == [item.upper() for item in headers]:
            raw_values = lines[index + len(headers) : index + len(headers) * 2]
            values = dict(zip(headers, raw_values, strict=False))
            break

    year = _parse_email_year(email_date)
    subject_match = re.search(r"\bHB#\s*(\d{10})\b", subject or "", flags=re.IGNORECASE)
    pkg_match = re.search(r"\d+", values.get("PKG", ""))
    weight_match = re.search(r"\d+(?:\.\d+)?", values.get("Weight", ""))

    return TexasEmailInfo(
        hbl_no=values.get("HAWB", "").strip(),
        mbl_no=normalize_mawb(values.get("MAWB", "")),
        cartons=int(pkg_match.group(0)) if pkg_match else None,
        gross_weight=float(weight_match.group(0)) if weight_match else None,
        delivery_to_hub_date=parse_texas_date(values.get("ETA", ""), default_year=year),
        eta_raw=values.get("ETA", ""),
        subject_hbl_no=subject_match.group(1) if subject_match else "",
    )


def _load_pdf_pages(pdf_bytes: bytes, source_file: str) -> list[TexasPdfPage]:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[TexasPdfPage] = []
    for page_index, page in enumerate(doc):
        width = float(page.rect.width)
        height = float(page.rect.height)
        text = page.get_text("text")
        words = [
            TexasWord(
                text=str(raw[4]).strip(),
                x0=float(raw[0]),
                y0=float(raw[1]),
                x1=float(raw[2]),
                y1=float(raw[3]),
                nx0=float(raw[0]) / width,
                ny0=float(raw[1]) / height,
                nx1=float(raw[2]) / width,
                ny1=float(raw[3]) / height,
            )
            for raw in page.get_text("words")
            if str(raw[4]).strip()
        ]
        page_type = _classify_page_text(text)
        pages.append(
            TexasPdfPage(
                page_index=page_index,
                page_type=page_type,
                source_file=source_file,
                width=width,
                height=height,
                text=text,
                words=words,
            )
        )
    return pages


def _classify_page_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").upper()
    if "AIR WAYBILL" in normalized and "SHIPPER'S NAME AND ADDRESS" in normalized:
        return "air_waybill"
    if "COMMERCIAL INVOICE ( CUSTOMER F8 )" in normalized and "PAGE 1 OF 2" in normalized:
        return "commercial_invoice_item"
    if "COMMERCIAL INVOICE ( CUSTOMER F8 )" in normalized and "PAGE 2 OF 2" in normalized:
        return "commercial_invoice_comments"
    if "CONTENT LIST" in normalized and "BOX NUMBER" in normalized:
        return "content_list"
    return "unknown"


def classify_texas_pdf_pages(pdf_bytes: bytes, source_file: str = "") -> list[TexasPdfPage]:
    return _load_pdf_pages(pdf_bytes, source_file)


def _line_groups(words: list[TexasWord], ny_min: float = 0.0, ny_max: float = 1.0, tolerance: float = 0.006) -> list[list[TexasWord]]:
    selected = sorted((word for word in words if ny_min <= word.ny <= ny_max), key=lambda item: (item.ny, item.nx0))
    groups: list[list[TexasWord]] = []
    group_y: list[float] = []
    for word in selected:
        if not groups or abs(group_y[-1] - word.ny) > tolerance:
            groups.append([word])
            group_y.append(word.ny)
            continue
        groups[-1].append(word)
        group_y[-1] = (group_y[-1] + word.ny) / 2
    return groups


def _line_text(words: list[TexasWord]) -> str:
    return " ".join(word.text for word in sorted(words, key=lambda item: item.nx0)).strip()


def _words_in_window(
    words: list[TexasWord],
    nx_min: float,
    nx_max: float,
    ny_min: float,
    ny_max: float,
) -> list[TexasWord]:
    return [
        word
        for word in words
        if nx_min <= word.nx <= nx_max and ny_min <= word.ny <= ny_max
    ]


def _window_text(
    words: list[TexasWord],
    nx_min: float,
    nx_max: float,
    ny_min: float,
    ny_max: float,
) -> str:
    return _line_text(_words_in_window(words, nx_min, nx_max, ny_min, ny_max))


def _line_with_label_value(words: list[TexasWord], label: str, value_pattern: str) -> str:
    for line in _line_groups(words):
        text = _line_text(line)
        upper_text = text.upper()
        label_index = upper_text.find(label.upper())
        if label_index < 0:
            continue
        match = re.search(value_pattern, text[label_index:])
        if match:
            return match.group(1)
    return ""


def _first_data_line_after_label(
    page: TexasPdfPage,
    label_text: str,
    nx_min: float,
    nx_max: float,
    ny_min: float,
    ny_max: float,
) -> str:
    label_seen = False
    for line in _line_groups(page.words, ny_min, ny_max):
        column_words = [word for word in line if nx_min <= word.nx <= nx_max]
        if not column_words:
            continue
        text = _line_text(column_words)
        if not label_seen and label_text.upper() in text.upper():
            label_seen = True
            continue
        if label_seen and text:
            return text
    return ""


def parse_texas_awb_layout(page: TexasPdfPage) -> TexasAwbInfo:
    top_digits = [
        word.text
        for word in page.words
        if word.ny <= 0.05 and re.fullmatch(r"\d{10}", word.text)
    ]
    hbl_no = ""
    if top_digits:
        hbl_no = Counter(top_digits).most_common(1)[0][0]

    mbl_no = ""
    for word in page.words:
        if 0.68 <= word.nx <= 0.95 and 0.02 <= word.ny <= 0.07 and re.fullmatch(r"\d{3}-\d{8}", word.text):
            mbl_no = normalize_mawb(word.text)
            break

    dimensions = ""
    for line in _line_groups(page.words, 0.50, 0.75):
        text = _line_text(line)
        if "DIMS" in text.upper() and "CMS" in text.upper():
            match = re.search(r"DIMS\s+\(CMS\):\s*(.+)$", text, flags=re.IGNORECASE)
            if match:
                dimensions = match.group(1).strip()
                break

    page_text = page.text.upper()
    carrier_code = "EI" if "EI REF" in page_text or "EXPEDITORS" in page_text else ""
    return TexasAwbInfo(hbl_no=hbl_no, mbl_no=mbl_no, carrier_code=carrier_code, dimensions=dimensions)


def parse_texas_commercial_invoice_layout(page: TexasPdfPage) -> list[TexasInvoiceInfo]:
    text = page.text
    invoice_no = _regex_value(text, r"Invoice\s+number\s+(\d+)")
    invoice_date = parse_texas_date(_regex_value(text, r"Invoice\s+date\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"))
    ti_waybill_no = _regex_value(text, r"TI\s+waybill\s+number\s+(\d+)")
    currency = _regex_value(text, r"(?:Unit|Subtotal)\s+value\s*\((\w{3})\)") or "USD"
    customer_po_raw = _regex_value(text, r"Customer\s+P\.O:\s*([A-Z0-9-]+)")
    shipper = _first_data_line_after_label(page, "Ship from", 0.04, 0.34, 0.15, 0.30)
    consignee = _first_data_line_after_label(page, "Ship to", 0.35, 0.66, 0.15, 0.30)

    rows: list[TexasInvoiceInfo] = []
    item_words = [
        word
        for word in page.words
        if 0.60 <= word.ny <= 0.70 and 0.03 <= word.nx <= 0.09 and re.fullmatch(r"\d+", word.text)
    ]
    for item_word in item_words:
        row_y = item_word.ny
        quantity = _number(_window_text(page.words, 0.66, 0.75, row_y - 0.01, row_y + 0.01))
        price = _number(_window_text(page.words, 0.75, 0.86, row_y - 0.01, row_y + 0.01))
        total_amount = _number(_window_text(page.words, 0.88, 0.98, row_y - 0.01, row_y + 0.01))
        hts_column_words = _words_in_window(page.words, 0.26, 0.48, row_y - 0.005, row_y + 0.05)
        made_in = ""
        customer_part_no = ""
        for word in sorted(hts_column_words, key=lambda item: (item.ny, item.nx0)):
            if not made_in:
                made_match = re.fullmatch(r"([A-Z]{2}):?", word.text)
                if made_match:
                    made_in = made_match.group(1)
                    continue
            if "-" in word.text and re.search(r"[A-Za-z]", word.text):
                customer_part_no = word.text
        rows.append(
            TexasInvoiceInfo(
                invoice_no=invoice_no,
                invoice_date=invoice_date,
                ti_waybill_no=ti_waybill_no,
                customer_part_no=customer_part_no,
                made_in=made_in,
                quantity=quantity,
                price=price,
                currency=currency,
                total_amount=total_amount,
                customer_po_raw=customer_po_raw,
                shipper=shipper,
                consignee=consignee,
                page_index=page.page_index,
            )
        )
    return rows


def _regex_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "", flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_texas_content_list_layout(page: TexasPdfPage) -> list[TexasContentRow]:
    waybill_no = _line_with_label_value(page.words, "WAYB", r"\b(\d{9})\b")
    total_cartons_text = _line_with_label_value(page.words, "TOTAL CARTONS", r"\b(\d{1,4})\b")
    total_cartons = int(total_cartons_text) if total_cartons_text else 0
    rows: list[TexasContentRow] = []
    box_words = [
        word
        for word in page.words
        if 0.35 <= word.ny <= 0.85 and 0.06 <= word.nx <= 0.17 and re.fullmatch(r"\d{8}", word.text)
    ]
    for box_word in box_words:
        row_y = box_word.ny
        box_size = _window_text(page.words, 0.18, 0.36, row_y - 0.01, row_y + 0.01)
        gross_weight = _number(_window_text(page.words, 0.84, 0.96, row_y - 0.01, row_y + 0.01))
        detail_y = row_y + 0.028
        part_y = row_y + 0.042
        po_no = _window_text(page.words, 0.18, 0.34, detail_y - 0.01, detail_y + 0.01)
        quantity = _number(_window_text(page.words, 0.64, 0.76, detail_y - 0.01, detail_y + 0.01))
        customer_part_no = _window_text(page.words, 0.18, 0.37, part_y - 0.01, part_y + 0.01)
        cartons = total_cartons or 1
        rows.append(
            TexasContentRow(
                waybill_no=waybill_no,
                box_number=box_word.text,
                box_size=box_size,
                gross_weight=gross_weight,
                po_no=po_no,
                quantity=quantity,
                customer_part_no=customer_part_no,
                cartons=cartons,
                cbm=calculate_texas_cbm(box_size, cartons=cartons),
                page_index=page.page_index,
            )
        )
    return rows


def calculate_texas_cbm(box_size: str, cartons: int = 1) -> float:
    numbers = [Decimal(item) for item in re.findall(r"\d+(?:\.\d+)?", box_size or "")]
    if len(numbers) < 3:
        return 0.0
    raw = numbers[0] * numbers[1] * numbers[2] / Decimal("1000000000") * Decimal(str(cartons or 1))
    display = raw.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if display <= 0 and raw > 0:
        display = Decimal("0.01")
    return float(display)


def normalize_airwaybill_no(value: Any) -> str:
    return re.sub(r"[\s-]+", "", str(value or "")).upper()


def normalize_hawb_no(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def is_valid_mawb_no(value: Any) -> bool:
    digits = normalize_airwaybill_no(value)
    if not re.fullmatch(r"\d{11}", digits):
        return False
    serial = digits[3:]
    return int(serial[:7]) % 7 == int(serial[-1])


def is_valid_hawb_no(value: Any) -> bool:
    return re.fullmatch(r"\d{10}", normalize_hawb_no(value)) is not None


def is_valid_invoice_no(value: Any) -> bool:
    return re.fullmatch(r"\d{10}", str(value or "").strip()) is not None


def is_valid_po_no(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return re.fullmatch(r"NPI\d{6}|J\d{8}", text) is not None


def is_valid_part_no(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return bool(text) and any(text.startswith(prefix) for prefix in PART_NUMBER_PREFIXES)


def _money(value: Any) -> Decimal:
    return _as_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validation_status(status: str) -> str:
    return {"ok": "通过", "warning": "警示", "error": "错误"}.get(status, status)


def _validation_item(
    *,
    field_name: str,
    final_value: Any,
    status: str,
    message: str,
    sources: list[tuple[str, Any]],
    row_no: int | None = None,
) -> TexasValidationItem:
    return TexasValidationItem(
        field=field_name,
        final_value=str(final_value or ""),
        status=status,
        status_label=_validation_status(status),
        message=message,
        sources=[
            TexasValidationSource(label=label, value=str(value or ""))
            for label, value in sources
        ],
        row_no=row_no,
    )


def _identity_validation_item(
    *,
    field_name: str,
    final_value: Any,
    sources: list[tuple[str, Any]],
    normalizer,
    format_validator,
    missing_warning: str,
    invalid_message: str,
    mismatch_message: str,
    ok_message: str,
) -> TexasValidationItem:
    final_norm = normalizer(final_value)
    present_sources = [(label, value, normalizer(value)) for label, value in sources if str(value or "").strip()]
    if not format_validator(final_value):
        return _validation_item(
            field_name=field_name,
            final_value=final_value,
            status="error",
            message=invalid_message,
            sources=sources,
        )
    mismatched = [label for label, _value, normalized in present_sources if normalized != final_norm]
    if mismatched:
        return _validation_item(
            field_name=field_name,
            final_value=final_value,
            status="error",
            message=f"{mismatch_message}：{', '.join(mismatched)}",
            sources=sources,
        )
    if len(present_sources) < len(sources):
        return _validation_item(
            field_name=field_name,
            final_value=final_value,
            status="warning",
            message=missing_warning,
            sources=sources,
        )
    return _validation_item(
        field_name=field_name,
        final_value=final_value,
        status="ok",
        message=ok_message,
        sources=sources,
    )


def build_texas_validation_sections(
    *,
    final_mbl_no: str,
    final_hbl_no: str,
    awb: TexasAwbInfo,
    email_info: TexasEmailInfo,
    lines: list[TexasBookingLine],
) -> list[TexasValidationSection]:
    identity_items = [
        _identity_validation_item(
            field_name="MAWB / MBLNO",
            final_value=final_mbl_no,
            sources=[
                ("PDF Air Waybill", awb.mbl_no),
                ("邮件正文 MAWB", email_info.mbl_no),
            ],
            normalizer=normalize_airwaybill_no,
            format_validator=is_valid_mawb_no,
            missing_warning="MAWB 格式和校验位通过，但 PDF 或邮件正文有来源缺失。",
            invalid_message="MAWB 必须是 11 位数字，且后 8 位的最后一位必须通过 mod 7 校验。",
            mismatch_message="最终填入值与来源不一致",
            ok_message="PDF Air Waybill、邮件正文和最终填入值一致，且 MAWB 校验位通过。",
        ),
        _identity_validation_item(
            field_name="HAWB / H.B/LNO",
            final_value=final_hbl_no,
            sources=[
                ("PDF Air Waybill", awb.hbl_no),
                ("邮件标题 HB#", email_info.subject_hbl_no),
                ("邮件正文 HAWB", email_info.hbl_no),
            ],
            normalizer=normalize_hawb_no,
            format_validator=is_valid_hawb_no,
            missing_warning="HAWB 是 10 位数字，但 PDF、邮件标题或邮件正文有来源缺失。",
            invalid_message="HAWB / H.B/LNO 必须是 10 位数字。",
            mismatch_message="最终填入值与来源不一致",
            ok_message="PDF Air Waybill、邮件标题、邮件正文和最终填入值一致。",
        ),
    ]

    line_items: list[TexasValidationItem] = []
    for row_no, line in enumerate(lines, start=1):
        line_items.append(
            _validation_item(
                field_name="Invoice No.",
                final_value=line.invoice_no,
                status="ok" if is_valid_invoice_no(line.invoice_no) else "warning",
                message="Invoice No. 是 10 位数字。"
                if is_valid_invoice_no(line.invoice_no)
                else "Invoice No. 应为 10 位数字，请人工确认。",
                sources=[("Commercial Invoice", line.invoice_no)],
                row_no=row_no,
            )
        )
        line_items.append(
            _validation_item(
                field_name="PO No.",
                final_value=line.po_no,
                status="ok" if is_valid_po_no(line.po_no) else "warning",
                message="PO No. 符合 NPI+6位数字 或 J+8位数字。"
                if is_valid_po_no(line.po_no)
                else "PO No. 应为 9 位：NPI+6位数字 或 J+8位数字。",
                sources=[("Content List / Invoice", line.po_no)],
                row_no=row_no,
            )
        )
        line_items.append(
            _validation_item(
                field_name="Customer Part No.",
                final_value=line.customer_part_no,
                status="ok" if is_valid_part_no(line.customer_part_no) else "warning",
                message="PN 前缀在允许清单内。"
                if is_valid_part_no(line.customer_part_no)
                else "PN 前缀不在允许清单内，请人工确认。",
                sources=[("Content List / Invoice", line.customer_part_no)],
                row_no=row_no,
            )
        )

        calculated_total = _money(_as_decimal(line.quantity) * _as_decimal(line.price))
        read_total = _money(line.total_amount)
        amount_ok = calculated_total == read_total
        line_items.append(
            _validation_item(
                field_name="Total Amount",
                final_value=line.total_amount,
                status="ok" if amount_ok else "warning",
                message="Total Amount = Quantity x Price。"
                if amount_ok
                else "PDF 读取到的 Total Amount 与 Quantity x Price 计算值不一致，请人工确认。",
                sources=[
                    ("Quantity", line.quantity),
                    ("Price", line.price),
                    ("计算值", calculated_total),
                    ("PDF读取 Total", line.total_amount),
                ],
                row_no=row_no,
            )
        )

    return [
        TexasValidationSection(title="空运提单单号校验", items=identity_items),
        TexasValidationSection(title="明细字段校验", items=line_items),
    ]


def join_invoice_and_content_list_by_waybill(
    invoices: list[TexasInvoiceInfo],
    content_rows: list[TexasContentRow],
) -> tuple[list[TexasBookingLine], list[str]]:
    warnings: list[str] = []
    content_by_waybill: dict[str, list[TexasContentRow]] = {}
    for row in content_rows:
        content_by_waybill.setdefault(row.waybill_no, []).append(row)

    lines: list[TexasBookingLine] = []
    for invoice in sorted(invoices, key=lambda item: item.page_index):
        matches = content_by_waybill.get(invoice.ti_waybill_no, [])
        if not matches:
            fallback = _fallback_content_match(invoice, content_rows)
            if fallback is not None:
                matches = [fallback]
                warnings.append(
                    f"Invoice {invoice.invoice_no} used fallback content-list match; check waybill {invoice.ti_waybill_no}."
                )
            else:
                warnings.append(f"Invoice {invoice.invoice_no} has no matching Content List WAYB # {invoice.ti_waybill_no}.")
                matches = [TexasContentRow(waybill_no=invoice.ti_waybill_no)]

        for content in matches:
            if content.quantity not in (None, 0, "") and invoice.quantity not in (None, 0, ""):
                if _as_decimal(content.quantity) != _as_decimal(invoice.quantity):
                    warnings.append(
                        f"Quantity mismatch for invoice {invoice.invoice_no}: invoice {invoice.quantity}, content list {content.quantity}."
                    )
            lines.append(
                TexasBookingLine(
                    invoice_no=invoice.invoice_no,
                    invoice_date=invoice.invoice_date,
                    ti_waybill_no=invoice.ti_waybill_no,
                    po_no=content.po_no or normalize_po_no(invoice.customer_po_raw),
                    invoice_customer_po_raw=invoice.customer_po_raw,
                    customer_part_no=content.customer_part_no or invoice.customer_part_no,
                    made_in=invoice.made_in,
                    cartons=int(content.cartons or 1),
                    pallet=0,
                    gross_weight=content.gross_weight or 0,
                    box_size=content.box_size,
                    cbm=content.cbm,
                    quantity=invoice.quantity or content.quantity or 0,
                    price=invoice.price or 0,
                    currency=invoice.currency or "USD",
                    total_amount=invoice.total_amount or 0,
                )
            )
    return lines, warnings


def _fallback_content_match(invoice: TexasInvoiceInfo, content_rows: list[TexasContentRow]) -> TexasContentRow | None:
    clean_po = normalize_po_no(invoice.customer_po_raw)
    for row in content_rows:
        if clean_po and row.po_no == clean_po:
            return row
    for row in content_rows:
        if invoice.customer_part_no and row.customer_part_no == invoice.customer_part_no:
            return row
    for row in content_rows:
        if invoice.quantity and _as_decimal(row.quantity) == _as_decimal(invoice.quantity):
            return row
    return None


def parse_flex_texas_eml(eml_path: Path) -> TexasExtraction:
    if is_system_export_pdf(eml_path):
        raise ValueError("RH2604405 260611.pdf is a system export PDF and may only be used as expected/reference.")
    message = BytesParser(policy=policy.default).parsebytes(Path(eml_path).read_bytes())
    subject = str(message.get("subject") or "")
    email_date = str(message.get("date") or "")
    email_info = parse_texas_email_body(_message_text(message), email_date=email_date, subject=subject)
    pdf_attachments = _pdf_attachments(message)
    if not pdf_attachments:
        raise ValueError("No source PDF attachment was found in the Flex-Texas .eml.")

    all_pages: list[TexasPdfPage] = []
    parsed_pdf_names: list[str] = []
    warnings: list[str] = []
    for filename, payload in pdf_attachments:
        if is_system_export_pdf(filename):
            warnings.append(f"Skipped system export PDF reference: {filename}")
            continue
        pages = classify_texas_pdf_pages(payload, source_file=filename)
        all_pages.extend(pages)
        parsed_pdf_names.append(filename)
    if not all_pages:
        raise ValueError("No parser source PDF remained after filtering system export PDF references.")

    awb_infos = [parse_texas_awb_layout(page) for page in all_pages if page.page_type == "air_waybill"]
    invoices = [
        invoice
        for page in all_pages
        if page.page_type == "commercial_invoice_item"
        for invoice in parse_texas_commercial_invoice_layout(page)
    ]
    content_rows = [
        row
        for page in all_pages
        if page.page_type == "content_list"
        for row in parse_texas_content_list_layout(page)
    ]
    if not invoices:
        raise ValueError("No Commercial Invoice item page was parsed from the Flex-Texas source PDF.")
    if not content_rows:
        warnings.append("No Content List page was parsed; carton, weight, CBM, PO, and customer part fields may be incomplete.")

    lines, join_warnings = join_invoice_and_content_list_by_waybill(invoices, content_rows)
    warnings.extend(join_warnings)
    awb = awb_infos[0] if awb_infos else TexasAwbInfo()
    hbl_no = awb.hbl_no or email_info.subject_hbl_no or email_info.hbl_no
    mbl_no = awb.mbl_no or email_info.mbl_no
    if email_info.hbl_no and hbl_no and email_info.hbl_no != hbl_no:
        warnings.append(f"HAWB mismatch: email {email_info.hbl_no}, PDF {hbl_no}.")
    if email_info.mbl_no and mbl_no and email_info.mbl_no != mbl_no:
        warnings.append(f"MAWB mismatch: email {email_info.mbl_no}, PDF {mbl_no}.")

    validation_sections = build_texas_validation_sections(
        final_mbl_no=mbl_no,
        final_hbl_no=hbl_no,
        awb=awb,
        email_info=email_info,
        lines=lines,
    )

    return TexasExtraction(
        hbl_no=hbl_no,
        mbl_no=mbl_no,
        delivery_to_hub_date=email_info.delivery_to_hub_date,
        transport_company=awb.carrier_code or "EI",
        delivery_party="VIA AIR",
        shipper=next((invoice.shipper for invoice in invoices if invoice.shipper), ""),
        source_pdf=", ".join(parsed_pdf_names),
        pdf_page_count=len(all_pages),
        lines=lines,
        warnings=warnings,
        validation_sections=validation_sections,
    )


def export_flex_texas_source_pdf_tiff(eml_path: Path, output_path: Path, zoom: float = 2.0) -> Path:
    import fitz
    from PIL import Image

    message = BytesParser(policy=policy.default).parsebytes(Path(eml_path).read_bytes())
    images: list[Image.Image] = []
    matrix = fitz.Matrix(zoom, zoom)
    for filename, payload in _pdf_attachments(message):
        if is_system_export_pdf(filename):
            continue
        doc = fitz.open(stream=payload, filetype="pdf")
        try:
            for page in doc:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                images.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
        finally:
            doc.close()
    if not images:
        raise ValueError("No source PDF attachment was found for Flex-Texas TIF review.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = images[0], images[1:]
    try:
        first.save(output_path, format="TIFF", save_all=True, append_images=rest, compression="tiff_lzw")
    finally:
        for image in images:
            image.close()
    return output_path


def _pdf_attachments(message: Message) -> list[tuple[str, bytes]]:
    attachments: list[tuple[str, bytes]] = []
    for part in message.walk():
        filename = part.get_filename() or ""
        if not filename.lower().endswith(".pdf"):
            continue
        payload = part.get_payload(decode=True)
        if payload:
            attachments.append((filename, payload))
    return attachments


def flex_texas_rows_for_template(extraction: TexasExtraction) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in extraction.lines:
        rows.append(
            {
                "PO No. *": line.po_no,
                "PO Line": 0,
                "Invoice No.*": line.invoice_no,
                "Invoice Date": line.invoice_date,
                "Customer Part No. *": line.customer_part_no,
                "Part Description *": line.part_description,
                "Made In *": line.made_in,
                "Cartons*": line.cartons,
                "Pallet*": line.pallet,
                "G.Wt*": line.gross_weight,
                "CBM * ": line.cbm,
                "Quantity *": line.quantity,
                "Price*": line.price,
                "Currency *": line.currency,
                "Total Amount *": line.total_amount,
                "Tray Type": line.tray_type,
            }
        )
    return rows
