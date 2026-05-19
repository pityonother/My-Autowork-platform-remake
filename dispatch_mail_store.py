from __future__ import annotations

import html
import mimetypes
import re
import shutil
import sqlite3
import subprocess
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import make_msgid
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.etree import ElementTree as ET

from app.core.db import connect, run_migrations
from app.shared.lazy_imports import lazy_module
from app_paths import RUNTIME_DIR

pd = lazy_module("pandas")
xlrd = lazy_module("xlrd")
Image = lazy_module("PIL.Image")
ImageDraw = lazy_module("PIL.ImageDraw")
ImageFont = lazy_module("PIL.ImageFont")


DB_PATH = RUNTIME_DIR / "dispatch_mail.db"
SPREADSHEET_SUFFIXES = {".xls", ".xlsx", ".xlsm"}
WORD_SUFFIXES = {".doc", ".docx"}
CONTENT_MATCH_SUFFIXES = SPREADSHEET_SUFFIXES | WORD_SUFFIXES | {".pdf"}
GENERIC_ATTACHMENT_TOKENS = {
    "booking",
    "shipping",
    "order",
    "form",
    "new",
    "hong",
    "kong",
    "logistics",
    "limited",
    "ltd",
    "shipment",
    "shipper",
    "export",
    "import",
    "warehouse",
    "attached",
    "under",
    "please",
    "deliver",
    "container",
    "freight",
    "ocean",
    "airfreight",
    "04292026",
    "20260429",
}


@dataclass
class DispatchAttachment:
    original_name: str
    stored_path: Path
    content_type: str
    role: str = "so"
    text: str = ""
    text_status: str = ""


@dataclass
class DispatchDqth:
    attachment: DispatchAttachment
    customer_pos: list[str]
    cartons: Decimal
    gross_weight: Decimal
    pallets: Decimal
    preview_index: int = -1
    matched_ticket_index: int | None = None
    suggested_name: str = ""
    suggested_order: int | None = None
    final_name: str = ""
    status: str = "未匹配"


@dataclass
class DispatchSo:
    attachment: DispatchAttachment
    preview_index: int = -1
    matched_ticket_index: int | None = None
    score: float = 0
    suggested_name: str = ""
    suggested_order: int | None = None
    final_name: str = ""
    status: str = "未匹配"


@dataclass
class DispatchTicket:
    index: int
    tan_no: str
    customer_pos: list[str]
    remark: str
    cartons: Decimal
    gross_weight: Decimal
    pallets: Decimal
    row_start: int
    row_end: int
    table_image_path: Path | None = None
    email_image_path: Path | None = None
    dqth: DispatchDqth | None = None
    so: DispatchSo | None = None
    warehouse_code: str = ""
    address: str = ""
    note: str = ""
    show_carton_count_in_title: bool = False
    dqth_expected_order: int | None = None
    so_expected_order: int | None = None


@dataclass
class DispatchParseResult:
    session_id: str
    eml_name: str
    attachments_dir: Path
    output_dir: Path
    master: DispatchAttachment | None
    tickets: list[DispatchTicket] = field(default_factory=list)
    dqths: list[DispatchDqth] = field(default_factory=list)
    sos: list[DispatchSo] = field(default_factory=list)
    base_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmatched_dqths: list[DispatchDqth] = field(default_factory=list)
    unmatched_sos: list[DispatchSo] = field(default_factory=list)


def get_connection() -> sqlite3.Connection:
    return connect(DB_PATH)


def migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dispatch_mail_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


MIGRATIONS = {
    1: migration_001_initial_schema,
}


def init_dispatch_db() -> None:
    with get_connection() as conn:
        run_migrations(conn, MIGRATIONS)


def get_dispatch_settings() -> dict[str, str]:
    init_dispatch_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT setting_key, setting_value FROM dispatch_mail_settings").fetchall()
    data = {row["setting_key"]: row["setting_value"] for row in rows}
    return {
        "to_email": data.get("to_email", ""),
        "cc_email": data.get("cc_email", ""),
        "from_email": data.get("from_email", ""),
    }


def save_dispatch_settings(*, to_email: str, cc_email: str, from_email: str) -> None:
    init_dispatch_db()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO dispatch_mail_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            [
                ("to_email", to_email.strip()),
                ("cc_email", cc_email.strip()),
                ("from_email", from_email.strip()),
            ],
        )


def decimal_value(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan":
        return Decimal("0")
    try:
        return Decimal(text).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0")


def display_number(value: Decimal) -> str:
    value = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if value == value.to_integral_value():
        return str(int(value))
    return str(value.normalize())


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("\xa0", " ")
    if text.endswith(".0") and re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def normalize_po(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value)).upper()


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "attachment"


def attachment_extension(name: str) -> str:
    suffix = Path(name).suffix
    return suffix if suffix else ".bin"


def collapse_content_text(parts: Iterable[Any], *, limit: int = 120_000) -> str:
    text = " ".join(normalize_text(part) for part in parts if normalize_text(part))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def read_spreadsheet_text(path: Path, *, max_rows: int = 260, max_cols: int = 80) -> str:
    parts: list[str] = []
    suffix = path.suffix.lower()
    if suffix == ".xls":
        book = xlrd.open_workbook(path, formatting_info=False)
        for sheet in book.sheets():
            for row_index in range(min(sheet.nrows, max_rows)):
                for col_index in range(min(sheet.ncols, max_cols)):
                    value = normalize_text(sheet.cell_value(row_index, col_index))
                    if value:
                        parts.append(value)
        return collapse_content_text(parts)

    with pd.ExcelFile(path) as excel_file:
        for sheet_name in excel_file.sheet_names:
            df = excel_file.parse(sheet_name=sheet_name, header=None, nrows=max_rows, dtype=object)
            for row in df.fillna("").values.tolist():
                for value in row[:max_cols]:
                    value_text = normalize_text(value)
                    if value_text:
                        parts.append(value_text)
    return collapse_content_text(parts)


