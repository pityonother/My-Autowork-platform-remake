from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.modules.finance.parsers import parse_exchange_rate, parse_payment_amount_text, split_invoice_payment_description
from app.modules.finance.rules import finance_business_key, finance_export_row_key, finance_record_business_fields_match


def test_parse_payment_amount_text_supports_hkd_and_rmb() -> None:
    assert parse_payment_amount_text("代垫 HKD 1,234.50") == ("HKD", Decimal("0.00"), Decimal("1234.50"))
    assert parse_payment_amount_text("付款 RMB 88") == ("RMB", Decimal("88.00"), Decimal("0.00"))


def test_parse_exchange_rate_accepts_blank_and_decimal_text() -> None:
    assert parse_exchange_rate("") is None
    assert parse_exchange_rate("  0.9148  ") == Decimal("0.91")


def test_parse_exchange_rate_rejects_invalid_text() -> None:
    assert parse_exchange_rate("abc") is None


def test_split_invoice_payment_description_extracts_business_fields_and_date() -> None:
    result = split_invoice_payment_description("SO123\\HAWB456\\DGF\\05/18", "2026-05-01")

    assert result == ("SO123\\HAWB456\\DGF", "SO123", "HAWB456", "DGF", "2026-05-18")


def test_finance_business_key_uses_currency_specific_amount() -> None:
    row = {
        "remark": "  SO123   HAWB456 ",
        "reimbursement_date": "2026-05-18",
        "currency": "HKD",
        "amount_rmb": 100,
        "amount_hkd": 200,
    }

    assert finance_business_key(row) == ("SO123 HAWB456", "2026-05-18", "HKD", "200.00")


def test_finance_export_row_key_normalizes_text_and_amounts() -> None:
    row = SimpleNamespace(
        forwarder_inv_no=" inv 001 ",
        hawb_ref=" hawb  456 ",
        forwarder=" dgf ",
        special_handling=Decimal("3.456"),
        amount_hkd=Decimal("200"),
    )

    assert finance_export_row_key(row) == ("INV 001", "HAWB 456", "DGF", "3.46", "200.00")


def test_duplicate_business_fields_match_hawb_forwarder_variants() -> None:
    candidate = {"so_no": "SO123", "hawb_ref": "HAWB456/DGF", "forwarder": ""}
    row = {"so_no": "SO123", "hawb_ref": "HAWB456", "forwarder": "DGF"}

    assert finance_record_business_fields_match(candidate, row)
