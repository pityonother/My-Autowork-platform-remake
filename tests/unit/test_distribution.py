from __future__ import annotations

import importlib
import asyncio
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.distribution.downloader import HashMismatchError, download_artifact
from app.distribution.errors import InstallError, ManifestError
from app.distribution.installed import InstalledModule, read_installed_modules, write_installed_modules
from app.distribution.installer import install_module, safe_extract_zip
from app.distribution.manifest import parse_manifest
from app.module_catalog import MODULE_CATALOG


def test_runtime_dir_can_be_overridden_by_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import app.core.paths as paths

    runtime_dir = tmp_path / "module-data"
    monkeypatch.setenv("BILL_TOOL_RUNTIME_DIR", str(runtime_dir))
    reloaded = importlib.reload(paths)

    assert reloaded.RUNTIME_DIR == runtime_dir.resolve()

    monkeypatch.delenv("BILL_TOOL_RUNTIME_DIR", raising=False)
    importlib.reload(paths)


def valid_manifest_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-05-27T18:00:00+08:00",
        "release_version": "2026.05.27+abcdef1",
        "modules": {
            "billing": {
                "title": "做账单",
                "version": "2026.05.27+abcdef1",
                "artifact": "modules/billing/BillingTool.zip",
                "sha256": "a" * 64,
                "size": 123,
                "entry_exe": "BillingTool/BillingTool.exe",
                "landing_path": "/modules/billing",
                "start_port": 8031,
            }
        },
    }


def test_manifest_parse_valid_and_resolves_relative_artifact(tmp_path: Path) -> None:
    manifest_url = (tmp_path / "manifest.json").as_uri()
    manifest = parse_manifest(valid_manifest_data(), manifest_url=manifest_url)

    module = manifest.modules["billing"]
    assert manifest.release_version == "2026.05.27+abcdef1"
    assert module.artifact_url.endswith("/modules/billing/BillingTool.zip")
    assert module.start_port == 8031


def test_manifest_requires_modules_field(tmp_path: Path) -> None:
    data = valid_manifest_data()
    data.pop("modules")

    with pytest.raises(ManifestError):
        parse_manifest(data, manifest_url=(tmp_path / "manifest.json").as_uri())


def test_download_rejects_sha256_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"not the expected content")

    with pytest.raises(HashMismatchError):
        download_artifact(
            module_id="billing",
            artifact_url=artifact.as_uri(),
            expected_sha256="0" * 64,
            downloads_dir=tmp_path / "downloads",
        )


def test_zip_slip_path_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../evil.txt", "bad")

    with pytest.raises(InstallError):
        safe_extract_zip(zip_path, tmp_path / "extract")


def test_install_package_missing_entry_keeps_current_version(tmp_path: Path) -> None:
    modules_dir = tmp_path / "modules"
    current_exe = modules_dir / "billing" / "current" / "BillingTool" / "BillingTool.exe"
    current_exe.parent.mkdir(parents=True)
    current_exe.write_text("old-version", encoding="utf-8")
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("BillingTool/README.txt", "missing exe")

    with pytest.raises(InstallError):
        install_module(
            module_id="billing",
            zip_path=zip_path,
            entry_exe="BillingTool/BillingTool.exe",
            modules_dir=modules_dir,
        )

    assert current_exe.read_text(encoding="utf-8") == "old-version"


def test_installed_modules_atomic_read_write(tmp_path: Path) -> None:
    path = tmp_path / "launcher" / "installed_modules.json"
    module = InstalledModule(
        module_id="billing",
        title="做账单",
        version="2026.05.27+abcdef1",
        entry_exe="BillingTool/BillingTool.exe",
        landing_path="/modules/billing",
        start_port=8031,
        installed_at=datetime.now().isoformat(timespec="seconds"),
        artifact_sha256="a" * 64,
    )

    write_installed_modules(path, {"billing": module})
    loaded = read_installed_modules(path)

    assert loaded["billing"].version == module.version
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_installed_modules_corrupted_json_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "launcher" / "installed_modules.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    assert read_installed_modules(path) == {}


def test_launcher_refresh_manifest_error_redirects_without_module_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.web.launcher import routes

    monkeypatch.setattr(routes, "read_manifest_url", lambda: "file:///missing/manifest.json")

    def fail_load_manifest(manifest_url: str):
        raise ManifestError("manifest 不是有效的 JSON 文件。")

    monkeypatch.setattr(routes, "load_manifest", fail_load_manifest)

    response = asyncio.run(routes.refresh())

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert "error_module" not in response.headers["location"]


