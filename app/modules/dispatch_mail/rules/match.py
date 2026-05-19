from __future__ import annotations

import re
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


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


def close_number(a: Decimal, b: Decimal, tolerance: Decimal = Decimal("0.02")) -> bool:
    return abs(a - b) <= tolerance


def match_dqths(tickets: list[Any], dqths: list[Any]) -> None:
    available = set(range(len(tickets)))
    for dqth in dqths:
        candidates: list[tuple[int, int]] = []
        for idx in available:
            ticket = tickets[idx]
            po_overlap = len(set(ticket.customer_pos) & set(dqth.customer_pos))
            if po_overlap == 0:
                continue
            score = po_overlap * 10
            if close_number(ticket.cartons, dqth.cartons):
                score += 3
            if close_number(ticket.pallets, dqth.pallets):
                score += 3
            if close_number(ticket.gross_weight, dqth.gross_weight, Decimal("1")):
                score += 3
            candidates.append((score, idx))
        if candidates:
            candidates.sort(key=lambda item: (-item[0], item[1]))
            best_score, best_idx = candidates[0]
            if best_score >= 10:
                dqth.matched_ticket_index = best_idx
                dqth.status = "已匹配"
                tickets[best_idx].dqth = dqth
                available.discard(best_idx)


def extract_match_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in re.findall(r"[A-Za-z0-9][A-Za-z0-9./#_-]{2,}", text):
        normalized = raw_token.strip(" .,#:/_-").lower().replace("#", "")
        for piece in [normalized, *re.split(r"[./_-]+", normalized)]:
            token = re.sub(r"[^a-z0-9]+", "", piece)
            if len(token) < 3 or token in GENERIC_ATTACHMENT_TOKENS:
                continue
            has_digit = any(char.isdigit() for char in token)
            if token.isdigit() and len(token) < 5:
                continue
            if not has_digit and len(token) < 4 and token not in {"ceva", "dgf", "sdb"}:
                continue
            tokens.add(token)
    return tokens


def content_match_score(attachment_text: str, ticket_text: str) -> float:
    attachment_tokens = extract_match_tokens(attachment_text)
    ticket_tokens = extract_match_tokens(ticket_text)
    if not attachment_tokens or not ticket_tokens:
        return 0
    overlap = attachment_tokens & ticket_tokens
    if not overlap:
        return 0
    identifier_overlap = {token for token in overlap if any(char.isdigit() for char in token)}
    word_overlap = overlap - identifier_overlap
    if identifier_overlap:
        return min(0.98, 0.58 + len(identifier_overlap) * 0.15 + len(word_overlap) * 0.04)
    return min(0.72, 0.35 + len(word_overlap) * 0.12)


def token_match_score(filename_stem: str, remark: str) -> float:
    tokens = re.findall(r"[A-Za-z0-9]{3,}", filename_stem.lower())
    if not tokens:
        return 0
    remark_lower = remark.lower()
    matched = sum(1 for token in tokens if token in remark_lower)
    if matched == 0:
        return 0
    return min(0.95, 0.35 + matched / len(tokens) * 0.6)


def _ensure_attachment_text(attachment: Any) -> None:
    from app.modules.dispatch_mail.legacy_adapter import ensure_attachment_text

    ensure_attachment_text(attachment)


def score_so_match(so: Any, ticket: Any) -> float:
    _ensure_attachment_text(so.attachment)
    base_name = Path(so.attachment.original_name).stem
    ticket_text = " ".join([ticket.remark, *ticket.customer_pos])
    filename_score = max(
        SequenceMatcher(None, base_name.lower(), ticket_text.lower()).ratio(),
        token_match_score(base_name, ticket_text),
    )
    content_score = content_match_score(f"{so.attachment.original_name} {so.attachment.text}", ticket_text)
    return max(filename_score, content_score)


__all__ = ["content_match_score", "extract_match_tokens", "match_dqths", "score_so_match"]
