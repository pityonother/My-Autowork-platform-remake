from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.paths import APP_DIR, RUNTIME_DIR
from app.distribution.downloader import download_artifact
from app.distribution.errors import DistributionError, ManifestError
from app.distribution.installed import InstalledModule, read_installed_modules, upsert_installed_module
from app.distribution.installer import install_module
from app.distribution.launcher import ModuleProcessRegistry
from app.distribution.manifest import ReleaseManifest, load_manifest
from app.factory import create_templates
from app.module_catalog import MODULE_CATALOG, MODULES_BY_ID


router = APIRouter()
templates = create_templates()

CONFIG_FILE = APP_DIR / "update_config.json"
CONFIG_ENV = "BILL_TOOL_MANIFEST_URL"
LAUNCHER_DIR = RUNTIME_DIR / "launcher"
INSTALLED_MODULES_PATH = LAUNCHER_DIR / "installed_modules.json"
DOWNLOADS_DIR = LAUNCHER_DIR / "downloads"
MODULES_DIR = RUNTIME_DIR / "modules"
MODULE_DATA_DIR = RUNTIME_DIR / "module_data"

process_registry = ModuleProcessRegistry(modules_dir=MODULES_DIR, module_data_dir=MODULE_DATA_DIR)


def read_manifest_url() -> str:
    env_value = os.environ.get(CONFIG_ENV, "").strip()
    if env_value:
        return env_value
    if not CONFIG_FILE.exists():
        return ""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return ""
    return str(data.get("manifest_url", "")).strip()


