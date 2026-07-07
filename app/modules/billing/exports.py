from __future__ import annotations

from typing import Any


def reconcile(**kwargs: Any) -> Any:
    from app.modules.billing.legacy_adapter import reconcile as legacy_reconcile

    return legacy_reconcile(**kwargs)


__all__ = ["reconcile"]
