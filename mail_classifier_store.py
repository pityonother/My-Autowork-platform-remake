from __future__ import annotations

import base64
import ctypes
import html
import imaplib
import json
import re
import sqlite3
import sys
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.core.db import connect, run_migrations
from app_paths import RUNTIME_DIR


DB_PATH = RUNTIME_DIR / "mail_classifier.db"

DEFAULT_IMAP_HOST = "imap.qiye.163.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SYNC_DAYS = 30
DEFAULT_MAILBOX = "INBOX"
MAX_SYNC_MESSAGES = 200

BUSINESS_LABELS = [
    ("export_order", "出口订单"),
    ("export_customs", "出口清关"),
    ("advance_payment", "代垫"),
    ("invoice", "发票"),
    ("customer_docs", "客户资料"),
    ("exception", "异常"),
    ("other", "其他"),
]
BUSINESS_LABEL_MAP = dict(BUSINESS_LABELS)

STATUS_LABELS = [
    ("pending", "待处理"),
    ("needs_review", "待确认"),
    ("completed", "已处理"),
    ("ignored", "忽略"),
]
STATUS_LABEL_MAP = dict(STATUS_LABELS)

RISK_LABELS = [
    ("has_attachment", "有附件"),
    ("missing_attachment", "疑似缺附件"),
    ("forwarded", "疑似转发"),
    ("history_thread", "疑似历史邮件"),
    ("rule_conflict", "规则冲突"),
    ("low_confidence", "低置信度"),
]
RISK_LABEL_MAP = dict(RISK_LABELS)

class SecretStorageError(RuntimeError):
    pass


class DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


@dataclass
class MailSyncResult:
    scanned: int
    imported: int
    updated: int
    skipped: int
    mailbox: str