def write_manifest_url(manifest_url: str) -> None:
    payload = {
        "manifest_url": manifest_url.strip(),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    tmp_path = CONFIG_FILE.with_suffix(CONFIG_FILE.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(CONFIG_FILE)


def try_load_manifest(manifest_url: str) -> tuple[ReleaseManifest | None, str]:
    if not manifest_url:
        return None, ""
    try:
        return load_manifest(manifest_url), ""
    except ManifestError as exc:
        return None, exc.user_message


def module_statuses(
    manifest: ReleaseManifest | None,
    manifest_error: str,
    *,
    error_module: str = "",
    error_status: str = "",
) -> list[dict[str, Any]]:
    installed = read_installed_modules(INSTALLED_MODULES_PATH)
    rows: list[dict[str, Any]] = []
    for module in MODULE_CATALOG:
        installed_module = installed.get(module.module_id)
        remote_module = manifest.modules.get(module.module_id) if manifest else None
        is_installed = installed_module is not None
        is_running = process_registry.is_running(module.module_id)
        if manifest_error:
            status = "下载失败"
            status_kind = "error"
        elif error_module == module.module_id and error_status:
            status = error_status
            status_kind = "error"
        elif not is_installed and remote_module:
            status = "可安装"
            status_kind = "info"
        elif is_installed and remote_module and installed_module.version != remote_module.version:
            status = "可更新"
            status_kind = "warn"
        elif is_installed and remote_module:
            status = "已最新"
            status_kind = "success"
        elif is_installed:
            status = "已安装"
            status_kind = "success"
        else:
            status = "未安装"
            status_kind = "neutral"
        rows.append(
            {
                "module_id": module.module_id,
                "title": module.title,
                "badge": module.badge,
                "subtitle": module.subtitle,
                "description": module.description,
                "installed_state": "已安装" if is_installed else "未安装",
                "installed_version": installed_module.version if installed_module else "-",
                "remote_version": remote_module.version if remote_module else "-",
                "status": status,
                "status_kind": status_kind,
                "can_install": bool(remote_module and not is_installed and not manifest_error),
                "can_update": bool(remote_module and is_installed and installed_module.version != remote_module.version and not manifest_error),
                "can_open": is_installed,
                "is_running": is_running,
            }
        )
    return rows


def page_context(request: Request, *, message: str = "", error: str = "") -> dict[str, Any]:
    manifest_url = read_manifest_url()
    manifest, manifest_error = try_load_manifest(manifest_url)
    query = request.query_params
    action_error = error or query.get("error", "")
    error_module = query.get("error_module", "")
    error_status = query.get("error_status", "")
    return {
        "request": request,
        "manifest_url": manifest_url,
        "manifest_error": manifest_error,
        "message": message or query.get("message", ""),
        "error": action_error,
        "release_version": manifest.release_version if manifest else "-",
        "generated_at": manifest.generated_at if manifest else "-",
        "modules": module_statuses(manifest, manifest_error, error_module=error_module, error_status=error_status),
        "config_env": CONFIG_ENV,
        "config_file": str(CONFIG_FILE),
        "runtime_dir": str(RUNTIME_DIR),
    }


def redirect_with(*, message: str = "", error: str = "", error_module: str = "", error_status: str = "") -> RedirectResponse:
    target = "/"
    if message:
        target += "?" + urlencode({"message": message})
    elif error:
        params = {"error": error}
        if error_module:
            params["error_module"] = error_module
        if error_status:
            params["error_status"] = error_status
        target += "?" + urlencode(params)
    return RedirectResponse(url=target, status_code=303)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "launcher.html", page_context(request))


@router.post("/launcher/settings")
async def save_settings(manifest_url: str = Form("")) -> RedirectResponse:
    write_manifest_url(manifest_url)
    return redirect_with(message="更新地址已保存。")


@router.post("/launcher/refresh")
async def refresh() -> RedirectResponse:
    manifest_url = read_manifest_url()
    try:
        load_manifest(manifest_url)
    except DistributionError as exc:
        return redirect_with(error=exc.user_message)
    return redirect_with(message="远端 manifest 已刷新。")


def install_or_update_module(module_id: str) -> RedirectResponse:
    if module_id not in MODULES_BY_ID:
        return redirect_with(error="未知模块。")
    manifest_url = read_manifest_url()
    try:
        manifest = load_manifest(manifest_url)
        remote_module = manifest.modules.get(module_id)
        if remote_module is None:
            raise ManifestError("manifest 中找不到这个模块。")
        download = download_artifact(
            module_id=module_id,
            artifact_url=remote_module.artifact_url,
            expected_sha256=remote_module.sha256,
            downloads_dir=DOWNLOADS_DIR,
        )
        install_module(
            module_id=module_id,
            zip_path=download.path,
            entry_exe=remote_module.entry_exe,
            modules_dir=MODULES_DIR,
            is_running=process_registry.is_running,
        )
        upsert_installed_module(
            INSTALLED_MODULES_PATH,
            InstalledModule(
                module_id=module_id,
                title=remote_module.title,
                version=remote_module.version,
                entry_exe=remote_module.entry_exe,
                landing_path=remote_module.landing_path,
                start_port=remote_module.start_port,
                installed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                artifact_sha256=download.sha256,
            ),
        )
    except DistributionError as exc:
        return redirect_with(error=exc.user_message)
    return redirect_with(message="模块已安装或更新。")


@router.post("/launcher/modules/{module_id}/install")
async def install(module_id: str) -> RedirectResponse:
    return install_or_update_module(module_id)


@router.post("/launcher/modules/{module_id}/update")
async def update(module_id: str) -> RedirectResponse:
    return install_or_update_module(module_id)


@router.post("/launcher/modules/{module_id}/open")
async def open_module(module_id: str) -> RedirectResponse:
    installed = read_installed_modules(INSTALLED_MODULES_PATH)
    module = installed.get(module_id)
    if module is None:
        return redirect_with(error="该模块尚未安装。")
    try:
        result = process_registry.launch(module)
    except DistributionError as exc:
        return redirect_with(error=exc.user_message)
    return redirect_with(message=result.message)


@router.get("/launcher/modules/{module_id}/status")
async def status(module_id: str) -> JSONResponse:
    statuses = {row["module_id"]: row for row in module_statuses(*try_load_manifest(read_manifest_url()))}
    return JSONResponse(statuses.get(module_id, {"module_id": module_id, "status": "未知模块"}))
