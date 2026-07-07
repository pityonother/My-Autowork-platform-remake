from __future__ import annotations

from typing import Any


def init_dispatch_db() -> None:
    from app.modules.dispatch_mail.legacy_adapter import init_dispatch_db as legacy_init_dispatch_db

    legacy_init_dispatch_db()


def get_dispatch_settings() -> dict[str, Any]:
    from app.modules.dispatch_mail.legacy_adapter import get_dispatch_settings as legacy_get_dispatch_settings

    return legacy_get_dispatch_settings()


def save_dispatch_settings(settings: dict[str, Any]) -> None:
    from app.modules.dispatch_mail.legacy_adapter import save_dispatch_settings as legacy_save_dispatch_settings

    legacy_save_dispatch_settings(settings)


__all__ = ["get_dispatch_settings", "init_dispatch_db", "save_dispatch_settings"]
