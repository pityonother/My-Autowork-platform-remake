from __future__ import annotations

import json
import mimetypes
import re
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import make_msgid
from pathlib import Path
from typing import Any

from app_paths import RESOURCE_DIR, RUNTIME_DIR


SIL_FUCA_WAREHOUSE_TEMPLATE_DIR = RUNTIME_DIR / "booking_sil_fuca_warehouse_template"
SIL_FUCA_WAREHOUSE_TEMPLATE_JSON = SIL_FUCA_WAREHOUSE_TEMPLATE_DIR / "template.json"
DEFAULT_SIL_FUCA_WAREHOUSE_TEMPLATE_DIR = (
    RESOURCE_DIR / "app" / "modules" / "booking" / "default_warehouse_template"
)
DEFAULT_SIL_FUCA_WAREHOUSE_TEMPLATE_JSON = DEFAULT_SIL_FUCA_WAREHOUSE_TEMPLATE_DIR / "template.json"


def safe_attachment_name(filename: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\r\n]+', "_", filename).strip()
    return clean or f"attachment_{uuid.uuid4().hex[:8]}"


def extract_sil_warehouse_no(path: Path) -> str:
    match = re.search(r"(SIL\d+)", path.name, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    raise ValueError("未能从入仓文件名中识别入仓号，文件名需包含类似 SIL26040490 的编号。")


def unique_attachment_name(filename: str, used_names: set[str]) -> str:
    safe = safe_attachment_name(filename)
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


def add_booking_attachment(message: EmailMessage, file_path: Path, filename: str) -> None:
    content = file_path.read_bytes()
    guessed_type, _ = mimetypes.guess_type(filename)
    maintype, subtype = (guessed_type or "application/octet-stream").split("/", 1)
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)


def html_to_plain_text(fragment: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return text


def replace_mail_template_values(content: str, mawb_no: str, warehouse_no: str) -> str:
    updated = content
    marker_index = updated.upper().find("MAWB#")
    if marker_index >= 0:
        number_match = re.search(r"\d{10,}", updated[marker_index:])
        if number_match:
            start = marker_index + number_match.start()
            end = marker_index + number_match.end()
            updated = f"{updated[:start]}{mawb_no}{updated[end:]}"
    updated = re.sub(r"(?i)(MAWB#(?:&nbsp;|\s)*)[A-Z0-9]+", lambda match: f"{match.group(1)}{mawb_no}", updated)
    updated = re.sub(r"(?i)SIL\d+", warehouse_no, updated)
    return updated


def remove_obsolete_sil_holiday_notice(content: str) -> str:
    updated = re.sub(
        r"(?is)<p\b[^>]*>.*?香港仓：5月1日(?:&amp;|&)5月5日（全日休息）.*?</p>",
        "",
        content,
    )
    return re.sub(
        r"(?m)^[^\S\r\n]*香港仓：5月1日&5月5日（全日休息）[^\S\r\n]*(?:\r?\n)?",
        "",
        updated,
    )


def save_sil_fuca_warehouse_template_from_eml(eml_path: Path) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    html_part = message.get_body(preferencelist=("html",))
    plain_part = message.get_body(preferencelist=("plain",))
    html_content = html_part.get_content() if html_part else ""
    plain_content = plain_part.get_content() if plain_part else html_to_plain_text(html_content)
    SIL_FUCA_WAREHOUSE_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, str]] = []
    for part in message.walk():
        cid = (part.get("Content-ID") or "").strip()
        if not cid or part.is_multipart():
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        clean_cid = cid.strip("<>")
        ext = mimetypes.guess_extension(part.get_content_type() or "") or ".bin"
        asset_name = f"{uuid.uuid4().hex}{ext}"
        asset_path = SIL_FUCA_WAREHOUSE_TEMPLATE_DIR / asset_name
        asset_path.write_bytes(payload)
        assets.append(
            {
                "cid": clean_cid,
                "path": str(asset_path),
                "content_type": part.get_content_type() or "application/octet-stream",
            }
        )
    data = {"html": html_content, "plain": plain_content, "assets": assets}
    SIL_FUCA_WAREHOUSE_TEMPLATE_JSON.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _empty_template() -> dict[str, Any]:
    return {"html": "", "plain": "", "assets": [], "_template_base_dir": ""}


def _load_template_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_template_base_dir"] = str(path.parent)
    return data


def load_sil_fuca_warehouse_template() -> dict[str, Any]:
    for template_path in (SIL_FUCA_WAREHOUSE_TEMPLATE_JSON, DEFAULT_SIL_FUCA_WAREHOUSE_TEMPLATE_JSON):
        if not template_path.exists():
            continue
        try:
            return _load_template_json(template_path)
        except Exception:
            continue
    return _empty_template()


