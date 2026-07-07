from __future__ import annotations

from typing import Any


def init_finance_db() -> None:
    from app.modules.finance.legacy_adapter import init_finance_db as legacy_init_finance_db

    legacy_init_finance_db()


def get_finance_batch_detail(batch_id: int) -> dict[str, Any]:
    from app.modules.finance.legacy_adapter import get_finance_batch_detail as legacy_get_finance_batch_detail

    return legacy_get_finance_batch_detail(batch_id)


def list_finance_batches() -> list[dict[str, Any]]:
    from app.modules.finance.legacy_adapter import list_finance_batches as legacy_list_finance_batches

    return legacy_list_finance_batches()


def list_finance_records(**filters: Any) -> list[dict[str, Any]]:
    from app.modules.finance.legacy_adapter import list_finance_records as legacy_list_finance_records

    return legacy_list_finance_records(**filters)


def mark_finance_records_exported(record_ids: list[int]) -> None:
    from app.modules.finance.legacy_adapter import mark_finance_records_exported as legacy_mark_finance_records_exported

    legacy_mark_finance_records_exported(record_ids)


def summarize_finance_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    from app.modules.finance.legacy_adapter import summarize_finance_records as legacy_summarize_finance_records

    return legacy_summarize_finance_records(records)


def update_finance_export_status(record_id: int, exported: bool) -> None:
    from app.modules.finance.legacy_adapter import update_finance_export_status as legacy_update_finance_export_status

    legacy_update_finance_export_status(record_id, exported)


def update_finance_task_status(record_id: int, task_status: str) -> None:
    from app.modules.finance.legacy_adapter import update_finance_task_status as legacy_update_finance_task_status

    legacy_update_finance_task_status(record_id, task_status)


__all__ = [
    "get_finance_batch_detail",
    "init_finance_db",
    "list_finance_batches",
    "list_finance_records",
    "mark_finance_records_exported",
    "summarize_finance_records",
    "update_finance_export_status",
    "update_finance_task_status",
]
