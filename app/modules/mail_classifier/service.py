from __future__ import annotations

from typing import Any


def sync_mail_account(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from app.modules.mail_classifier.legacy_adapter import sync_mail_account as legacy_sync_mail_account

    return legacy_sync_mail_account(*args, **kwargs)


__all__ = ["sync_mail_account"]