def resolve_template_asset_path(asset: dict[str, Any], template_base_dir: Path) -> Path | None:
    raw_path = str(asset.get("path") or "").strip()
    if not raw_path:
        return None
    asset_path = Path(raw_path)
    candidates = [asset_path] if asset_path.is_absolute() else [template_base_dir / asset_path]
    if asset_path.name:
        candidates.append(template_base_dir / asset_path.name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_sil_fuca_warehouse_mail_subject(mawb_no: str, warehouse_no: str) -> str:
    return f"啟益 富昌 - MAWB# {mawb_no} - 入倉號{warehouse_no}"


def build_sil_fuca_warehouse_mail_body(mawb_no: str, warehouse_no: str) -> str:
    subject_line = build_sil_fuca_warehouse_mail_subject(mawb_no, warehouse_no)
    return (
        "\r\n"
        f"{subject_line}\r\n"
        "\r\n"
        "\r\n"
        "\r\n"
        "香港仓库上下班时间：上午09:00-12:00（星期一到星期六） 下午13:30-17:00（星期一至星期五）\r\n"
        "注意东莞货物入仓要求：E33K和1339采购单别不同，货物，装箱单发票及入仓单要分开做\r\n"
        "1.从1/26号起，供应商删除BOOKING导入，仅保留\"MES导入\"一种途径来生成入仓单\r\n"
        "2.净、毛重不能为0，如果有多个料号装在一个纸箱，请按实际拆分净、毛重;如无法拆分实际，也可以取平均值(但这一箱的总重需与实际总重相符合)\r\n"
        "3、通过MES导入获取的资料，除了净、毛重可以修改，余下的部分不支持修改，如需忝加、修改、删除)，只能先去启益MES更新资料后，再通过MES导入全量更新。\r\n"
        "*******************************************************\r\n"
        "Thanks & Best regards\r\n"
        "  雨欣/kiki\r\n"
        "暢通全球物流有限公司\r\n"
        "Smooth Global Logistics Company Limited\r\n"
        "ADDRESS:FLAT/RM A 13/F WING CHEUNG IND BLDG 58-70 KWAI CHEONG ROAD KWAI CHUNG NT\r\n"
        "WH:LOT 1970,1971,1973,1975,1978 & 1979 RP IN DD 125, PING HA ROAD, YUEN LONG, N.T. HONG KONG.\r\n"
        "Mail：sale@hkctwl.net\r\n"
        "Tel: +852 5804 4169/0755-8221 9763\r\n"
        "MP:+86 136 0746 2150\r\n"
        "深圳市易斯特國際貨運代理有限公司\r\n"
        "深圳市龍華區民治大道港深國際中心8樓B823\r\n"
    )


def build_reply_subject(original_subject: str, fallback: str = "Flex-Texas booking") -> str:
    subject = str(original_subject or "").strip() or fallback
    if re.match(r"(?i)^\s*(re|答复|回复)\s*:", subject):
        return subject
    return f"Re: {subject}"


def build_flex_texas_booking_reply_body(preview: Any) -> str:
    lines = [
        "Hi,",
        "",
        "Please find attached the completed TMS warehouse-entry PDF.",
    ]
    if getattr(preview, "mawb_no", ""):
        lines.append(f"MAWB: {preview.mawb_no}")
    if getattr(preview, "hbl_no", ""):
        lines.append(f"HAWB: {preview.hbl_no}")
    lines.extend(["", "Thanks & Best regards"])
    return "\r\n".join(lines)


def _references_header(original_message_id: str, original_references: str) -> str:
    message_id = original_message_id.strip()
    references = original_references.strip()
    if not message_id:
        return references
    if message_id in references:
        return references
    return " ".join(item for item in (references, message_id) if item)


def generate_flex_texas_booking_reply_eml(
    *,
    preview: Any,
    customer_eml_path: Path,
    tms_pdf_path: Path,
    output_path: Path,
    body_text: str = "",
    from_email: str = '"op19@hkctwl.net" <op19@hkctwl.net>',
) -> str:
    if getattr(preview, "supplier", "") != "FLEX-TEXAS":
        raise ValueError("当前只支持 FLEX-TEXAS 生成原邮件回复 eml。")
    if not customer_eml_path.exists():
        raise FileNotFoundError("未找到客户原始 eml，无法生成原邮件回复。")
    if not tms_pdf_path.exists():
        raise FileNotFoundError("未找到 TMS 导出的 PDF 文件。")

    original = BytesParser(policy=policy.default).parsebytes(customer_eml_path.read_bytes())
    original_subject = str(original.get("subject") or "")
    reply_to = str(original.get("reply-to") or original.get("from") or "").strip()
    if not reply_to:
        raise ValueError("客户原始 eml 缺少 From / Reply-To，无法确定回复收件人。")

    original_message_id = str(original.get("message-id") or "").strip()
    original_references = str(original.get("references") or "").strip()
    subject = build_reply_subject(original_subject)

    message = EmailMessage(policy=policy.SMTP)
    message["X-Unsent"] = "1"
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="booking.local")
    if from_email.strip():
        message["From"] = from_email.strip()
    message["To"] = reply_to
    if original_message_id:
        message["In-Reply-To"] = original_message_id
    references = _references_header(original_message_id, original_references)
    if references:
        message["References"] = references
    message.set_content(body_text.strip() or build_flex_texas_booking_reply_body(preview))
    add_booking_attachment(message, tms_pdf_path, tms_pdf_path.name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes())
    return subject


