from __future__ import annotations

import html
import json
import mimetypes
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.parser import BytesParser
from email import policy
from email.policy import SMTP
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.core.db import connect, run_migrations
from app_paths import RUNTIME_DIR

DB_PATH = RUNTIME_DIR / "ufo_mail.db"
SIGNATURE_DIR = RUNTIME_DIR / "ufo_signature"

DEFAULT_ISSUES = [
    (
        "外箱没有标签",
        "Carton without label",
        "The carton was received without any external label. Please confirm the cargo information and provide further instruction.",
    ),
    (
        "外箱标签没有 Flex PO",
        "Carton label missing Flex PO",
        "The carton label is missing the Flex PO information. Please help confirm the correct Flex PO.",
    ),
    (
        "外箱标签没有 Flex PN",
        "Carton label missing Flex PN",
        "The carton label is missing the Flex PN information. Please help confirm the correct Flex PN.",
    ),
    (
        "外箱标签没有 COO",
        "Carton label missing COO",
        "The carton label is missing COO information. Please help confirm the country of origin.",
    ),
    (
        "货物文件没有 Flex PO",
        "Documents missing Flex PO",
        "The cargo documents are missing the Flex PO information. Please help confirm the correct Flex PO.",
    ),
    (
        "货物文件没有 Flex PN",
        "Documents missing Flex PN",
        "The cargo documents are missing the Flex PN information. Please help confirm the correct Flex PN.",
    ),
    (
        "货物包装过高",
        "Over-height packing",
        "The cargo packing is over-height. Please confirm whether it can be accepted or if repacking is required.",
    ),
    (
        "货物箱数不可数",
        "Carton quantity cannot be counted",
        "The carton quantity cannot be counted accurately upon receipt. Please confirm the correct carton quantity.",
    ),
    (
        "货物没有文件",
        "Cargo without documents",
        "The cargo was received without documents. Please provide the required documents for handling.",
    ),
    (
        "货物包装扁箱",
        "Flattened cartons",
        "Some cartons were received in flattened condition. Please review the attached photos and advise.",
    ),
    (
        "货物包装破损",
        "Damaged packing",
        "Some cargo packing was received damaged. Please review the attached photos and advise.",
    ),
]


@dataclass
class UfoIssueInput:
    short_cn: str
    short_en: str
    detail_en: str


@dataclass
class UfoAttachment:
    path: Path
    filename: str


@dataclass
class UfoMailInput:
    ufo_no: str
    to_email: str
    cc_email: str
    from_email: str
    issue_ids: Sequence[int]
    attachments: Sequence[UfoAttachment]


def get_connection() -> sqlite3.Connection:
    return connect(DB_PATH)


def migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ufo_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            short_cn TEXT NOT NULL,
            short_en TEXT NOT NULL,
            detail_en TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ufo_issues_active ON ufo_issues(is_active);

        CREATE TABLE IF NOT EXISTS ufo_mail_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


MIGRATIONS = {
    1: migration_001_initial_schema,
}


