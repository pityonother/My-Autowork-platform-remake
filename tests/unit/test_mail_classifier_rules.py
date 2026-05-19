from __future__ import annotations

import mail_classifier_store
from app.modules.mail_classifier.rules import classify_message


def test_classify_message_detects_business_and_attachment_risk() -> None:
    result = classify_message(
        subject="FW: TAN 交仓单",
        body_preview="请安排司机资料",
        attachment_names=["packing.xlsx"],
    )

    assert "export_order" in result["business_labels"]
    assert result["status_label"] == "pending"
    assert "has_attachment" in result["risk_labels"]
    assert "forwarded" in result["risk_labels"]


def test_classify_message_marks_unknown_missing_attachment_for_review() -> None:
    result = classify_message(subject="hello", body_preview="please see attached", attachment_names=[])

    assert result["business_labels"] == ["other"]
    assert result["status_label"] == "needs_review"
    assert "missing_attachment" in result["risk_labels"]


def test_legacy_store_reexports_classify_message() -> None:
    assert mail_classifier_store.classify_message is classify_message