def get_connection() -> sqlite3.Connection:
    return connect(DB_PATH)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mail_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_email TEXT NOT NULL UNIQUE,
            imap_host TEXT NOT NULL,
            imap_port INTEGER NOT NULL,
            use_ssl INTEGER NOT NULL DEFAULT 1,
            password_blob TEXT,
            default_mailbox TEXT NOT NULL,
            sync_days INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mail_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            account_email TEXT NOT NULL,
            mailbox TEXT NOT NULL,
            uid TEXT NOT NULL,
            message_id TEXT,
            from_name TEXT,
            from_addr TEXT,
            to_addrs TEXT,
            subject TEXT,
            received_at TEXT,
            body_preview TEXT,
            attachment_names TEXT NOT NULL DEFAULT '[]',
            raw_flags TEXT,
            business_labels TEXT NOT NULL DEFAULT '[]',
            status_label TEXT NOT NULL DEFAULT 'needs_review',
            risk_labels TEXT NOT NULL DEFAULT '[]',
            confidence INTEGER NOT NULL DEFAULT 0,
            matched_rules TEXT NOT NULL DEFAULT '[]',
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES mail_accounts(id),
            UNIQUE(account_email, mailbox, uid)
        );

        CREATE INDEX IF NOT EXISTS idx_mail_messages_account ON mail_messages(account_email);
        CREATE INDEX IF NOT EXISTS idx_mail_messages_received ON mail_messages(received_at);
        CREATE INDEX IF NOT EXISTS idx_mail_messages_status ON mail_messages(status_label);

        CREATE TABLE IF NOT EXISTS mail_classification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            previous_business_labels TEXT,
            previous_status_label TEXT,
            previous_risk_labels TEXT,
            new_business_labels TEXT NOT NULL,
            new_status_label TEXT NOT NULL,
            new_risk_labels TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES mail_messages(id)
        );
        """
    )


MIGRATIONS = {
    1: migration_001_initial_schema,
}


def init_mail_classifier_db() -> None:
    with get_connection() as conn:
        run_migrations(conn, MIGRATIONS)


def _blob_from_bytes(data: bytes) -> tuple[DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    if sys.platform != "win32":
        raise SecretStorageError("当前版本只支持在 Windows 上保存邮箱密码。")
    data = secret.encode("utf-8")
    data_blob, _data_buffer = _blob_from_bytes(data)
    out_blob = DataBlob()
    description = "mail_classifier_password"
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(data_blob),
        description,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise SecretStorageError("无法使用 Windows DPAPI 加密邮箱密码。")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return "dpapi:" + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(blob_text: str | None) -> str:
    if not blob_text:
        return ""
    if not blob_text.startswith("dpapi:"):
        raise SecretStorageError("邮箱密码存储格式不受支持。")
    if sys.platform != "win32":
        raise SecretStorageError("当前版本只支持在 Windows 上读取已保存的邮箱密码。")
    encrypted = base64.b64decode(blob_text.split(":", 1)[1])
    data_blob, _data_buffer = _blob_from_bytes(encrypted)
    out_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(data_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise SecretStorageError("无法使用 Windows DPAPI 解密邮箱密码。")
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return raw.decode("utf-8")


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def decode_mime_text(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def encode_imap_mailbox_name(mailbox: str) -> str:
    text = clean_text(mailbox) or DEFAULT_MAILBOX
    result: list[str] = []
    buffer: list[str] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        raw = "".join(buffer).encode("utf-16-be")
        encoded = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        result.append(f"&{encoded}-")
        buffer.clear()

    for char in text:
        code = ord(char)
        if 0x20 <= code <= 0x7E:
            flush_buffer()
            result.append("&-" if char == "&" else char)
        else:
            buffer.append(char)
    flush_buffer()
    return "".join(result)


def strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(clean_text(text))


def body_preview_from_bytes(data: bytes, limit: int = 600) -> str:
    if not data:
        return ""
    message = BytesParser(policy=policy.default).parsebytes(data)
    chunks: list[str] = []
    if message.is_multipart():
        parts = message.walk()
    else:
        parts = [message]
    for part in parts:
        content_type = part.get_content_type()
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            payload = part.get_content()
        except Exception:  # noqa: BLE001
            payload = ""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="ignore")
        if content_type == "text/html":
            payload = strip_html(str(payload))
        payload = clean_text(payload)
        if payload:
            chunks.append(payload)
        if sum(len(item) for item in chunks) >= limit:
            break
    return clean_text(" ".join(chunks))[:limit]


def extract_attachment_names_from_structure(structure_text: str) -> list[str]:
    names: list[str] = []
    for raw in re.findall(r'\b(?:FILENAME|NAME)\s+"((?:\\.|[^"])*)"', structure_text or "", flags=re.IGNORECASE):
        value = raw.replace('\\"', '"').replace("\\\\", "\\")
        decoded = decode_mime_text(value)
        if decoded and decoded not in names:
            names.append(decoded)
    return names


def parse_received_at(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:  # noqa: BLE001
        return clean_text(value)
    if parsed.tzinfo:
        parsed = parsed.astimezone()
    return parsed.replace(tzinfo=None).isoformat(timespec="seconds")


def parse_addresses(value: str | None) -> tuple[str, str]:
    addresses = getaddresses([value or ""])
    if not addresses:
        return "", ""
    name, addr = addresses[0]
    return decode_mime_text(name), addr


def save_mail_account_settings(
    *,
    account_email: str,
    imap_host: str,
    imap_port: int,
    password: str,
    default_mailbox: str,
    sync_days: int,
    use_ssl: bool = True,
) -> dict[str, Any]:
    init_mail_classifier_db()
    normalized_email = normalize_email(account_email)
    if not normalized_email:
        raise ValueError("请填写邮箱账号。")
    if not imap_host.strip():
        raise ValueError("请填写 IMAP 服务器。")
    normalized_mailbox = clean_text(default_mailbox) or DEFAULT_MAILBOX
    normalized_days = max(1, min(int(sync_days or DEFAULT_SYNC_DAYS), 365))
    now = now_text()
    with get_connection() as conn:
        current = conn.execute(
            "SELECT password_blob FROM mail_accounts WHERE account_email = ?",
            (normalized_email,),
        ).fetchone()
        password_blob = current["password_blob"] if current else ""
        if password:
            password_blob = protect_secret(password)
        if not password_blob:
            raise ValueError("首次保存邮箱配置时需要填写密码。")
        conn.execute(
            """
            INSERT INTO mail_accounts (
                account_email, imap_host, imap_port, use_ssl, password_blob,
                default_mailbox, sync_days, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_email) DO UPDATE SET
                imap_host = excluded.imap_host,
                imap_port = excluded.imap_port,
                use_ssl = excluded.use_ssl,
                password_blob = excluded.password_blob,
                default_mailbox = excluded.default_mailbox,
                sync_days = excluded.sync_days,
                updated_at = excluded.updated_at
            """,
            (
                normalized_email,
                imap_host.strip(),
                int(imap_port or DEFAULT_IMAP_PORT),
                1 if use_ssl else 0,
                password_blob,
                normalized_mailbox,
                normalized_days,
                now,
                now,
            ),
        )
    return get_mail_account(normalized_email) or {}


def get_mail_account(account_email: str) -> dict[str, Any] | None:
    init_mail_classifier_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_email, imap_host, imap_port, use_ssl,
                   CASE WHEN password_blob IS NULL OR password_blob = '' THEN 0 ELSE 1 END AS has_password,
                   default_mailbox, sync_days, created_at, updated_at
            FROM mail_accounts
            WHERE account_email = ?
            """,
            (normalize_email(account_email),),
        ).fetchone()
    return dict(row) if row else None