def init_ufo_db() -> None:
    with get_connection() as conn:
        run_migrations(conn, MIGRATIONS)
        count = conn.execute("SELECT COUNT(*) FROM ufo_issues").fetchone()[0]
        if count == 0:
            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany(
                """
                INSERT INTO ufo_issues (short_cn, short_en, detail_en, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                [(short_cn, short_en, detail_en, now, now) for short_cn, short_en, detail_en in DEFAULT_ISSUES],
            )


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def get_ufo_mail_settings() -> dict[str, str]:
    init_ufo_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT setting_key, setting_value FROM ufo_mail_settings").fetchall()
    settings = {row["setting_key"]: row["setting_value"] for row in rows}
    return {
        "to_email": settings.get("to_email", ""),
        "cc_email": settings.get("cc_email", ""),
        "from_email": settings.get("from_email", ""),
    }


def save_ufo_mail_settings(*, to_email: str, cc_email: str, from_email: str) -> None:
    init_ufo_db()
    now = datetime.now().isoformat(timespec="seconds")
    values = {
        "to_email": clean_text(to_email),
        "cc_email": clean_text(cc_email),
        "from_email": clean_text(from_email),
    }
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO ufo_mail_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            [(key, value, now) for key, value in values.items()],
        )


def get_ufo_signature_settings() -> dict[str, Any]:
    init_ufo_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT setting_key, setting_value FROM ufo_mail_settings").fetchall()
    settings = {row["setting_key"]: row["setting_value"] for row in rows}
    try:
        assets = json.loads(settings.get("signature_assets", "[]"))
    except json.JSONDecodeError:
        assets = []
    return {
        "enabled": settings.get("signature_enabled", "0") == "1",
        "html": settings.get("signature_html", ""),
        "plain": settings.get("signature_plain", ""),
        "assets": assets,
        "source_name": settings.get("signature_source_name", ""),
        "updated_at": settings.get("signature_updated_at", ""),
    }


def save_ufo_signature_settings(
    *,
    enabled: bool,
    signature_html: str,
    signature_plain: str,
    assets: Sequence[dict[str, str]],
    source_name: str,
) -> None:
    init_ufo_db()
    now = datetime.now().isoformat(timespec="seconds")
    values = {
        "signature_enabled": "1" if enabled else "0",
        "signature_html": signature_html,
        "signature_plain": signature_plain,
        "signature_assets": json.dumps(list(assets), ensure_ascii=True),
        "signature_source_name": clean_text(source_name),
        "signature_updated_at": now,
    }
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO ufo_mail_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            [(key, value, now) for key, value in values.items()],
        )


def set_ufo_signature_enabled(enabled: bool) -> None:
    settings = get_ufo_signature_settings()
    save_ufo_signature_settings(
        enabled=enabled,
        signature_html=settings["html"],
        signature_plain=settings["plain"],
        assets=settings["assets"],
        source_name=settings["source_name"],
    )


def list_ufo_issues(include_inactive: bool = False) -> list[dict[str, Any]]:
    init_ufo_db()
    query = "SELECT * FROM ufo_issues"
    params: list[Any] = []
    if not include_inactive:
        query += " WHERE is_active = ?"
        params.append(1)
    query += " ORDER BY is_active DESC, short_cn COLLATE NOCASE, id"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def create_ufo_issue(issue: UfoIssueInput) -> None:
    short_cn = clean_text(issue.short_cn)
    short_en = clean_text(issue.short_en)
    detail_en = clean_text(issue.detail_en)
    if not short_cn or not short_en or not detail_en:
        raise ValueError("问题的中文简述、英文简述和英文具体描述都不能为空。")
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ufo_issues (short_cn, short_en, detail_en, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (short_cn, short_en, detail_en, now, now),
        )


def update_ufo_issue(issue_id: int, issue: UfoIssueInput) -> None:
    short_cn = clean_text(issue.short_cn)
    short_en = clean_text(issue.short_en)
    detail_en = clean_text(issue.detail_en)
    if not short_cn or not short_en or not detail_en:
        raise ValueError("问题的中文简述、英文简述和英文具体描述都不能为空。")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE ufo_issues
            SET short_cn = ?, short_en = ?, detail_en = ?, updated_at = ?
            WHERE id = ?
            """,
            (short_cn, short_en, detail_en, datetime.now().isoformat(timespec="seconds"), issue_id),
        )


def set_ufo_issue_active(issue_id: int, is_active: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE ufo_issues
            SET is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if is_active else 0, datetime.now().isoformat(timespec="seconds"), issue_id),
        )


def get_ufo_issues_by_ids(issue_ids: Iterable[int]) -> list[dict[str, Any]]:
    ids = [int(issue_id) for issue_id in issue_ids]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM ufo_issues WHERE id IN ({placeholders}) AND is_active = 1",
            ids,
        ).fetchall()
    by_id = {row["id"]: dict(row) for row in rows}
    return [by_id[issue_id] for issue_id in ids if issue_id in by_id]


