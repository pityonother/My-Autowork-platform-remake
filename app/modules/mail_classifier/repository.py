from __future__ import annotations

from typing import Any


def init_mail_classifier_db() -> None:
    from app.modules.mail_classifier.legacy_adapter import init_mail_classifier_db as legacy_init_mail_classifier_db

    legacy_init_mail_classifier_db()


def get_default_account_form() -> dict[str, Any]:
    from app.modules.mail_classifier.legacy_adapter import get_default_account_form as legacy_get_default_account_form

    return legacy_get_default_account_form()


def get_mail_summary() -> dict[str, Any]:
    from app.modules.mail_classifier.legacy_adapter import get_mail_summary as legacy_get_mail_summary

    return legacy_get_mail_summary()


def list_mail_accounts() -> list[dict[str, Any]]:
    from app.modules.mail_classifier.legacy_adapter import list_mail_accounts as legacy_list_mail_accounts

    return legacy_list_mail_accounts()


def list_mail_messages(**filters: Any) -> list[dict[str, Any]]:
    from app.modules.mail_classifier.legacy_adapter import list_mail_messages as legacy_list_mail_messages

    return legacy_list_mail_messages(**filters)


def save_mail_account_settings(**settings: Any) -> dict[str, Any]:
    from app.modules.mail_classifier.legacy_adapter import (
        save_mail_account_settings as legacy_save_mail_account_settings,
    )

    return legacy_save_mail_account_settings(**settings)


def update_mail_message_labels(message_id: int, *, business_label: str, status_label: str) -> None:
    from app.modules.mail_classifier.legacy_adapter import (
        update_mail_message_labels as legacy_update_mail_message_labels,
    )

    legacy_update_mail_message_labels(message_id, business_label=business_label, status_label=status_label)


__all__ = [
    "get_default_account_form",
    "get_mail_summary",
    "init_mail_classifier_db",
    "list_mail_accounts",
    "list_mail_messages",
    "save_mail_account_settings",
    "update_mail_message_labels",
]
