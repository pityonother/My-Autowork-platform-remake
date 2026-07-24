from __future__ import annotations

import ast
from pathlib import Path


def test_no_duplicate_top_level_function_names() -> None:
    project_root = Path(__file__).resolve().parents[2]
    duplicates: list[str] = []
    ignored_dirs = {
        ".git",
        ".github",
        ".idea",
        ".pytest_cache",
        ".venv",
        ".venv-yolo",
        "__pycache__",
        "build",
        "dist",
        "release_site",
        "runtime",
    }

    source_files = [
        path
        for path in project_root.rglob("*.py")
        if not any(part in ignored_dirs or part.startswith(".venv") for part in path.relative_to(project_root).parts)
    ]
    for path in source_files:
        relative_path = path.relative_to(project_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        seen: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    duplicates.append(f"{relative_path}:{node.name}")
                seen.add(node.name)

    assert duplicates == []


def test_module_css_files_are_loaded_by_their_templates() -> None:
    project_root = Path(__file__).resolve().parents[2]
    module_templates = {
        "booking": ["booking.html"],
        "dispatch_mail": [
            "dispatch_attachment_preview.html",
            "dispatch_mail.html",
            "dispatch_mail_compose.html",
            "dispatch_mail_preview.html",
        ],
        "finance": ["finance_batch.html", "finance_records.html"],
        "mail_classifier": ["mail_classifier.html"],
        "ufo_mail": ["ufo_mail.html"],
    }
    missing: list[str] = []
    for module_name, template_names in module_templates.items():
        css_path = project_root / "static" / "modules" / module_name / "styles.css"
        if not css_path.is_file() or not css_path.read_text(encoding="utf-8").strip():
            missing.append(f"static/modules/{module_name}/styles.css")
            continue
        href = f"/static/modules/{module_name}/styles.css"
        for template_name in template_names:
            text = (project_root / "templates" / template_name).read_text(encoding="utf-8")
            if href not in text:
                missing.append(f"{template_name}:{href}")

    assert missing == []


def test_module_specific_css_is_not_left_in_global_stylesheet() -> None:
    project_root = Path(__file__).resolve().parents[2]
    text = (project_root / "static" / "styles.css").read_text(encoding="utf-8")
    disallowed = [
        ".booking-",
        ".finance-",
        ".dispatch-",
        ".ufo-",
        ".mail-classifier-page",
        ".mail-app-",
    ]
    leftovers = [prefix for prefix in disallowed if prefix in text]

    assert leftovers == []


def test_ufo_settings_save_button_bypasses_generate_form_validation() -> None:
    project_root = Path(__file__).resolve().parents[2]
    text = (project_root / "templates" / "ufo_mail.html").read_text(encoding="utf-8")
    button_start = text.index('formaction="/modules/ufo-mail/settings"')
    button_end = text.index(">", button_start)

    assert "formnovalidate" in text[button_start:button_end]


def test_ufo_mail_recipient_fields_are_client_editable() -> None:
    project_root = Path(__file__).resolve().parents[2]
    text = (project_root / "templates" / "ufo_mail.html").read_text(encoding="utf-8")

    for field_name in ("to_email", "cc_email", "from_email"):
        input_start = text.index(f'name="{field_name}"', text.index('id="ufo-generate-form"'))
        input_end = text.index(">", input_start)
        assert "readonly" not in text[input_start:input_end]


def test_ufo_issue_cards_support_free_drag_and_personal_ordering() -> None:
    project_root = Path(__file__).resolve().parents[2]
    text = (project_root / "templates" / "ufo_mail.html").read_text(encoding="utf-8")
    css = (project_root / "static" / "modules" / "ufo_mail" / "styles.css").read_text(encoding="utf-8")

    required_markup = [
        'id="ufo-issue-search"',
        'id="ufo-arrange-issues-btn"',
        'id="ufo-arrange-save-btn"',
        'id="ufo-arrange-cancel-btn"',
        'id="ufo-arrange-reset-btn"',
        'id="ufo-issue-grid"',
        'data-ufo-issue-id="{{ issue.id }}"',
    ]
    for fragment in required_markup:
        assert fragment in text

    required_drag_behaviour = [
        "ufo-issue-personal-order-v1",
        "pointerdown",
        "pointermove",
        "pointerup",
        "elementsFromPoint",
        "ufo-drag-ghost",
    ]
    for fragment in required_drag_behaviour:
        assert fragment in text

    assert "ufo-step-buttons" not in text
    assert ".ufo-issue-tile[hidden]" in css


def test_ufo_reason_workspace_matches_approved_site_and_throttles_drag() -> None:
    project_root = Path(__file__).resolve().parents[2]
    text = (project_root / "templates" / "ufo_mail.html").read_text(encoding="utf-8")
    css = (project_root / "static" / "modules" / "ufo_mail" / "styles.css").read_text(encoding="utf-8")

    for fragment in (
        "ufo-reason-workspace",
        'id="ufo-reason-filter-row"',
        'data-ufo-issue-category=',
        "ufo-category-tag",
        "ufo-position-number",
        'id="ufo-detail-panel"',
        'id="ufo-reason-dock"',
    ):
        assert fragment in text

    for fragment in (
        "dragFrameRequest",
        "requestAnimationFrame(flushIssueDragFrame)",
        "translate3d",
        "getAnimations().forEach",
        "lastTargetId",
    ):
        assert fragment in text

    for fragment in (
        "--ufo-reason-forest: #1f5545",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        "min-height: 164px",
        "background: rgba(18, 60, 49, 0.94)",
    ):
        assert fragment in css