def build_ufo_subject(ufo_no: str, issues: Sequence[dict[str, Any]]) -> str:
    issue_titles = [clean_text(issue.get("short_en")) for issue in issues if clean_text(issue.get("short_en"))]
    prefix = clean_text(ufo_no) or "UFO"
    if not issue_titles:
        return prefix
    return f"{prefix}, {', '.join(issue_titles)}"


def build_ufo_body(ufo_no: str, issues: Sequence[dict[str, Any]]) -> str:
    lines = [
        "Dear Flex Team,",
        "",
        f"Please kindly note the following issue(s) for {clean_text(ufo_no) or 'the received cargo'}:",
        "",
    ]
    for index, issue in enumerate(issues, start=1):
        lines.append(f"{index}. {clean_text(issue.get('detail_en'))}")
    lines.extend(
        [
            "",
            "Please refer to the attached UFO file and photos for details.",
            "",
            "Best regards,",
        ]
    )
    return "\r\n".join(lines)


def build_ufo_body_html(ufo_no: str, issues: Sequence[dict[str, Any]]) -> str:
    issue_items = "\n".join(
        f"<li>{html.escape(clean_text(issue.get('detail_en')))}</li>"
        for issue in issues
    )
    target = html.escape(clean_text(ufo_no) or "the received cargo")
    return f"""\
<div style="font-family: Arial, 'Microsoft YaHei', sans-serif; font-size: 14px; color: #1f2933; line-height: 1.6;">
  <p>Dear Flex Team,</p>
  <p>Please kindly note the following issue(s) for {target}:</p>
  <ol>
    {issue_items}
  </ol>
  <p>Please refer to the attached UFO file and photos for details.</p>
</div>
"""


def strip_forwarded_history(signature_html: str) -> str:
    return re.split(r"<blockquote\b", signature_html, maxsplit=1, flags=re.IGNORECASE)[0]


def find_signature_fragment_start(html_text: str, marker_start: int) -> int:
    """Back up from matched text to the open HTML wrapper that carries its style."""
    tag_pattern = re.compile(r"<(/?)([a-zA-Z0-9]+)\b[^>]*?>", flags=re.IGNORECASE)
    stack: list[tuple[str, int]] = []
    tracked_tags = {"div", "p", "span", "font", "b", "strong", "table", "tbody", "tr", "td"}
    for match in tag_pattern.finditer(html_text[:marker_start]):
        tag = match.group(2).lower()
        if tag not in tracked_tags:
            continue
        is_close = bool(match.group(1))
        is_self_closing = match.group(0).rstrip().endswith("/>")
        if is_close:
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0] == tag:
                    del stack[index:]
                    break
        elif not is_self_closing:
            stack.append((tag, match.start()))

    nearby_open_tags = [
        (tag, position)
        for tag, position in stack
        if marker_start - position <= 1600 and tag not in {"html", "body"}
    ]
    if not nearby_open_tags:
        block_start = max(html_text.rfind("<p", 0, marker_start), html_text.rfind("<div", 0, marker_start))
        return block_start if block_start >= 0 else marker_start

    preferred_tags = {"div", "p", "table"}
    preferred = [(tag, position) for tag, position in nearby_open_tags if tag in preferred_tags]
    if preferred:
        return preferred[0][1]
    return nearby_open_tags[0][1]


def extract_signature_html(full_html: str, marker: str) -> str:
    cleaned = strip_forwarded_history(full_html)
    marker_text = clean_text(marker) or "Thanks & Best regards"
    marker_pattern = re.escape(marker_text).replace(r"\&", r"(?:&|&amp;)")
    marker_match = re.search(marker_pattern, cleaned, flags=re.IGNORECASE)
    if marker_match:
        fragment_start = find_signature_fragment_start(cleaned, marker_match.start())
        return cleaned[fragment_start:].strip()
    img_match = re.search(r"<img\b", cleaned, flags=re.IGNORECASE)
    if img_match:
        return cleaned[img_match.start():].strip()
    hr_match = re.search(r"<hr\b", cleaned, flags=re.IGNORECASE)
    if hr_match:
        return cleaned[hr_match.start():].strip()
    return cleaned.strip()


