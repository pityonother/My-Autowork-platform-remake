from __future__ import annotations

from fastapi.testclient import TestClient

from booking_web_app import app as booking_app
from reconcile_web_app import app as main_app


def test_main_pages_open() -> None:
    client = TestClient(main_app)
    paths = [
        "/",
        "/modules/billing",
        "/modules/booking",
        "/modules/dispatch-mail",
        "/modules/export-customs",
        "/modules/finance-records",
        "/modules/mail-classifier",
        "/modules/ufo-mail",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path


def test_ufo_mail_cache_button_renders_chinese_text() -> None:
    client = TestClient(main_app)
    response = client.get("/modules/ufo-mail")

    assert response.status_code == 200
    assert "清理输出缓存" in response.text
    assert "????" not in response.text


def test_ufo_mail_low_confidence_review_confirmation_renders(monkeypatch) -> None:
    from app.modules.ufo_mail import routes

    def fake_generate_mail(**kwargs):
        raise routes.LowConfidenceReviewRequired(
            session_id="abc123def456",
            review_reports=[r"C:\runtime\outputs\ufo.cover_report.csv"],
        )

    monkeypatch.setattr(routes, "generate_mail", fake_generate_mail)
    client = TestClient(main_app)
    response = client.post(
        "/modules/ufo-mail/generate",
        data={
            "ufo_no": "UFO26052203",
            "to_email": "to@example.com",
            "cc_email": "",
            "from_email": "from@example.com",
            "issue_ids": "1",
        },
        files=[("attachments", ("RH2600000.pdf", b"%PDF-1.4\n", "application/pdf"))],
    )

    assert response.status_code == 400
    assert "/modules/ufo-mail/generate/confirm-review" in response.text
    assert 'name="session_id" value="abc123def456"' in response.text
    assert 'name="ufo_no" value="UFO26052203"' in response.text


def test_booking_standalone_entry_opens() -> None:
    client = TestClient(booking_app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in {200, 307}

    page_response = client.get("/modules/booking")
    assert page_response.status_code == 200


def test_finance_records_rejects_invalid_batch_id() -> None:
    client = TestClient(main_app, raise_server_exceptions=False)
    response = client.get("/modules/finance-records?batch_id=abc")

    assert response.status_code == 400


def test_finance_export_rejects_invalid_exchange_rate() -> None:
    client = TestClient(main_app, raise_server_exceptions=False)
    response = client.post(
        "/modules/finance-records/export",
        data={"exchange_rate": "abc"},
        files={"bill_file": ("bill.xls", b"abc", "application/vnd.ms-excel")},
    )

    assert response.status_code == 400
