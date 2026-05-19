from __future__ import annotations

from app.modules.mail_classifier.legacy_adapter import (
    get_default_account_form,
    get_mail_summary,
    list_mail_accounts,
    list_mail_messages,
    save_mail_account_settings,
    update_mail_message_labels,
)


__all__ = [
    "get_default_account_form",
    "get_mail_summary",
    "list_mail_accounts",
    "list_mail_messages",
    "save_mail_account_settings",
    "update_mail_message_labels",
]