def test_module_catalog_covers_expected_modules_with_unique_ids() -> None:
    expected = {
        "billing",
        "import_customs",
        "export_clearance",
        "finance",
        "mail_classifier",
        "ufo_mail",
        "dispatch_mail",
        "booking",
    }
    module_ids = [module.module_id for module in MODULE_CATALOG]

    assert set(module_ids) == expected
    assert len(module_ids) == len(set(module_ids))


def test_module_entrypoints_import_without_reconcile_web_app(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    module_names = [
        "module_entrypoints.billing_tool",
        "module_entrypoints.import_customs_tool",
        "module_entrypoints.export_clearance_tool",
        "module_entrypoints.finance_tool",
        "module_entrypoints.mail_classifier_tool",
        "module_entrypoints.ufo_mail_tool",
        "module_entrypoints.dispatch_mail_tool",
        "module_entrypoints.booking_tool",
    ]
    script = (
        "import importlib, sys; "
        f"mods = {module_names!r}; "
        "[importlib.import_module(name) for name in mods]; "
        "raise SystemExit(1 if 'reconcile_web_app' in sys.modules else 0)"
    )
    env = os.environ.copy()
    env["BILL_TOOL_RUNTIME_DIR"] = str(tmp_path / "runtime")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_create_booking_app_uses_delivery_refresh_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    import booking_web_app

    calls: list[str] = []

    def fake_start() -> None:
        calls.append("start")

    async def fake_stop() -> None:
        calls.append("stop")

    monkeypatch.setattr(booking_web_app, "start_delivery_list_background_refresh", fake_start)
    monkeypatch.setattr(booking_web_app, "stop_delivery_list_background_refresh", fake_stop)

    with TestClient(booking_web_app.create_booking_app()) as client:
        response = client.get("/modules/booking")
        assert response.status_code == 200

    assert calls == ["start", "stop"]


def test_reconcile_app_uses_delivery_refresh_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    import reconcile_web_app

    calls: list[str] = []

    def fake_start() -> None:
        calls.append("start")

    async def fake_stop() -> None:
        calls.append("stop")

    monkeypatch.setattr(reconcile_web_app, "start_delivery_list_background_refresh", fake_start)
    monkeypatch.setattr(reconcile_web_app, "stop_delivery_list_background_refresh", fake_stop)

    with TestClient(reconcile_web_app.app) as client:
        response = client.get("/")
        assert response.status_code in {200, 307}

    assert calls == ["start", "stop"]


def test_build_release_zip_excludes_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from tools import build_release

    monkeypatch.setattr(build_release, "PROJECT_ROOT", tmp_path)
    dist_dir = tmp_path / "dist" / "BillingTool"
    (dist_dir / "runtime").mkdir(parents=True)
    (dist_dir / "runtime" / "secret.db").write_text("secret", encoding="utf-8")
    (dist_dir / "BillingTool.exe").write_text("exe", encoding="utf-8")

    artifact = build_release.zip_onedir(app_name="BillingTool", output_zip=tmp_path / "release_site" / "billing.zip")

    with zipfile.ZipFile(artifact.zip_path) as archive:
        names = archive.namelist()

    assert "BillingTool/BillingTool.exe" in names
    assert all("runtime" not in name.lower().split("/") for name in names)


def test_build_release_manifest_generation_without_pyinstaller(tmp_path: Path) -> None:
    from tools import build_release

    output_dir = tmp_path / "release_site"
    artifacts = {}
    for module in MODULE_CATALOG:
        zip_path = output_dir / "modules" / module.module_id / f"{module.artifact_name_prefix}-test.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(b"zip")
        artifacts[module.module_id] = build_release.BuildArtifact(
            name=module.exe_stem,
            zip_path=zip_path,
            sha256="b" * 64,
            size=zip_path.stat().st_size,
        )

    manifest_path = build_release.write_manifest(
        version="test-version",
        output_dir=output_dir,
        manifest_base_url="",
        module_artifacts=artifacts,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert set(manifest["modules"]) == {module.module_id for module in MODULE_CATALOG}
    assert manifest["modules"]["billing"]["artifact"].startswith("modules/billing/")
