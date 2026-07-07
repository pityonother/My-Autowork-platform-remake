from __future__ import annotations

from pathlib import Path
from typing import Any


def build_finance_export_rows(**filters: Any) -> list[Any]:
    from app.modules.finance.legacy_adapter import build_finance_export_rows as legacy_build_finance_export_rows

    return legacy_build_finance_export_rows(**filters)


def export_finance_outbound_bill(bill_path: Path, rows: list[Any], output_path: Path) -> list[int]:
    from app.modules.finance.legacy_adapter import export_finance_outbound_bill as legacy_export_finance_outbound_bill

    return legacy_export_finance_outbound_bill(bill_path, rows, output_path)


__all__ = ["build_finance_export_rows", "export_finance_outbound_bill"]
