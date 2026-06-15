from __future__ import annotations

from app.modules.ufo_mail.legacy_adapter import (
    UfoIssueInput,
    create_ufo_issue,
    export_ufo_config_package,
    get_ufo_mail_settings,
    get_ufo_signature_settings,
    import_ufo_config_package,
    list_ufo_issues,
    save_ufo_mail_settings,
    set_ufo_issue_active,
    set_ufo_signature_enabled,
    update_ufo_issue,
)


__all__ = [
    "UfoIssueInput",
    "create_ufo_issue",
    "export_ufo_config_package",
    "get_ufo_mail_settings",
    "get_ufo_signature_settings",
    "import_ufo_config_package",
    "list_ufo_issues",
    "save_ufo_mail_settings",
    "set_ufo_issue_active",
    "set_ufo_signature_enabled",
    "update_ufo_issue",
]
