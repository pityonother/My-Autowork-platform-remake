from __future__ import annotations

from datetime import date
from io import BytesIO


def export_cleared_workbook(clear_date: date) -> BytesIO:
    from app.modules.export_clearance.legacy_adapter import export_cleared_workbook as legacy_export_cleared_workbook

    return legacy_export_cleared_workbook(clear_date=clear_date)


def export_pending_workbook() -> BytesIO:
    from app.modules.export_clearance.legacy_adapter import export_pending_workbook as legacy_export_pending_workbook

    return legacy_export_pending_workbook()


__all__ = ["export_cleared_workbook", "export_pending_workbook"]
