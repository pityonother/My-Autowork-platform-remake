from __future__ import annotations

from collections.abc import Sequence
from typing import Any


BUSINESS_LABEL_NAMES = {
    "export_order": "出口订单",
    "export_customs": "出口清关",
    "advance_payment": "代垫",
    "invoice": "发票",
    "customer_docs": "客户资料",
    "exception": "异常",
    "other": "其他",
}

DEFAULT_RULES = [
    (
        "export_order",
        ["交仓", "订车", "tan", "司机资料", "交仓单", "装箱单", "入仓", "截仓", "so", "extr"],
    ),
    (
        "export_customs",
        ["清关", "报关", "customs", "declaration", "clearance", "报关单", "放行", "查验", "商检", "海关", "hs code"],
    ),
    (
        "advance_payment",
        ["代垫", "支出", "付款", "payment", "payable", "reimbursement", "hub related", "派送费", "卸货费", "停车费"],
    ),
    (
        "invoice",
        ["发票", "invoice", "commercial invoice", "tax invoice", "billing", "账单", "开票"],
    ),
    (
        "customer_docs",
        ["客户资料", "资料更新", "contact", "profile", "授权书", "委托书"],
    ),
    (
        "exception",
        ["异常", "missing", "damage", "damaged", "short", "wrong", "hold", "problem", "discrepancy"],
    ),
]


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def normalize_match_text(value: str) -> str:
    return clean_text(value).lower()


def classify_message(*, subject: str, body_preview: str, attachment_names: Sequence[str]) -> dict[str, Any]:
    haystack = normalize_match_text(
        " ".join([subject or "", body_preview or "", " ".join(attachment_names)])
    )
    matched_labels: list[str] = []
    matched_rules: list[dict[str, Any]] = []
    total_hits = 0
    for label_key, terms in DEFAULT_RULES:
        hits = [term for term in terms if normalize_match_text(term) in haystack]
        if not hits:
            continue
        matched_labels.append(label_key)
        total_hits += len(hits)
        matched_rules.append(
            {
                "label": label_key,
                "label_name": BUSINESS_LABEL_NAMES.get(label_key, label_key),
                "hits": hits[:8],
            }
        )

    risk_labels: list[str] = []
    if attachment_names:
        risk_labels.append("has_attachment")
    normalized_subject = normalize_match_text(subject)
    if normalized_subject.startswith(("fw:", "fwd:", "转发")):
        risk_labels.append("forwarded")
    if normalized_subject.startswith(("re:", "回复")):
        risk_labels.append("history_thread")
    if any(term in haystack for term in ["附件", "attached", "attachment"]) and not attachment_names:
        risk_labels.append("missing_attachment")

    if not matched_labels:
        matched_labels = ["other"]
        confidence = 25
        status_label = "needs_review"
        risk_labels.append("low_confidence")
    else:
        confidence = min(95, 55 + total_hits * 8)
        status_label = "pending"

    if len(matched_labels) > 1:
        status_label = "needs_review"
        risk_labels.append("rule_conflict")
        confidence = min(confidence, 70)

    return {
        "business_labels": matched_labels,
        "status_label": status_label,
        "risk_labels": list(dict.fromkeys(risk_labels)),
        "confidence": confidence,
        "matched_rules": matched_rules,
    }


__all__ = ["DEFAULT_RULES", "classify_message"]
