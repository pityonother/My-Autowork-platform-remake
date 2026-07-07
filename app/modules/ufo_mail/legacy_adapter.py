from __future__ import annotations

from ufo_mail_store import (
    UfoAttachment,
    UfoIssueInput,
    UfoMailInput,
    build_ufo_subject,
    create_ufo_issue,
    export_ufo_config_package,
    generate_ufo_eml,
    get_ufo_mail_settings,
    get_ufo_signature_settings,
    init_ufo_db,
    import_ufo_config_package,
    import_ufo_signature_from_eml,
    list_ufo_issues,
    save_ufo_mail_settings,
    set_ufo_issue_active,
    set_ufo_signature_enabled,
    strip_forwarded_history,
    update_ufo_issue,
)


__all__ = [
    "UfoAttachment",
    "UfoIssueInput",
    "UfoMailInput",
    "build_ufo_subject",
    "create_ufo_issue",
    "export_ufo_config_package",
    "generate_ufo_eml",
    "get_ufo_mail_settings",
    "get_ufo_signature_settings",
    "init_ufo_db",
    "import_ufo_config_package",
    "import_ufo_signature_from_eml",
    "list_ufo_issues",
    "save_ufo_mail_settings",
    "set_ufo_issue_active",
    "set_ufo_signature_enabled",
    "strip_forwarded_history",
    "update_ufo_issue",
]