def list_mail_accounts() -> list[dict[str, Any]]:
    init_mail_classifier_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, account_email, imap_host, imap_port, use_ssl,
                   CASE WHEN password_blob IS NULL OR password_blob = '' THEN 0 ELSE 1 END AS has_password,
                   default_mailbox, sync_days, created_at, updated_at
            FROM mail_accounts
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_default_account_form() -> dict[str, Any]:
    accounts = list_mail_accounts()
    if accounts:
        return accounts[0]
    return {
        "account_email": "",
        "imap_host": DEFAULT_IMAP_HOST,
        "imap_port": DEFAULT_IMAP_PORT,
        "use_ssl": 1,
        "has_password": 0,
        "default_mailbox": DEFAULT_MAILBOX,
        "sync_days": DEFAULT_SYNC_DAYS,
    }


def _get_account_with_secret(account_email: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM mail_accounts WHERE account_email = ?",
            (normalize_email(account_email),),
        ).fetchone()
    if not row:
        raise ValueError("没有找到这个邮箱配置。")
    account = dict(row)
    account["password"] = unprotect_secret(account.get("password_blob"))
    if not account["password"]:
        raise ValueError("这个邮箱配置没有保存密码。")
    return account


def _imap_connect(account: dict[str, Any]) -> imaplib.IMAP4:
    host = account["imap_host"]
    port = int(account["imap_port"])
    if int(account.get("use_ssl", 1)):
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)
    mail.login(account["account_email"], account["password"])
    return mail


def _collect_imap_literals(data: Iterable[Any], marker: str | None = None) -> tuple[bytes, str]:
    payloads: list[bytes] = []
    meta_parts: list[str] = []
    for item in data:
        if isinstance(item, tuple):
            meta = item[0].decode("utf-8", errors="ignore") if isinstance(item[0], bytes) else str(item[0])
            meta_parts.append(meta)
            if marker is None or marker in meta.upper():
                payloads.append(item[1])
        elif isinstance(item, bytes):
            meta_parts.append(item.decode("utf-8", errors="ignore"))
    return b"\n".join(payloads), " ".join(meta_parts)


def _fetch_message_summary(mail: imaplib.IMAP4, uid: bytes) -> dict[str, Any]:
    status, data = mail.uid("fetch", uid, "(BODY.PEEK[HEADER] BODYSTRUCTURE FLAGS)")
    if status != "OK":
        raise RuntimeError(f"读取邮件头失败：UID {uid.decode(errors='ignore')}")
    header_bytes, structure_text = _collect_imap_literals(data, "BODY[HEADER]")
    status, body_data = mail.uid("fetch", uid, "(BODY.PEEK[TEXT]<0.12000>)")
    body_bytes = b""
    if status == "OK":
        body_bytes, _ = _collect_imap_literals(body_data)

    message = BytesParser(policy=policy.default).parsebytes(header_bytes)
    from_name, from_addr = parse_addresses(message.get("From"))
    subject = decode_mime_text(message.get("Subject"))
    to_addrs = ", ".join(addr for _, addr in getaddresses([message.get("To") or ""]) if addr)
    attachment_names = extract_attachment_names_from_structure(structure_text)
    raw_flags = " ".join(re.findall(r"\\\w+", structure_text))
    return {
        "uid": uid.decode("ascii", errors="ignore"),
        "message_id": clean_text(message.get("Message-ID")),
        "from_name": from_name,
        "from_addr": from_addr,
        "to_addrs": to_addrs,
        "subject": subject,
        "received_at": parse_received_at(message.get("Date")),
        "body_preview": body_preview_from_bytes(body_bytes),
        "attachment_names": attachment_names,
        "raw_flags": raw_flags,
    }


