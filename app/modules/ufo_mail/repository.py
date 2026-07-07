from __future__ import annotations

from typing import Any

from app.modules.ufo_mail.schemas import UfoIssueInput


def init_ufo_db() -> None:
    from app.modules.ufo_mail.legacy_adapter import init_ufo_db as legacy_init_ufo_db

    legacy_init_ufo_db()


def create_ufo_issue(issue: UfoIssueInput) -> None:
    from app.modules.ufo_mail.legacy_adapter import create_ufo_issue as legacy_create_ufo_issue

    legacy_create_ufo_issue(issue)


def export_ufo_config_package(output_path: Any) -> None:
    from app.modules.ufo_mail.legacy_adapter import export_ufo_config_package as legacy_export_ufo_config_package

    legacy_export_ufo_config_package(output_path)


def get_ufo_mail_settings() -> dict[str, Any]:
    from app.modules.ufo_mail.legacy_adapter import get_ufo_mail_settings as legacy_get_ufo_mail_settings

    return legacy_get_ufo_mail_settings()


def get_ufo_signature_settings() -> dict[str, Any]:
    from app.modules.ufo_mail.legacy_adapter import get_ufo_signature_settings as legacy_get_ufo_signature_settings

    return legacy_get_ufo_signature_settings()


def import_ufo_config_package(path: Any) -> dict[str, Any]:
    from app.modules.ufo_mail.legacy_adapter import import_ufo_config_package as legacy_import_ufo_config_package

    return legacy_import_ufo_config_package(path)


def list_ufo_issues(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    from app.modules.ufo_mail.legacy_adapter import list_ufo_issues as legacy_list_ufo_issues

    return legacy_list_ufo_issues(include_inactive=include_inactive)


def save_ufo_mail_settings(to_email: str, cc_email: str, from_email: str) -> None:
    from app.modules.ufo_mail.legacy_adapter import save_ufo_mail_settings as legacy_save_ufo_mail_settings

    legacy_save_ufo_mail_settings(to_email=to_email, cc_email=cc_email, from_email=from_email)


def set_ufo_issue_active(issue_id: int, is_active: bool) -> None:
    from app.modules.ufo_mail.legacy_adapter import set_ufo_issue_active as legacy_set_ufo_issue_active

    legacy_set_ufo_issue_active(issue_id, is_active)


def set_ufo_signature_enabled(enabled: bool) -> None:
    from app.modules.ufo_mail.legacy_adapter import set_ufo_signature_enabled as legacy_set_ufo_signature_enabled

    legacy_set_ufo_signature_enabled(enabled)


def update_ufo_issue(issue_id: int, issue: UfoIssueInput) -> None:
    from app.modules.ufo_mail.legacy_adapter import update_ufo_issue as legacy_update_ufo_issue

    legacy_update_ufo_issue(issue_id, issue)


__all__ = [
    "UfoIssueInput",
    "create_ufo_issue",
    "export_ufo_config_package",
    "get_ufo_mail_settings",
    "get_ufo_signature_settings",
    "import_ufo_config_package",
    "init_ufo_db",
    "list_ufo_issues",
    "save_ufo_mail_settings",
    "set_ufo_issue_active",
    "set_ufo_signature_enabled",
    "update_ufo_issue",
]
