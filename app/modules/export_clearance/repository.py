from __future__ import annotations

from typing import Any


def init_db() -> None:
    from app.modules.export_clearance.legacy_adapter import init_db as legacy_init_db

    legacy_init_db()


def get_batch_detail(batch_id: int) -> dict[str, Any]:
    from app.modules.export_clearance.legacy_adapter import get_batch_detail as legacy_get_batch_detail

    return legacy_get_batch_detail(batch_id)


def list_batches() -> list[dict[str, Any]]:
    from app.modules.export_clearance.legacy_adapter import list_batches as legacy_list_batches

    return legacy_list_batches()


def list_records(**filters: Any) -> list[dict[str, Any]]:
    from app.modules.export_clearance.legacy_adapter import list_records as legacy_list_records

    return legacy_list_records(**filters)


def mark_record_clearance(record_id: int, status: str) -> None:
    from app.modules.export_clearance.legacy_adapter import mark_record_clearance as legacy_mark_record_clearance

    legacy_mark_record_clearance(record_id, status)


__all__ = ["get_batch_detail", "init_db", "list_batches", "list_records", "mark_record_clearance"]
