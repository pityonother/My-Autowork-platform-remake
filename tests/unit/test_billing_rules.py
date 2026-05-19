from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.billing.rules.fees import maybe_correct_fee_name, parse_loading_count_hint, split_loading


def test_parse_loading_count_hint_extracts_pallets_and_cartons() -> None:
    assert parse_loading_count_hint("装卸 2板 3箱") == (Decimal("2.00"), Decimal("3.00"))


def test_split_loading_supports_mixed_pallet_and_carton_amount() -> None:
    result = split_loading(Decimal("137.56"))

    assert result.pallet_count == 2
    assert result.carton_count == 1
    assert result.remark == "2板1箱"


def test_split_loading_rejects_unmatched_amount() -> None:
    with pytest.raises(ValueError):
        split_loading(Decimal("11.00"))


def test_fixed_delivery_fee_typo_is_corrected() -> None:
    corrected, reason = maybe_correct_fee_name("装卸费", "客户送货", Decimal("239.16"))

    assert corrected == "派送费"
    assert reason
