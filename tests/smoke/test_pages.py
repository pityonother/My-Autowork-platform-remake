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


def test_ufo_mail_client_can_save_and_reload_recipient_settings(monkeypatch, tmp_path) -> None:
    import ufo_mail_store

    monkeypatch.setattr(ufo_mail_store, "DB_PATH", tmp_path / "ufo_mail.db")
    monkeypatch.setattr(ufo_mail_store, "SIGNATURE_DIR", tmp_path / "ufo_signature")
    client = TestClient(main_app, follow_redirects=False)

    save_response = client.post(
        "/modules/ufo-mail/settings",
        data={
            "to_email": "to@example.com",
            "cc_email": "cc@example.com",
            "from_email": "from@example.com",
        },
    )
    page_response = client.get("/modules/ufo-mail")

    assert save_response.status_code == 303
    assert save_response.headers["location"] == "/modules/ufo-mail#generate"
    assert 'name="to_email" value="to@example.com"' in page_response.text
    assert 'name="cc_email" value="cc@example.com"' in page_response.text
    assert 'name="from_email" value="from@example.com"' in page_response.text


def test_ufo_mail_low_confidence_review_confirmation_renders(monkeypatch, tmp_path) -> None:
    import ufo_mail_store
    from app.modules.ufo_mail import routes

    monkeypatch.setattr(ufo_mail_store, "DB_PATH", tmp_path / "ufo_mail.db")
    monkeypatch.setattr(ufo_mail_store, "SIGNATURE_DIR", tmp_path / "ufo_signature")

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
    assert 'name="to_email" value="to@example.com"' in response.text
    assert 'name="cc_email" value=""' in response.text
    assert 'name="from_email" value="from@example.com"' in response.text


def test_booking_standalone_entry_opens() -> None:
    client = TestClient(booking_app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in {200, 307}

    page_response = client.get("/modules/booking")
    assert page_response.status_code == 200


def test_home_page_has_flex_texas_booking_shortcut() -> None:
    client = TestClient(main_app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Flex-Texas Booking" in response.text
    assert 'href="/modules/booking?supplier=FLEX-TEXAS"' in response.text


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