def generate_sil_fuca_warehouse_eml(
    *,
    preview: Any,
    customer_eml_path: Path,
    warehouse_file_path: Path,
    output_path: Path,
) -> str:
    from app.modules.booking.legacy_adapter import extract_all_booking_attachments_from_eml, extract_mawb_no

    if preview.supplier != "SIL-FUCA":
        raise ValueError("当前只有 SIL-FUCA 支持自动生成入仓邮件。")
    if not customer_eml_path.exists():
        raise FileNotFoundError("未找到客户原始邮件，无法附带原始附件生成入仓邮件。")

    mawb_no = preview.mawb_no or extract_mawb_no(preview.email_subject)
    if not mawb_no:
        raise ValueError("未能从客户原始邮件标题识别 MAWB#。")
    warehouse_no = extract_sil_warehouse_no(warehouse_file_path)
    subject = build_sil_fuca_warehouse_mail_subject(mawb_no, warehouse_no)
    attachments_dir = RUNTIME_DIR / "booking_warehouse_attachments" / preview.session_id
    source_attachments, _ = extract_all_booking_attachments_from_eml(customer_eml_path, attachments_dir)

    message = EmailMessage(policy=policy.SMTP)
    message["Subject"] = subject
    message["From"] = '"op19@hkctwl.net" <op19@hkctwl.net>'
    message["To"] = "hong <hong@hkctwl.net>, lydia <lydia@hkctwl.net>, mavis <mavis@hkctwl.net>, sanford <sanford@hkctwl.net>, warehouse <warehouse@smooth-global.com>"
    template = load_sil_fuca_warehouse_template()
    plain_body = remove_obsolete_sil_holiday_notice(
        replace_mail_template_values(template.get("plain") or "", mawb_no, warehouse_no)
    ).strip()
    if not plain_body:
        plain_body = remove_obsolete_sil_holiday_notice(build_sil_fuca_warehouse_mail_body(mawb_no, warehouse_no))
    message.set_content(plain_body)
    html_body = remove_obsolete_sil_holiday_notice(
        replace_mail_template_values(template.get("html") or "", mawb_no, warehouse_no)
    ).strip()
    if html_body:
        message.add_alternative(html_body, subtype="html")
        html_part = message.get_payload()[-1]
        template_base_dir = Path(str(template.get("_template_base_dir") or ""))
        for asset in template.get("assets", []):
            asset_path = resolve_template_asset_path(asset, template_base_dir)
            if asset_path is None:
                continue
            content_type = str(asset.get("content_type") or "application/octet-stream")
            maintype, subtype = content_type.split("/", 1)
            cid = str(asset.get("cid") or "").strip()
            if not cid:
                continue
            html_part.add_related(
                asset_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                cid=f"<{cid}>",
                disposition="inline",
            )

    used_names: set[str] = set()
    add_booking_attachment(message, warehouse_file_path, unique_attachment_name(warehouse_file_path.name, used_names))
    for attachment in source_attachments:
        add_booking_attachment(message, attachment.path, unique_attachment_name(attachment.filename, used_names))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes())
    return subject


__all__ = [
    "build_sil_fuca_warehouse_mail_body",
    "build_sil_fuca_warehouse_mail_subject",
    "build_flex_texas_booking_reply_body",
    "build_reply_subject",
    "extract_sil_warehouse_no",
    "generate_flex_texas_booking_reply_eml",
    "generate_sil_fuca_warehouse_eml",
    "load_sil_fuca_warehouse_template",
    "replace_mail_template_values",
    "save_sil_fuca_warehouse_template_from_eml",
]
