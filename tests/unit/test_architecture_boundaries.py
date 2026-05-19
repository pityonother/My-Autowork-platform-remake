from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path


def test_main_app_has_no_direct_route_decorators() -> None:
    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / "reconcile_web_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    route_decorators: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app":
                    route_decorators.append(node.name)
    assert route_decorators == []


def test_expected_module_boundary_files_exist() -> None:
    project_root = Path(__file__).resolve().parents[2]
    expected = [
        "app/core/db.py",
        "app/core/paths.py",
        "app/factory.py",
        "app/shared/uploads.py",
        "app/shared/sessions.py",
        "app/shared/files.py",
        "app/shared/excel.py",
        "app/shared/email.py",
        "app/shared/lazy_imports.py",
        "app/shared/performance.py",
        "app/web/home/routes.py",
        "app/modules/billing/routes.py",
        "app/modules/billing/service.py",
        "app/modules/billing/rules/fees.py",
        "app/modules/import_customs/routes.py",
        "app/modules/import_customs/service.py",
        "app/modules/export_clearance/routes.py",
        "app/modules/export_clearance/repository.py",
        "app/modules/export_clearance/rules.py",
        "app/modules/finance/routes.py",
        "app/modules/finance/repository.py",
        "app/modules/finance/parsers.py",
        "app/modules/booking/routes.py",
        "app/modules/booking/service.py",
        "app/modules/booking/excel_io.py",
        "app/modules/booking/rules/protocol.py",
        "app/modules/booking/rules/registry.py",
        "app/modules/dispatch_mail/routes.py",
        "app/modules/dispatch_mail/service.py",
        "app/modules/dispatch_mail/rules/match.py",
        "app/modules/mail_classifier/routes.py",
        "app/modules/mail_classifier/rules.py",
        "app/modules/ufo_mail/routes.py",
        "app/modules/ufo_mail/repository.py",
        "app/modules/ufo_mail/service.py",
    ]
    missing = [relative_path for relative_path in expected if not (project_root / relative_path).is_file()]
    assert missing == []


def test_adapter_modules_import() -> None:
    module_names = [
        "app.modules.booking.rules.registry",
        "app.modules.billing.rules.fees",
        "app.modules.dispatch_mail.rules.classify",
        "app.modules.dispatch_mail.rules.match",
        "app.modules.dispatch_mail.rules.naming",
        "app.modules.export_clearance.rules",
        "app.modules.finance.parsers",
        "app.modules.finance.rules",
        "app.modules.mail_classifier.rules",
        "app.modules.ufo_mail.rules",
    ]
    for module_name in module_names:
        importlib.import_module(module_name)


def test_module_routes_do_not_import_top_level_legacy_modules() -> None:
    project_root = Path(__file__).resolve().parents[2]
    legacy_modules = {
        "invoice_reconciler",
        "customs_reconciler",
        "export_clearance_store",
        "finance_store",
        "booking_store",
        "dispatch_mail_store",
        "mail_classifier_store",
        "ufo_mail_store",
    }
    violations: list[str] = []
    for path in (project_root / "app" / "modules").rglob("routes.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in legacy_modules:
                violations.append(f"{path.relative_to(project_root).as_posix()}:{node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in legacy_modules:
                        violations.append(f"{path.relative_to(project_root).as_posix()}:{alias.name}")
    assert violations == []


def test_legacy_imports_are_isolated_to_legacy_adapters() -> None:
    project_root = Path(__file__).resolve().parents[2]
    legacy_modules = {
        "invoice_reconciler",
        "customs_reconciler",
        "export_clearance_store",
        "finance_store",
        "booking_store",
        "dispatch_mail_store",
        "mail_classifier_store",
        "ufo_mail_store",
    }
    violations: list[str] = []
    for path in (project_root / "app" / "modules").rglob("*.py"):
        if path.name == "legacy_adapter.py" or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in legacy_modules:
                violations.append(f"{path.relative_to(project_root).as_posix()}:{node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in legacy_modules:
                        violations.append(f"{path.relative_to(project_root).as_posix()}:{alias.name}")
    assert violations == []


def test_routes_use_shared_template_object() -> None:
    project_root = Path(__file__).resolve().parents[2]
    violations = [
        path.relative_to(project_root).as_posix()
        for path in (project_root / "app" / "modules").rglob("routes.py")
        if "create_templates" in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_schema_singular_modules_do_not_hide_db_initializers() -> None:
    project_root = Path(__file__).resolve().parents[2]
    schema_files = [
        path.relative_to(project_root).as_posix()
        for path in (project_root / "app" / "modules").rglob("schema.py")
    ]
    assert schema_files == []


def test_create_app_can_skip_runtime_initializers() -> None:
    from app.factory import create_app

    calls: list[str] = []

    create_app("test", db_initializers=[lambda: calls.append("init")], init_runtime=False)

    assert calls == []


def test_web_app_import_keeps_heavy_libraries_lazy() -> None:
    project_root = Path(__file__).resolve().parents[2]
    heavy_modules = ["pandas", "PIL.Image", "fitz", "openpyxl", "xlrd"]
    script = (
        "import sys; "
        f"heavy = {heavy_modules!r}; "
        "baseline = {name for name in heavy if name in sys.modules}; "
        "import reconcile_web_app; "
        "loaded_after = {name for name in heavy if name in sys.modules}; "
        "newly_loaded = sorted(loaded_after - baseline); "
        "print('\\n'.join(newly_loaded)); "
        "raise SystemExit(1 if newly_loaded else 0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
