from __future__ import annotations

from app.modules.dispatch_mail.rules.match import content_match_score, extract_match_tokens
from app.modules.dispatch_mail.rules.naming import build_dispatch_attachment_name, unique_filename


def test_extract_match_tokens_keeps_business_identifiers() -> None:
    tokens = extract_match_tokens("Customer PO ABC-12345, TAN# 98765, shipping attached")

    assert "abc12345" in tokens
    assert "98765" in tokens
    assert "shipping" not in tokens


def test_content_match_score_prefers_identifier_overlap() -> None:
    score = content_match_score("SO ABC-12345 cartons", "ticket ABC-12345 pallets")

    assert score >= 0.70


def test_dispatch_attachment_names_are_stable_and_unique() -> None:
    filename = build_dispatch_attachment_name("2板1箱", "dqth", 1, ".xlsx")
    used = {filename}

    assert filename == "2板1箱装箱单(1).xlsx"
    assert unique_filename(filename, used) == "2板1箱装箱单(1)(2).xlsx"