def html_to_plain_text(fragment: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def import_ufo_signature_from_eml(eml_path: Path, *, source_name: str, marker: str = "Thanks & Best regards") -> dict[str, Any]:
    msg = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    html_part = None
    related_assets: dict[str, Any] = {}
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/html" and html_part is None:
            html_part = part
        cid = part.get("content-id")
        if cid and ctype.startswith("image/"):
            related_assets[cid.strip("<>")] = part
    if html_part is None:
        raise ValueError("这封 eml 中没有找到 HTML 正文，无法提取带图片的签名。")

    signature_html = extract_signature_html(html_part.get_content(), marker)
    if not signature_html:
        raise ValueError("没有提取到签名内容，请换一个签名开始标记再试。")

    SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, str]] = []
    used_cids = set(re.findall(r"cid:([^'\" >]+)", signature_html, flags=re.IGNORECASE))
    for cid in used_cids:
        part = related_assets.get(cid)
        if part is None:
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        ctype = part.get_content_type()
        extension = mimetypes.guess_extension(ctype) or ".bin"
        stored_name = f"{uuid.uuid4().hex}{extension}"
        stored_path = SIGNATURE_DIR / stored_name
        stored_path.write_bytes(payload)
        assets.append(
            {
                "cid": cid,
                "path": str(stored_path),
                "filename": part.get_filename() or stored_name,
                "content_type": ctype,
            }
        )

    signature_plain = html_to_plain_text(signature_html)
    save_ufo_signature_settings(
        enabled=True,
        signature_html=signature_html,
        signature_plain=signature_plain,
        assets=assets,
        source_name=source_name,
    )
    return get_ufo_signature_settings()


def generate_ufo_eml(mail_input: UfoMailInput, output_path: Path) -> str:
    issues = get_ufo_issues_by_ids(mail_input.issue_ids)
    if not issues:
        raise ValueError("请至少勾选一个问题。")

    subject = build_ufo_subject(mail_input.ufo_no, issues)
    body = build_ufo_body(mail_input.ufo_no, issues)
    body_html = build_ufo_body_html(mail_input.ufo_no, issues)
    signature = get_ufo_signature_settings()

    message = EmailMessage(policy=SMTP)
    message["Subject"] = subject
    if clean_text(mail_input.from_email):
        message["From"] = clean_text(mail_input.from_email)
    if clean_text(mail_input.to_email):
        message["To"] = clean_text(mail_input.to_email)
    if clean_text(mail_input.cc_email):
        message["Cc"] = clean_text(mail_input.cc_email)
    message.set_content(body)
    if signature["enabled"] and signature["html"]:
        message.set_content(f"{body}\r\n\r\n{signature['plain']}")
        message.add_alternative(
            f"{body_html}<br>{signature['html']}",
            subtype="html",
        )
        html_part = message.get_payload()[-1]
        for asset in signature["assets"]:
            asset_path = Path(asset.get("path", ""))
            if not asset_path.exists():
                continue
            content_type = asset.get("content_type") or "application/octet-stream"
            maintype, subtype = content_type.split("/", 1)
            cid = asset.get("cid") or f"{uuid.uuid4().hex}@ufo-signature"
            html_part.add_related(
                asset_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                cid=f"<{cid}>",
                disposition="inline",
            )

    for attachment in mail_input.attachments:
        content = attachment.path.read_bytes()
        guessed_type, _ = mimetypes.guess_type(attachment.filename)
        maintype, subtype = (guessed_type or "application/octet-stream").split("/", 1)
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=attachment.filename)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes())
    return subject


from app.modules.ufo_mail.rules import detect_ufo_no
