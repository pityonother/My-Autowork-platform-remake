from __future__ import annotations

import ast
from pathlib import Path


def test_no_duplicate_top_level_function_names() -> None:
    project_root = Path(__file__).resolve().parents[2]
    duplicates: list[str] = []

    source_files = [
        path
        for path in project_root.rglob("*.py")
        if not any(part.startswith(".venv") for part in path.parts) and "__pycache__" not in path.parts
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