def read_pdf_text(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", "PDF 文本读取依赖不可用"

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return "", "PDF 已加密，无法自动读取"
        parts = [page.extract_text() or "" for page in reader.pages[:20]]
    except Exception as exc:
        return "", f"PDF 读取失败：{exc}"
    text = collapse_content_text(parts)
    if not text:
        return "", "PDF 可能是扫描件或图片型文件，未提取到文字"
    return text, "已读取 PDF 文本"


def read_docx_text(path: Path, *, max_paragraphs: int = 400) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(fragments).strip()
        if text:
            paragraphs.append(text)
        if len(paragraphs) >= max_paragraphs:
            break
    return collapse_content_text(paragraphs)


def read_doc_text_with_word(path: Path) -> tuple[str, str]:
    text_path = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.txt")
    script_path = text_path.with_suffix(".ps1")
    script = f"""
$ErrorActionPreference = 'Stop'
$documentPath = {powershell_literal(str(path))}
$textPath = {powershell_literal(str(text_path))}
$word = $null
$document = $null
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
    $document = $word.Documents.Open($documentPath, $false, $true)
    $document.SaveAs2($textPath, 7)
}}
finally {{
    if ($document) {{
        $document.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }}
    if ($word) {{
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }}
}}
"""
    script_path.write_text(script, encoding="utf-8")
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if completed.returncode != 0 or not text_path.exists():
            return "", "旧 Word 文件暂时无法自动读取"
        try:
            text = text_path.read_text(encoding="utf-16")
        except UnicodeError:
            text = text_path.read_text(encoding="utf-8", errors="replace")
        return collapse_content_text([text]), "已读取 Word 文本"
    except Exception as exc:
        return "", f"Word 读取失败：{exc}"
    finally:
        if script_path.exists():
            script_path.unlink()
        if text_path.exists():
            text_path.unlink()


def ensure_attachment_text(attachment: DispatchAttachment) -> None:
    if attachment.text_status:
        return
    suffix = attachment.stored_path.suffix.lower()
    if suffix in SPREADSHEET_SUFFIXES:
        try:
            attachment.text = read_spreadsheet_text(attachment.stored_path)
            attachment.text_status = "已读取表格文本" if attachment.text else "表格未提取到文字"
        except Exception as exc:
            attachment.text = ""
            attachment.text_status = f"表格读取失败：{exc}"
        return
    if suffix == ".pdf":
        attachment.text, attachment.text_status = read_pdf_text(attachment.stored_path)
        return
    if suffix == ".docx":
        try:
            attachment.text = read_docx_text(attachment.stored_path)
            attachment.text_status = "已读取 DOCX 文本" if attachment.text else "DOCX 未提取到文字"
        except Exception:
            attachment.text, attachment.text_status = read_doc_text_with_word(attachment.stored_path)
        return
    if suffix == ".doc":
        attachment.text, attachment.text_status = read_doc_text_with_word(attachment.stored_path)
        return
    attachment.text = ""
    attachment.text_status = "当前文件类型未参与内容读取"


def is_inline_or_body_image(part: Any) -> bool:
    content_type = part.get_content_type()
    if not content_type.startswith("image/"):
        return False
    disposition = part.get_content_disposition()
    content_id = part.get("Content-ID")
    return bool(content_id) or disposition != "attachment"


def extract_email_attachments(eml_path: Path, target_dir: Path) -> list[DispatchAttachment]:
    target_dir.mkdir(parents=True, exist_ok=True)
    msg = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    attachments: list[DispatchAttachment] = []
    for index, part in enumerate(msg.walk(), start=1):
        filename = part.get_filename()
        if not filename:
            continue
        disposition = part.get_content_disposition()
        if is_inline_or_body_image(part):
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        clean_name = safe_filename(filename)
        stored_path = target_dir / f"{index:03d}_{clean_name}"
        stored_path.write_bytes(payload)
        attachments.append(
            DispatchAttachment(
                original_name=filename,
                stored_path=stored_path,
                content_type=part.get_content_type(),
            )
        )
    return attachments


def looks_like_tan_master(path: Path) -> bool:
    attachment = DispatchAttachment(original_name=path.name, stored_path=path, content_type="")
    return looks_like_tan_master_attachment(attachment)


def find_header_row(rows: list[list[Any]], required: Sequence[str]) -> int:
    for idx, row in enumerate(rows):
        row_text = " ".join(normalize_text(cell) for cell in row)
        if all(item.lower() in row_text.lower() for item in required):
            return idx
    return 0


def header_index_map(header: Sequence[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header):
        text = normalize_text(cell).replace("\n", " ")
        if text:
            mapping[text] = idx
    return mapping


def find_column(mapping: dict[str, int], names: Sequence[str]) -> int | None:
    for name in names:
        for header, idx in mapping.items():
            if name.lower() in header.lower():
                return idx
    return None


def resolve_render_end_col(
    rows: list[list[Any]],
    *,
    header_row: int,
    start_row: int,
    end_row: int,
    preferred_cols: Sequence[int | None],
) -> int:
    last_col = max((col for col in preferred_cols if col is not None), default=0)
    for row in [rows[header_row], *rows[start_row : end_row + 1]]:
        for idx in range(len(row) - 1, -1, -1):
            if normalize_text(row[idx]):
                last_col = max(last_col, idx)
                break
    return last_col


def powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def extract_tail_paper_note(remark: str) -> str:
    text = normalize_text(remark)
    label = "\u5bc4\u5c3e\u7eb8"
    match = re.search(rf"{label}\s*[:\uff1a]\s*(.+)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip(" ;\uff1b,\uff0c")


def build_default_ticket_note(remark: str, *, today: date | None = None) -> str:
    base_date = today or date.today()
    cutoff = base_date + timedelta(days=1)
    parts = [f"\u622a{cutoff.day}\u53f717\u70b9"]
    tail_paper_note = extract_tail_paper_note(remark)
    if tail_paper_note:
        parts.append(f"\u5bc4\u5c3e\u7eb8\uff1a{tail_paper_note}")
    return "\n".join(parts)


def should_show_cartons_in_title(detail_rows: Sequence[Sequence[Any]], carton_col: int | None, pallet_col: int | None) -> bool:
    if carton_col is None or pallet_col is None:
        return False
    for row in detail_rows:
        cartons = decimal_value(row[carton_col]) if carton_col < len(row) else Decimal("0")
        pallets = decimal_value(row[pallet_col]) if pallet_col < len(row) else Decimal("0")
        if cartons > 0 and pallets == 0:
            return True
    return False


def parse_master_workbook(master: DispatchAttachment, output_dir: Path) -> list[DispatchTicket]:
    if master.stored_path.suffix.lower() != ".xls":
        with pd.ExcelFile(master.stored_path) as excel_file:
            sheet_name = excel_file.sheet_names[0]
            df = excel_file.parse(sheet_name=sheet_name, header=None)
        rows = df.fillna("").values.tolist()
        merged_cells: list[tuple[int, int, int, int]] = []
    else:
        book = xlrd.open_workbook(master.stored_path, formatting_info=True)
        sheet = book.sheet_by_index(0)
        sheet_name = sheet.name
        rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        merged_cells = list(sheet.merged_cells)

    header_row = find_header_row(rows, ["Customer PO", "卡板"])
    mapping = header_index_map(rows[header_row])
    item_col = find_column(mapping, ["Item", "序号"])
    po_col = find_column(mapping, ["Customer PO"])
    pcs_col = find_column(mapping, ["总数量PCS", "PCS"])
    gross_col = find_column(mapping, ["毛重KG", "毛重"])
    carton_col = find_column(mapping, ["箱数"])
    pallet_col = find_column(mapping, ["卡板数", "卡板"])
    remark_col = find_column(mapping, ["备注", "LOD ID", "包装尺寸"])
    if po_col is None or pallet_col is None:
        raise ValueError("Tan# 总表缺少 Customer PO 或 卡板数列，无法拆票。")

    tan_rows: list[tuple[int, str, str]] = []
    tan_pattern = re.compile(r"^TAN\s*#\s*(\d+)\b", flags=re.IGNORECASE)
    for row_idx, row in enumerate(rows):
        for cell in row:
            match = tan_pattern.search(normalize_text(cell))
            if match:
                remark = " ".join(normalize_text(value) for value in row if normalize_text(value))
                tan_rows.append((row_idx, f"TAN#{match.group(1)}", remark))
                break

    tickets: list[DispatchTicket] = []
    previous_tan_row = header_row
    for ticket_index, (tan_row, tan_no, remark) in enumerate(tan_rows, start=1):
        detail_start = previous_tan_row + 1
        detail_rows = [row for row in rows[detail_start:tan_row] if any(normalize_text(cell) for cell in row)]
        pos = sorted({normalize_po(row[po_col]) for row in detail_rows if po_col < len(row) and normalize_po(row[po_col])})
        cartons = sum((decimal_value(row[carton_col]) for row in detail_rows if carton_col is not None and carton_col < len(row)), Decimal("0"))
        gross = sum((decimal_value(row[gross_col]) for row in detail_rows if gross_col is not None and gross_col < len(row)), Decimal("0"))
        pallets = sum((decimal_value(row[pallet_col]) for row in detail_rows if pallet_col < len(row)), Decimal("0"))
        show_cartons = should_show_cartons_in_title(detail_rows, carton_col, pallet_col)
        if not remark and remark_col is not None:
            remark = " ".join(normalize_text(row[remark_col]) for row in detail_rows if remark_col < len(row) and normalize_text(row[remark_col]))
        preview_rows = build_ticket_snapshot_rows(
            rows,
            start_row=detail_start,
            tan_row=tan_row,
            tan_no=tan_no,
            remark=remark,
            item_col=item_col,
            po_col=po_col,
            pcs_col=pcs_col,
            pallet_col=pallet_col,
            carton_col=carton_col,
        )
        ticket = DispatchTicket(
            index=ticket_index,
            tan_no=tan_no,
            customer_pos=pos,
            remark=remark,
            cartons=cartons,
            gross_weight=gross,
            pallets=pallets,
            row_start=detail_start,
            row_end=tan_row,
            note=build_default_ticket_note(remark),
            show_carton_count_in_title=show_cartons,
        )
        ticket.table_image_path = render_ticket_snapshot_image(
            tan_no=tan_no,
            preview_rows=preview_rows,
            output_path=output_dir / f"ticket_{ticket_index}.png",
        )
        email_start_col = item_col if item_col is not None else 0
        email_end_col = pallet_col if pallet_col is not None else max(email_start_col, len(rows[header_row]) - 1)
        if email_end_col < email_start_col:
            email_start_col, email_end_col = email_end_col, email_start_col
        ticket.email_image_path = render_master_ticket_image(
            workbook_path=master.stored_path,
            sheet_name=sheet_name,
            rows=rows,
            header_row=header_row,
            start_row=detail_start,
            end_row=tan_row,
            start_col=email_start_col,
            end_col=email_end_col,
            tan_no=tan_no,
            tan_remark=remark,
            output_path=output_dir / f"ticket_{ticket_index}_email.png",
        )
        tickets.append(ticket)
        previous_tan_row = tan_row
    return tickets


def parse_dqth_file(attachment: DispatchAttachment) -> DispatchDqth:
    if attachment.stored_path.suffix.lower() == ".xls":
        book = xlrd.open_workbook(attachment.stored_path, formatting_info=False)
        sheet = book.sheet_by_index(0)
        rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
    else:
        with pd.ExcelFile(attachment.stored_path) as excel_file:
            df = excel_file.parse(sheet_name=0, header=None)
        rows = df.fillna("").values.tolist()
    header_row = find_header_row(rows, ["Customer PO"])
    mapping = header_index_map(rows[header_row])
    po_col = find_column(mapping, ["Customer PO", "订单号"])
    carton_col = find_column(mapping, ["CTN", "箱数"])
    pallet_col = find_column(mapping, ["Pallet", "卡板"])
    gross_col = find_column(mapping, ["Gross weight", "总毛重"])
    data_rows = rows[header_row + 1 :]
    pos = sorted({normalize_po(row[po_col]) for row in data_rows if po_col is not None and po_col < len(row) and normalize_po(row[po_col])})
    cartons = sum((decimal_value(row[carton_col]) for row in data_rows if carton_col is not None and carton_col < len(row)), Decimal("0"))
    pallets = sum((decimal_value(row[pallet_col]) for row in data_rows if pallet_col is not None and pallet_col < len(row)), Decimal("0"))
    gross = sum((decimal_value(row[gross_col]) for row in data_rows if gross_col is not None and gross_col < len(row)), Decimal("0"))
    return DispatchDqth(attachment=attachment, customer_pos=pos, cartons=cartons, pallets=pallets, gross_weight=gross)


def read_dispatch_attachment_preview(attachment: DispatchAttachment, *, max_rows: int = 60, max_cols: int = 18) -> tuple[str, list[list[str]]] | None:
    suffix = attachment.stored_path.suffix.lower()
    if suffix == ".xls":
        book = xlrd.open_workbook(attachment.stored_path, formatting_info=False)
        sheet = book.sheet_by_index(0)
        rows = [
            [normalize_text(sheet.cell_value(r, c)) for c in range(min(sheet.ncols, max_cols))]
            for r in range(min(sheet.nrows, max_rows))
        ]
        return sheet.name, rows
    if suffix in {".xlsx", ".xlsm"}:
        with pd.ExcelFile(attachment.stored_path) as excel_file:
            sheet_name = excel_file.sheet_names[0]
            df = excel_file.parse(sheet_name=sheet_name, header=None, nrows=max_rows)
        rows = [
            [normalize_text(cell) for cell in row[:max_cols]]
            for row in df.fillna("").values.tolist()
        ]
        return sheet_name, rows
    return None


def read_docx_text_preview(path: Path, *, max_paragraphs: int = 120) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(fragments).strip()
        if text:
            paragraphs.append(text)
        if len(paragraphs) >= max_paragraphs:
            break
    return paragraphs


def render_word_preview_pdf(document_path: Path, output_path: Path) -> Path | None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = output_path.with_suffix(".render-word.ps1")
    script = f"""
$ErrorActionPreference = 'Stop'
$documentPath = {powershell_literal(str(document_path))}
$outputPath = {powershell_literal(str(output_path))}
$word = $null
$document = $null
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
    $document = $word.Documents.Open($documentPath, $false, $true)
    $document.ExportAsFixedFormat($outputPath, 17)
}}
finally {{
    if ($document) {{
        $document.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }}
    if ($word) {{
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }}
}}
"""
    script_path.write_text(script, encoding="utf-8")
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if completed.returncode == 0 and output_path.exists():
            return output_path
        return None
    finally:
        if script_path.exists():
            script_path.unlink()


def match_sos(tickets: list[DispatchTicket], sos: list[DispatchSo], threshold: float = 0.40) -> None:
    available = set(range(len(tickets)))
    for so in sos:
        scores: list[tuple[float, int]] = []
        for idx in available:
            score = score_so_match(so, tickets[idx])
            scores.append((score, idx))
        if scores:
            scores.sort(key=lambda item: (-item[0], item[1]))
            score, idx = scores[0]
            next_score = scores[1][0] if len(scores) > 1 else 0
            so.score = score
            if score >= threshold and (score >= 0.85 or score - next_score >= 0.06):
                so.matched_ticket_index = idx
                so.status = "已匹配"
                tickets[idx].so = so
                available.discard(idx)


def dispatch_load_label(ticket: DispatchTicket) -> str:
    pallets_text = display_number(ticket.pallets)
    cartons_text = display_number(ticket.cartons)
    if ticket.show_carton_count_in_title and ticket.cartons > 0:
        return f"{pallets_text}板+{cartons_text}箱"
    return f"{pallets_text}板"


def is_auto_attachment_name(*, current_name: str, original_name: str, suggested_name: str) -> bool:
    normalized_current = current_name.strip()
    if not normalized_current:
        return True
    return normalized_current in {original_name.strip(), suggested_name.strip()}


def refresh_dispatch_match_status(result: DispatchParseResult) -> None:
    result.unmatched_dqths = [item for item in result.dqths if all(ticket.dqth is not item for ticket in result.tickets)]
    result.unmatched_sos = [item for item in result.sos if all(ticket.so is not item for ticket in result.tickets)]
    warnings = list(result.base_warnings)
    if result.tickets and len(result.dqths) != len(result.tickets):
        warnings.append(f"DQT 数量 {len(result.dqths)} 与 Tan# 票数 {len(result.tickets)} 不一致。")
    for ticket in result.tickets:
        if ticket.dqth is None:
            warnings.append(f"{ticket.tan_no} 未匹配到 DQT 装箱单。")
    result.warnings = warnings


def render_master_ticket_image_with_excel(
    *,
    workbook_path: Path,
    sheet_name: str,
    header_row: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    tan_no: str,
    tan_remark: str,
    output_path: Path,
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = output_path.with_suffix(".render.ps1")
    temp_sheet_name = f"DispatchRender{uuid.uuid4().hex[:6]}"
    header_row_excel = header_row + 1
    start_row_excel = start_row + 1
    end_row_excel = end_row + 1
    start_col_excel = start_col + 1
    end_col_excel = end_col + 1
    body_row_count = end_row - start_row + 1
    temp_end_row = body_row_count + 1
    script = f"""
$ErrorActionPreference = 'Stop'
$workbookPath = {powershell_literal(str(workbook_path))}
$sheetName = {powershell_literal(sheet_name)}
$outputPath = {powershell_literal(str(output_path))}
$tempSheetName = {powershell_literal(temp_sheet_name)}
$headerRow = {header_row_excel}
$startRow = {start_row_excel}
$endRow = {end_row_excel}
$startCol = {start_col_excel}
$endCol = {end_col_excel}
$colCount = $endCol - $startCol + 1
$tempEndRow = {temp_end_row}
$tanNo = {powershell_literal(tan_no)}
$tanRemark = {powershell_literal(tan_remark)}
$sheet = $null
$tempSheet = $null
$chartObject = $null
$chart = $null
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$workbook = $excel.Workbooks.Open($workbookPath, 0, $true)
try {{
    $sheet = $workbook.Worksheets.Item($sheetName)
    $tempSheet = $workbook.Worksheets.Add()
    $tempSheet.Name = $tempSheetName

    $sourceHeader = $sheet.Range($sheet.Cells.Item($headerRow, $startCol), $sheet.Cells.Item($headerRow, $endCol))
    $sourceBody = $sheet.Range($sheet.Cells.Item($startRow, $startCol), $sheet.Cells.Item($endRow, $endCol))
    $targetHeader = $tempSheet.Range($tempSheet.Cells.Item(1, 1), $tempSheet.Cells.Item(1, $colCount))
    $targetBody = $tempSheet.Range($tempSheet.Cells.Item(2, 1), $tempSheet.Cells.Item($tempEndRow, $colCount))

    $sourceHeader.Copy()
    $targetHeader.PasteSpecial(-4104)
    $sourceBody.Copy()
    $targetBody.PasteSpecial(-4104)
    $excel.CutCopyMode = 0

    for ($sourceCol = $startCol; $sourceCol -le $endCol; $sourceCol++) {{
        $targetCol = $sourceCol - $startCol + 1
        $tempSheet.Columns.Item($targetCol).ColumnWidth = $sheet.Columns.Item($sourceCol).ColumnWidth
    }}
    if ($colCount -ge 1) {{
        $tempSheet.Columns.Item(1).ColumnWidth = [Math]::Max($tempSheet.Columns.Item(1).ColumnWidth, 15)
    }}
    $tempSheet.Rows.Item(1).RowHeight = $sheet.Rows.Item($headerRow).RowHeight
    for ($offset = 0; $offset -lt ($endRow - $startRow + 1); $offset++) {{
        $tempSheet.Rows.Item($offset + 2).RowHeight = $sheet.Rows.Item($startRow + $offset).RowHeight
    }}
    foreach ($row in @($headerRow) + ($startRow..$endRow)) {{
        $targetRow = if ($row -eq $headerRow) {{ 1 }} else {{ $row - $startRow + 2 }}
        for ($sourceCol = $startCol; $sourceCol -le $endCol; $sourceCol++) {{
            $cell = $sheet.Cells.Item($row, $sourceCol)
            if (-not $cell.MergeCells) {{
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($cell) | Out-Null
                continue
            }}
            $mergeArea = $cell.MergeArea
            $firstCell = $mergeArea.Cells.Item(1, 1)
            if ($firstCell.Row -ne $row -or $firstCell.Column -ne $sourceCol) {{
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($firstCell) | Out-Null
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mergeArea) | Out-Null
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($cell) | Out-Null
                continue
            }}
            $mergeEndCol = [Math]::Min($endCol, $mergeArea.Column + $mergeArea.Columns.Count - 1)
            $targetStartCol = $sourceCol - $startCol + 1
            $targetEndCol = $mergeEndCol - $startCol + 1
            $targetRange = $tempSheet.Range(
                $tempSheet.Cells.Item($targetRow, $targetStartCol),
                $tempSheet.Cells.Item($targetRow + $mergeArea.Rows.Count - 1, $targetEndCol)
            )
            if ($targetRange.MergeCells) {{
                $targetRange.UnMerge()
            }}
            $targetRange.Merge() | Out-Null
            $targetRange.HorizontalAlignment = $mergeArea.HorizontalAlignment
            $targetRange.VerticalAlignment = $mergeArea.VerticalAlignment
            $targetRange.WrapText = $mergeArea.WrapText
            if ($mergeArea.WrapText -and $mergeArea.Rows.Count -eq 1) {{
                $sourceText = [string]$firstCell.Text
                $estimatedLines = [Math]::Max(1, [Math]::Ceiling($sourceText.Length / 32.0))
                $targetRowHeight = [Math]::Max($tempSheet.Rows.Item($targetRow).RowHeight, $sheet.Rows.Item($row).RowHeight * $estimatedLines)
                $tempSheet.Rows.Item($targetRow).RowHeight = $targetRowHeight
            }}
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($targetRange) | Out-Null
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($firstCell) | Out-Null
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mergeArea) | Out-Null
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($cell) | Out-Null
        }}
    }}

    $tanDisplayRow = $tempEndRow
    $tanLabelCell = $tempSheet.Cells.Item($tanDisplayRow, 1)
    $tanLabelCell.Value2 = $tanNo
    if ($colCount -gt 1) {{
        $tanRemarkRange = $tempSheet.Range($tempSheet.Cells.Item($tanDisplayRow, 2), $tempSheet.Cells.Item($tanDisplayRow, $colCount))
        if ($tanRemarkRange.MergeCells) {{
            $tanRemarkRange.UnMerge()
        }}
        $tanRemarkRange.Merge() | Out-Null
        $tempSheet.Cells.Item($tanDisplayRow, 2).Value2 = $tanRemark
        $tanRemarkRange.WrapText = $true
        $tanRemarkRange.HorizontalAlignment = -4131
        $tanRemarkRange.VerticalAlignment = -4108
        $tanRemarkRange.Rows.AutoFit() | Out-Null
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tanRemarkRange) | Out-Null
    }} else {{
        $tanLabelCell.Value2 = $tanRemark
        $tanLabelCell.WrapText = $true
        $tanLabelCell.Rows.AutoFit() | Out-Null
    }}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tanLabelCell) | Out-Null

    $usedRange = $tempSheet.Range($tempSheet.Cells.Item(1, 1), $tempSheet.Cells.Item($tempEndRow, $colCount))
    $chartObject = $tempSheet.ChartObjects().Add(0, 0, $usedRange.Width + 6, $usedRange.Height + 6)
    $chart = $chartObject.Chart
    $usedRange.CopyPicture(1, 2)
    $chart.Paste()
    $chart.Export($outputPath) | Out-Null
    $chartObject.Delete()
    $tempSheet.Delete()
}}
finally {{
    $workbook.Close($false)
    $excel.Quit()
    if ($sheet) {{ [System.Runtime.InteropServices.Marshal]::ReleaseComObject($sheet) | Out-Null }}
    if ($tempSheet) {{ [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tempSheet) | Out-Null }}
    if ($chart) {{ [System.Runtime.InteropServices.Marshal]::ReleaseComObject($chart) | Out-Null }}
    if ($chartObject) {{ [System.Runtime.InteropServices.Marshal]::ReleaseComObject($chartObject) | Out-Null }}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}}
"""
    script_path.write_text(script, encoding="utf-8")
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return completed.returncode == 0 and output_path.exists()
    finally:
        if script_path.exists():
            script_path.unlink()


def render_master_ticket_image_fallback(
    rows: list[list[Any]],
    header_row: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    tan_no: str,
    tan_remark: str,
    output_path: Path,
) -> Path:
    selected_rows = [rows[header_row]] + rows[start_row : end_row + 1]
    selected_rows = [[normalize_text(cell) for cell in row[start_col : end_col + 1]] for row in selected_rows]
    if selected_rows:
        tan_row = selected_rows[-1]
        if tan_row:
            tan_row[0] = tan_no
            if len(tan_row) > 1:
                tan_row[1] = tan_remark
    try:
        font = ImageFont.truetype("msyh.ttc", 16)
    except Exception:
        font = ImageFont.load_default()
    padding_x = 10
    padding_y = 8
    line_height = font.getbbox("A")[3] - font.getbbox("A")[1] + 5
    col_widths: list[int] = []
    column_count = max(1, end_col - start_col + 1)
    for col_idx in range(column_count):
        width = 140 if col_idx == 0 else 86
        for row in selected_rows:
            text = row[col_idx] if col_idx < len(row) else ""
            width = max(width, min(360, int(font.getlength(text[:60])) + padding_x * 2))
        col_widths.append(width)
    width = sum(col_widths) + 1
    wrapped_rows: list[list[list[str]]] = []
    row_heights: list[int] = []
    for row_idx, row in enumerate(selected_rows):
        is_tan_row = row_idx == len(selected_rows) - 1
        wrapped_row: list[list[str]] = []
        max_lines = 1
        if is_tan_row and len(col_widths) > 1:
            wrapped_row.append(wrap_text_by_width(row[0] if row else "", font, col_widths[0] - padding_x * 2))
            remark_width = sum(col_widths[1:]) - padding_x * 2
            remark_lines = wrap_text_by_width(tan_remark, font, remark_width)
            wrapped_row.append(remark_lines)
            max_lines = max(len(wrapped_row[0]), len(remark_lines))
        else:
            for col_idx, col_width in enumerate(col_widths):
                text = row[col_idx] if col_idx < len(row) else ""
                wrapped = wrap_text_by_width(text, font, col_width - padding_x * 2)
                wrapped_row.append(wrapped)
                max_lines = max(max_lines, len(wrapped))
        wrapped_rows.append(wrapped_row)
        row_heights.append(max(36, max_lines * line_height + padding_y * 2))
    height = sum(row_heights) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 0
    for row_idx, row in enumerate(selected_rows):
        x = 0
        fill = "#f2eadc" if row_idx == 0 else "white"
        is_tan_row = row_idx == len(selected_rows) - 1
        if is_tan_row:
            fill = "#fff1dc"
        row_height = row_heights[row_idx]
        if is_tan_row and len(col_widths) > 1:
            first_width = col_widths[0]
            draw.rectangle([x, y, x + first_width, y + row_height], fill=fill, outline="#7d6f60")
            text_y = y + padding_y
            for line in wrapped_rows[row_idx][0]:
                draw.text((x + padding_x, text_y), line, fill="#1f2933", font=font)
                text_y += line_height
            merged_width = sum(col_widths[1:])
            draw.rectangle([x + first_width, y, x + first_width + merged_width, y + row_height], fill=fill, outline="#7d6f60")
            text_y = y + padding_y
            for line in wrapped_rows[row_idx][1]:
                draw.text((x + first_width + padding_x, text_y), line, fill="#1f2933", font=font)
                text_y += line_height
            y += row_height
            continue
        for col_idx, col_width in enumerate(col_widths):
            draw.rectangle([x, y, x + col_width, y + row_height], fill=fill, outline="#7d6f60")
            text_y = y + padding_y
            for line in wrapped_rows[row_idx][col_idx]:
                draw.text((x + padding_x, text_y), line, fill="#1f2933", font=font)
                text_y += line_height
            x += col_width
        y += row_height
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def render_master_ticket_image(
    *,
    workbook_path: Path,
    sheet_name: str,
    rows: list[list[Any]],
    header_row: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    tan_no: str,
    tan_remark: str,
    output_path: Path,
) -> Path:
    if render_master_ticket_image_with_excel(
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        header_row=header_row,
        start_row=start_row,
        end_row=end_row,
        start_col=start_col,
        end_col=end_col,
        tan_no=tan_no,
        tan_remark=tan_remark,
        output_path=output_path,
    ):
        return output_path
    return render_master_ticket_image_fallback(
        rows,
        header_row,
        start_row,
        end_row,
        start_col,
        end_col,
        tan_no,
        tan_remark,
        output_path,
    )


def build_ticket_snapshot_rows(
    rows: list[list[Any]],
    *,
    start_row: int,
    tan_row: int,
    tan_no: str,
    remark: str,
    item_col: int | None,
    po_col: int | None,
    pcs_col: int | None,
    pallet_col: int | None,
    carton_col: int | None,
) -> list[list[str]]:
    snapshot_rows: list[list[str]] = []
    for row in rows[start_row:tan_row]:
        if not any(normalize_text(cell) for cell in row):
            continue
        snapshot_rows.append(
            [
                normalize_text(row[item_col]) if item_col is not None and item_col < len(row) else "",
                normalize_text(row[po_col]) if po_col is not None and po_col < len(row) else "",
                normalize_text(row[pcs_col]) if pcs_col is not None and pcs_col < len(row) else "",
                normalize_text(row[pallet_col]) if pallet_col is not None and pallet_col < len(row) else "",
                normalize_text(row[carton_col]) if carton_col is not None and carton_col < len(row) else "",
                "",
            ]
        )
    snapshot_rows.append([tan_no, "", "", "", "", remark])
    return snapshot_rows


def wrap_text_by_width(text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return [""]
    lines: list[str] = []
    for paragraph in normalized.splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = f"{current}{char}"
            if current and font.getlength(candidate) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current or "")
    return lines or [""]


def render_ticket_snapshot_image(*, tan_no: str, preview_rows: list[list[str]], output_path: Path) -> Path:
    try:
        title_font = ImageFont.truetype("msyh.ttc", 24)
        header_font = ImageFont.truetype("msyh.ttc", 18)
        body_font = ImageFont.truetype("msyh.ttc", 18)
    except Exception:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    headers = ["序号 / Tan#", "PO", "PCS数量", "板数", "箱数", "备注"]
    col_widths = [170, 300, 135, 110, 110, 760]
    cell_padding_x = 14
    cell_padding_y = 10
    line_height = body_font.getbbox("A")[3] - body_font.getbbox("A")[1] + 6
    header_line_height = header_font.getbbox("A")[3] - header_font.getbbox("A")[1] + 6
    title_height = 66
    row_heights: list[int] = []
    wrapped_rows: list[list[list[str]]] = []

    for row in preview_rows:
        wrapped_row: list[list[str]] = []
        max_lines = 1
        for value, width in zip(row, col_widths, strict=False):
            wrapped = wrap_text_by_width(value, body_font, width - cell_padding_x * 2)
            wrapped_row.append(wrapped)
            max_lines = max(max_lines, len(wrapped))
        wrapped_rows.append(wrapped_row)
        row_heights.append(max(42, max_lines * line_height + cell_padding_y * 2))

    table_width = sum(col_widths) + 1
    header_height = max(46, header_line_height + cell_padding_y * 2)
    total_height = title_height + header_height + sum(row_heights) + 1
    image = Image.new("RGB", (table_width, total_height), "#fffdf8")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((0, 0, table_width - 1, title_height - 6), radius=18, fill="#f6ede1", outline="#d7c7af")
    draw.text((18, 18), f"匹配总表预览  {tan_no}", fill="#7b461c", font=title_font)

    y = title_height
    x = 0
    for header, width in zip(headers, col_widths, strict=False):
        draw.rectangle([x, y, x + width, y + header_height], fill="#efe2ce", outline="#cdbba0")
        draw.text((x + cell_padding_x, y + cell_padding_y), header, fill="#3e2a1f", font=header_font)
        x += width
    y += header_height

    for row_index, wrapped_row in enumerate(wrapped_rows):
        row = preview_rows[row_index]
        is_tan_row = bool(row and row[0].upper().startswith("TAN#"))
        row_fill = "#fff1dc" if is_tan_row else ("#ffffff" if row_index % 2 == 0 else "#fbf6ee")
        row_height = row_heights[row_index]
        x = 0
        for col_index, width in enumerate(col_widths):
            draw.rectangle([x, y, x + width, y + row_height], fill=row_fill, outline="#d7c7af")
            lines = wrapped_row[col_index]
            text_y = y + cell_padding_y
            for line in lines:
                draw.text((x + cell_padding_x, text_y), line, fill="#1f2933", font=body_font)
                text_y += line_height
            x += width
        y += row_height

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def parse_dispatch_eml(session_id: str, eml_path: Path, uploads_dir: Path, outputs_dir: Path) -> DispatchParseResult:
    attachment_dir = uploads_dir / session_id / "dispatch_attachments"
    output_dir = outputs_dir / f"dispatch_{session_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    attachments = extract_email_attachments(eml_path, attachment_dir)
    if not attachments:
        raise ValueError("客户邮件没有可处理的附件。")
    master, dqth_attachments, so_attachments, warnings = classify_attachments(attachments)
    tickets: list[DispatchTicket] = []
    if master:
        tickets = parse_master_workbook(master, output_dir)
    dqths = [parse_dqth_file(item) for item in dqth_attachments]
    for idx, dqth in enumerate(dqths):
        dqth.preview_index = idx
    sos = [DispatchSo(attachment=item, preview_index=idx) for idx, item in enumerate(so_attachments)]
    if tickets:
        match_dqths(tickets, dqths)
        match_sos(tickets, sos)
        apply_attachment_names(tickets, dqths, sos)
    base_warnings = list(warnings)
    if master and not tickets:
        base_warnings.append("已识别总表，但没有拆出 Tan# 票段。")
    result = DispatchParseResult(
        session_id=session_id,
        eml_name=eml_path.name,
        attachments_dir=attachment_dir,
        output_dir=output_dir,
        master=master,
        tickets=tickets,
        dqths=dqths,
        sos=sos,
        base_warnings=base_warnings,
    )
    refresh_dispatch_match_status(result)
    return result


def resolve_assignments(result: DispatchParseResult, form: dict[str, Any]) -> None:
    dqth_by_ticket: dict[int, DispatchDqth | None] = {}
    so_by_ticket: dict[int, DispatchSo | None] = {}
    for ticket in result.tickets:
        dqth_choice = str(form.get(f"dqth_match_{ticket.index}", "")).strip()
        so_choice = str(form.get(f"so_match_{ticket.index}", "")).strip()
        chosen_dqth = None
        chosen_so = None
        if dqth_choice.isdigit():
            dqth_index = int(dqth_choice)
            if 0 <= dqth_index < len(result.dqths):
                chosen_dqth = result.dqths[dqth_index]
        if so_choice.isdigit():
            so_index = int(so_choice)
            if 0 <= so_index < len(result.sos):
                chosen_so = result.sos[so_index]
        dqth_by_ticket[ticket.index] = chosen_dqth
        so_by_ticket[ticket.index] = chosen_so

    for dqth in result.dqths:
        dqth.matched_ticket_index = None
    for so in result.sos:
        so.matched_ticket_index = None

    for ticket in result.tickets:
        ticket.dqth = dqth_by_ticket[ticket.index]
        ticket.so = so_by_ticket[ticket.index]
        if ticket.dqth:
            ticket.dqth.matched_ticket_index = ticket.index - 1
        if ticket.so:
            ticket.so.matched_ticket_index = ticket.index - 1

    apply_attachment_names(result.tickets, result.dqths, result.sos)

    for ticket in result.tickets:
        if ticket.dqth:
            ticket.dqth.final_name = form.get(f"dqth_name_{ticket.index}", ticket.dqth.final_name).strip() or ticket.dqth.final_name
        if ticket.so:
            ticket.so.final_name = form.get(f"so_name_{ticket.index}", ticket.so.final_name).strip() or ticket.so.final_name
    refresh_dispatch_match_status(result)


def update_ticket_compose_fields(result: DispatchParseResult, form: dict[str, Any]) -> None:
    for ticket in result.tickets:
        ticket.warehouse_code = form.get(f"warehouse_code_{ticket.index}", "").strip()
        ticket.address = form.get(f"address_{ticket.index}", "").strip()
        ticket.note = form.get(f"note_{ticket.index}", "").strip()


def build_dispatch_subject(tracking_no: str, total_pallets: Decimal, arrival_day: str, arrival_hour: str) -> str:
    return f"{tracking_no} 伟创力出口{display_number(total_pallets)}板，预计{arrival_day}号{arrival_hour}点前到倉庫 貨物到倉庫有扁箱請第一時間拍照通知，謝謝"


def display_arrival_deadline(arrival_hour: str) -> str:
    value = arrival_hour.strip()
    if not value:
        return "17：00"
    if ":" in value or "：" in value or "点" in value:
        return value
    return f"{value}：00"


def build_dispatch_ticket_title(ticket: DispatchTicket) -> str:
    return dispatch_load_label(ticket)


def build_dispatch_body_html(result: DispatchParseResult, arrival_hour: str, truck_plate: str, image_cids: dict[int, str]) -> str:
    deadline_text = display_arrival_deadline(arrival_hour)
    sections = [
        '<html><head><meta http-equiv="content-type" content="text/html; charset=UTF-8"></head><body>',
        "<div style=\"font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif; font-size:15px; line-height:1.5; color:#000000;\">",
        "<p style=\"margin:0; font-size:15px;\">Dear Kinki</p>",
        "<p style=\"margin:0; font-size:15px;\">"
        "请查收附件的交仓文件和装箱单，预计"
        f"<span style=\"color:#ff0000; font-weight:700;\">{html.escape(deadline_text)}前到仓库</span>"
        "，卸货车牌 "
        f"<span style=\"color:#ff0000; font-weight:700; font-size:27px;\">{html.escape(truck_plate)}</span>"
        "，到仓后卸货请注意，有破损请第一时间通知，"
        "</p>",
        "<p style=\"margin:0 0 12px 0; font-size:15px;\">另外请注意交仓要求和时间，谢谢。<span style=\"color:#ff0000;\">（注意伟创力的发票不可拿去交仓，装箱单发票仅供仓库核对货）</span></p>",
    ]
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"]
    for idx, ticket in enumerate(result.tickets, start=1):
        label = numerals[idx - 1] if idx - 1 < len(numerals) else str(idx)
        cid = image_cids.get(ticket.index, "")
        sections.append("<p style=\"margin:0; font-size:29px; line-height:1.1;\">--------------------------------</p>" if idx > 1 else "")
        sections.append(
            f"<p style=\"margin:0; font-size:21px;\">{label}：{html.escape(build_dispatch_ticket_title(ticket))}交{html.escape(ticket.warehouse_code)}：{html.escape(ticket.address).replace(chr(10), '<br>')}</p>"
        )
        if cid:
            sections.append(f"<p style=\"margin:0;\"><img src=\"cid:{cid}\" style=\"max-width:100%; height:auto; display:block;\"></p>")
        sections.append(
            f"<p style=\"margin:0 0 6px 0; font-size:21px; font-weight:700; color:#ff0000;\">注意：{html.escape(ticket.note).replace(chr(10), '<br>')}</p>"
        )
    sections.append("</div></body></html>")
    return "\n".join(sections)


def build_dispatch_body_text(result: DispatchParseResult, arrival_hour: str, truck_plate: str) -> str:
    deadline_text = display_arrival_deadline(arrival_hour)
    lines = [
        "Dear Kinki",
        "",
        f"请查收附件的交仓文件和装箱单，预计{deadline_text}前到仓库，卸货车牌 {truck_plate}，",
        "到仓后卸货请注意，有破损请第一时间通知，",
        "另外请注意交仓要求和时间，谢谢。",
        "（注意伟创力的发票不可拿去交仓，装箱单发票仅供仓库核对货）",
        "",
    ]
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"]
    for idx, ticket in enumerate(result.tickets, start=1):
        label = numerals[idx - 1] if idx - 1 < len(numerals) else str(idx)
        entry_lines = [
            f"{label}：{build_dispatch_ticket_title(ticket)}交{ticket.warehouse_code}仓：{ticket.address}",
        ]
        entry_lines.extend(
            [
                f"注意：{ticket.note}",
                "----------------",
            ]
        )
        lines.extend(entry_lines)
    return "\r\n".join(lines)


def add_file_attachment(message: EmailMessage, path: Path, filename: str) -> None:
    content = path.read_bytes()
    guessed_type, _ = mimetypes.guess_type(filename)
    maintype, subtype = (guessed_type or "application/octet-stream").split("/", 1)
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)


def generate_dispatch_eml(
    result: DispatchParseResult,
    output_path: Path,
    *,
    tracking_no: str,
    arrival_day: str,
    arrival_hour: str,
    truck_plate: str,
    to_email: str,
    cc_email: str,
    from_email: str,
) -> str:
    save_dispatch_settings(to_email=to_email, cc_email=cc_email, from_email=from_email)
    total_pallets = sum((ticket.pallets for ticket in result.tickets), Decimal("0"))
    subject = build_dispatch_subject(tracking_no, total_pallets, arrival_day, arrival_hour)
    image_cids = {
        ticket.index: make_msgid(domain="dispatch.local")[1:-1]
        for ticket in result.tickets
        if (getattr(ticket, "email_image_path", None) or ticket.table_image_path)
    }
    message = EmailMessage(policy=policy.SMTP)
    message["Subject"] = subject
    if from_email.strip():
        message["From"] = from_email.strip()
    if to_email.strip():
        message["To"] = to_email.strip()
    if cc_email.strip():
        message["Cc"] = cc_email.strip()
    message.set_content(build_dispatch_body_text(result, arrival_hour, truck_plate))
    message.add_alternative(build_dispatch_body_html(result, arrival_hour, truck_plate, image_cids), subtype="html")
    html_part = message.get_payload()[-1]
    for ticket in result.tickets:
        cid = image_cids.get(ticket.index)
        image_path = getattr(ticket, "email_image_path", None) or ticket.table_image_path
        if cid and image_path and image_path.exists():
            html_part.add_related(image_path.read_bytes(), maintype="image", subtype="png", cid=f"<{cid}>", disposition="inline")

    if result.master:
        add_file_attachment(message, result.master.stored_path, result.master.original_name)
    used_names: set[str] = set()
    for ticket in result.tickets:
        if ticket.dqth:
            name = unique_filename(ticket.dqth.final_name, used_names)
            add_file_attachment(message, ticket.dqth.attachment.stored_path, name)
        if ticket.so:
            name = unique_filename(ticket.so.final_name, used_names)
            add_file_attachment(message, ticket.so.attachment.stored_path, name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes())
    return subject


from app.modules.dispatch_mail.rules.classify import classify_attachments, looks_like_tan_master_attachment
from app.modules.dispatch_mail.rules.match import content_match_score, extract_match_tokens, match_dqths, score_so_match
from app.modules.dispatch_mail.rules.naming import (
    apply_attachment_names,
    build_dispatch_attachment_name,
    pick_final_attachment_name,
    unique_filename,
)
