from __future__ import annotations

DEFAULT_IMAP_HOST = "imap.qiye.163.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SYNC_DAYS = 30
DEFAULT_MAILBOX = "INBOX"

BUSINESS_LABELS = [
    ("export_order", "出口订单"),
    ("export_customs", "出口清关"),
    ("advance_payment", "代垫"),
    ("invoice", "发票"),
    ("customer_docs", "客户资料"),
    ("exception", "异常"),
    ("other", "其他"),
]

STATUS_LABELS = [
    ("pending", "待处理"),
    ("needs_review", "待确认"),
    ("completed", "已处理"),
    ("ignored", "忽略"),
]

RISK_LABELS = [
    ("has_attachment", "有附件"),
    ("missing_attachment", "疑似缺附件"),
    ("forwarded", "疑似转发"),
    ("history_thread", "疑似历史邮件"),
    ("rule_conflict", "规则冲突"),
    ("low_confidence", "低置信度"),
]
RISK_LABEL_MAP = dict(RISK_LABELS)


__all__ = [
    "BUSINESS_LABELS",
    "DEFAULT_IMAP_HOST",
    "DEFAULT_IMAP_PORT",
    "DEFAULT_MAILBOX",
    "DEFAULT_SYNC_DAYS",
    "RISK_LABEL_MAP",
    "STATUS_LABELS",
]