def upsert_mail_message(account: dict[str, Any], mailbox: str, summary: dict[str, Any]) -> tuple[int, bool]:
    classification = classify_message(
        subject=summary.get("subject", ""),
        body_preview=summary.get("body_preview", ""),
        attachment_names=summary.get("attachment_names", []),
    )
    now = now_text()
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id FROM mail_messages
            WHERE account_email = ? AND mailbox = ? AND uid = ?
            """,
            (account["account_email"], mailbox, summary["uid"]),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE mail_messages
                SET message_id = ?, from_name = ?, from_addr = ?, to_addrs = ?,
                    subject = ?, received_at = ?, body_preview = ?, attachment_names = ?,
                    raw_flags = ?, matched_rules = ?, confidence = ?,
                    last_seen_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    summary.get("message_id", ""),
                    summary.get("from_name", ""),
                    summary.get("from_addr", ""),
                    summary.get("to_addrs", ""),
                    summary.get("subject", ""),
                    summary.get("received_at", ""),
                    summary.get("body_preview", ""),
                    to_json(summary.get("attachment_names", [])),
                    summary.get("raw_flags", ""),
                    to_json(classification["matched_rules"]),
                    int(classification["confidence"]),
                    now,
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"]), False

        cursor = conn.execute(
            """
            INSERT INTO mail_messages (
                account_id, account_email, mailbox, uid, message_id,
                from_name, from_addr, to_addrs, subject, received_at,
                body_preview, attachment_names, raw_flags, business_labels,
                status_label, risk_labels, confidence, matched_rules,
                last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account["id"],
                account["account_email"],
                mailbox,
                summary["uid"],
                summary.get("message_id", ""),
                summary.get("from_name", ""),
                summary.get("from_addr", ""),
                summary.get("to_addrs", ""),
                summary.get("subject", ""),
                summary.get("received_at", ""),
                summary.get("body_preview", ""),
                to_json(summary.get("attachment_names", [])),
                summary.get("raw_flags", ""),
                to_json(classification["business_labels"]),
                classification["status_label"],
                to_json(classification["risk_labels"]),
                int(classification["confidence"]),
                to_json(classification["matched_rules"]),
                now,
                now,
                now,
            ),
        )
        message_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO mail_classification_logs (
                message_id, previous_business_labels, previous_status_label,
                previous_risk_labels, new_business_labels, new_status_label,
                new_risk_labels, action, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                "",
                "",
                "",
                to_json(classification["business_labels"]),
                classification["status_label"],
                to_json(classification["risk_labels"]),
                "auto_classify",
                "首次同步自动分类",
                now,
            ),
        )
        return message_id, True


def sync_mail_account(account_email: str, *, mailbox: str | None = None, sync_days: int | None = None) -> MailSyncResult:
    init_mail_classifier_db()
    account = _get_account_with_secret(account_email)
    target_mailbox = clean_text(mailbox or account.get("default_mailbox") or DEFAULT_MAILBOX)
    days = max(1, min(int(sync_days or account.get("sync_days") or DEFAULT_SYNC_DAYS), 365))
    since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    imported = 0
    updated = 0
    skipped = 0
    scanned = 0
    mail = _imap_connect(account)
    try:
        status, _ = mail.select(encode_imap_mailbox_name(target_mailbox), readonly=True)
        if status != "OK":
            raise RuntimeError(f"无法打开邮箱文件夹：{target_mailbox}")
        status, search_data = mail.uid("search", None, "SINCE", since_date)
        if status != "OK":
            raise RuntimeError("IMAP 搜索邮件失败。")
        uids = search_data[0].split() if search_data and search_data[0] else []
        for uid in uids[-MAX_SYNC_MESSAGES:]:
            scanned += 1
            try:
                summary = _fetch_message_summary(mail, uid)
                _, is_new = upsert_mail_message(account, target_mailbox, summary)
                if is_new:
                    imported += 1
                else:
                    updated += 1
            except Exception:  # noqa: BLE001
                skipped += 1
    finally:
        try:
            mail.close()
        except Exception:  # noqa: BLE001
            pass
        mail.logout()
    return MailSyncResult(scanned=scanned, imported=imported, updated=updated, skipped=skipped, mailbox=target_mailbox)


