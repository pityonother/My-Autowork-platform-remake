from __future__ import annotations

from typing import Any


def reconcile_customs(**kwargs: Any) -> Any:
    from app.modules.import_customs.legacy_adapter import reconcile_customs as legacy_reconcile_customs

    return legacy_reconcile_customs(**kwargs)


__all__ = ["reconcile_customs"]
