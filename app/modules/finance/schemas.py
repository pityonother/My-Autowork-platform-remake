from __future__ import annotations

TASK_STATUS_OPTIONS = [
    ("submitted_to_finance", "提交给财务付款"),
    ("water_slip_received", "财务提供水单"),
    ("sent_out", "水单已发送出去"),
    ("invoice_received", "对方开票回来"),
    ("completed", "任务完成"),
]
TASK_STATUS_LABELS = dict(TASK_STATUS_OPTIONS)


__all__ = ["TASK_STATUS_LABELS", "TASK_STATUS_OPTIONS"]