def label_names(keys: Sequence[str], mapping: dict[str, str]) -> list[str]:
    return [mapping.get(key, key) for key in keys]


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    business_keys = from_json_list(item.get("business_labels"))
    risk_keys = from_json_list(item.get("risk_labels"))
    attachment_names = from_json_list(item.get("attachment_names"))
    try:
        matched_rules = json.loads(item.get("matched_rules") or "[]")
    except json.JSONDecodeError:
        matched_rules = []
    item["business_label_keys"] = business_keys
    item["business_label_names"] = label_names(business_keys, BUSINESS_LABEL_MAP)
    item["risk_label_keys"] = risk_keys
    item["risk_label_names"] = label_names(risk_keys, RISK_LABEL_MAP)
    item["status_label_name"] = STATUS_LABEL_MAP.get(item.get("status_label"), item.get("status_label", ""))
    item["attachment_names_list"] = attachment_names
    item["matched_rules_list"] = matched_rules if isinstance(matched_rules, list) else []
    return item


def list_mail_messages(
    *,
    account_email: str = "",
    business_label: str = "",
    status_label: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    init_mail_classifier_db()
    conditions: list[str] = []
    params: list[Any] = []
    if account_email:
        conditions.append("account_email = ?")
        params.append(normalize_email(account_email))
    if status_label:
        conditions.append("status_label = ?")
        params.append(status_label)
    if business_label:
        conditions.append("business_labels LIKE ?")
        params.append(f'%"{business_label}"%')
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(max(1, min(int(limit), 500)))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM mail_messages
            {where}
            ORDER BY COALESCE(received_at, '') DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_message(row) for row in rows]


def update_mail_message_labels(
    message_id: int,
    *,
    business_labels: Sequence[str],
    status_label: str,
) -> None:
    init_mail_classifier_db()
    valid_business = [key for key, _ in BUSINESS_LABELS]
    valid_status = {key for key, _ in STATUS_LABELS}
    cleaned_business = [key for key in business_labels if key in valid_business]
    if not cleaned_business:
        cleaned_business = ["other"]
    cleaned_business = list(dict.fromkeys(cleaned_business))
    cleaned_status = status_label if status_label in valid_status else "needs_review"
    now = now_text()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM mail_messages WHERE id = ?", (message_id,)).fetchone()
        if not row:
            raise ValueError("没有找到这封邮件记录。")
        risk_labels = from_json_list(row["risk_labels"])
        if len(cleaned_business) > 1 and "rule_conflict" not in risk_labels:
            risk_labels.append("rule_conflict")
        if len(cleaned_business) == 1 and "rule_conflict" in risk_labels:
            risk_labels = [item for item in risk_labels if item != "rule_conflict"]
        conn.execute(
            """
            UPDATE mail_messages
            SET business_labels = ?, status_label = ?, risk_labels = ?, updated_at = ?
            WHERE id = ?
            """,
            (to_json(cleaned_business), cleaned_status, to_json(risk_labels), now, message_id),
        )
        conn.execute(
            """
            INSERT INTO mail_classification_logs (
                message_id, previous_business_labels, previous_status_label,
                previous_risk_labels, new_business_labels, new_status_label,
                new_risk_labels, action, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                row["business_labels"],
                row["status_label"],
                row["risk_labels"],
                to_json(cleaned_business),
                cleaned_status,
                to_json(risk_labels),
                "manual_update",
                "用户手动调整标签",
                now,
            ),
        )


def get_mail_summary() -> dict[str, Any]:
    init_mail_classifier_db()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mail_messages").fetchone()[0]
        needs_review = conn.execute("SELECT COUNT(*) FROM mail_messages WHERE status_label = 'needs_review'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM mail_messages WHERE status_label = 'pending'").fetchone()[0]
    return {"total": total, "needs_review": needs_review, "pending": pending}


from app.modules.mail_classifier.rules import DEFAULT_RULES, classify_message
