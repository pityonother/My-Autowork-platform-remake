from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.distribution.downloader import calculate_sha256  # noqa: E402
from app.module_catalog import MODULE_CATALOG, ModuleDefinition  # noqa: E402


HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
    "multipart",
    "pandas",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageSequence",
    "fitz",
]

COLLECT_SUBMODULES = [
    "openpyxl",
    "xlrd",
]

DATA_FILES = [
    ("templates", "templates"),
    ("static", "static"),
    ("booking_template_zh.xlsx", "."),
    ("sample_price.xlsx", "."),
    (
        "app/modules/booking/default_warehouse_template",
        "app/modules/booking/default_warehouse_template",
    ),
]

MODULE_ENTRYPOINTS = {
    "billing": "module_entrypoints/billing_tool.py",
    "import_customs": "module_entrypoints/import_customs_tool.py",
    "export_clearance": "module_entrypoints/export_clearance_tool.py",
    "finance": "module_entrypoints/finance_tool.py",
    "mail_classifier": "module_entrypoints/mail_classifier_tool.py",
    "ufo_mail": "module_entrypoints/ufo_mail_tool.py",
    "dispatch_mail": "module_entrypoints/dispatch_mail_tool.py",
    "booking": "module_entrypoints/booking_tool.py",
}


class ReleaseBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildArtifact:
    name: str
    zip_path: Path
    sha256: str
    size: int


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ReleaseBuildError(f"命令失败，退出码 {completed.returncode}: {' '.join(command)}")


def resolve_version(explicit_version: str | None = None) -> str:
    if explicit_version:
        return explicit_version
    env_version = os.environ.get("APP_RELEASE_VERSION", "").strip()
    if env_version:
        return env_version
    date_part = datetime.now().strftime("%Y.%m.%d")
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        print("WARNING: 没有可用 git sha，本次版本号使用 dev-local，不适合正式发布。")
        return "dev-local"
    return f"{date_part}+{completed.stdout.strip()}"


def require_pyinstaller() -> None:
    if platform.system() != "Windows":
        raise ReleaseBuildError("当前脚本需要在 Windows 上运行 PyInstaller 构建 exe。")
    try:
        import PyInstaller  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise ReleaseBuildError("PyInstaller 不可用，请先安装 requirements.txt。") from exc


def pyinstaller_command(*, app_name: str, entrypoint: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--specpath",
        str(PROJECT_ROOT / "build" / "specs"),
        "--name",
        app_name,
        "--console",
    ]
    for source, target in DATA_FILES:
        command.extend(["--add-data", f"{PROJECT_ROOT / source};{target}"])
    for hidden_import in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", hidden_import])
    for package_name in COLLECT_SUBMODULES:
        command.extend(["--collect-submodules", package_name])
    command.append(entrypoint)
    return command


def build_onedir(*, app_name: str, entrypoint: str, skip_pyinstaller: bool) -> None:
    if skip_pyinstaller:
        dist_dir = PROJECT_ROOT / "dist" / app_name
        if not dist_dir.is_dir():
            raise ReleaseBuildError(f"--skip-pyinstaller 找不到现有 dist 目录：{dist_dir}")
        return
    require_pyinstaller()
    run(pyinstaller_command(app_name=app_name, entrypoint=entrypoint))


def zip_onedir(*, app_name: str, output_zip: Path) -> BuildArtifact:
    dist_dir = PROJECT_ROOT / "dist" / app_name
    if not dist_dir.is_dir():
        raise ReleaseBuildError(f"找不到 PyInstaller 输出目录：{dist_dir}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(dist_dir)
            if any(part.lower() == "runtime" for part in relative.parts):
                continue
            archive.write(path, (Path(app_name) / relative).as_posix())

    return BuildArtifact(
        name=app_name,
        zip_path=output_zip,
        sha256=calculate_sha256(output_zip),
        size=output_zip.stat().st_size,
    )


def artifact_reference(relative_path: str, manifest_base_url: str) -> str:
    if not manifest_base_url:
        return relative_path.replace("\\", "/")
    base = manifest_base_url.rstrip("/") + "/"
    return urljoin(base, relative_path.replace("\\", "/"))


def build_launcher(*, version: str, output_dir: Path, skip_pyinstaller: bool) -> BuildArtifact:
    build_onedir(app_name="LauncherTool", entrypoint="launcher_packaged_app.py", skip_pyinstaller=skip_pyinstaller)
    return zip_onedir(
        app_name="LauncherTool",
        output_zip=output_dir / "launcher" / f"LauncherTool-{version}.zip",
    )


def build_module(*, module: ModuleDefinition, version: str, output_dir: Path, skip_pyinstaller: bool) -> BuildArtifact:
    entrypoint = MODULE_ENTRYPOINTS[module.module_id]
    build_onedir(app_name=module.exe_stem, entrypoint=entrypoint, skip_pyinstaller=skip_pyinstaller)
    return zip_onedir(
        app_name=module.exe_stem,
        output_zip=output_dir / "modules" / module.module_id / f"{module.artifact_name_prefix}-{version}.zip",
    )


def write_manifest(
    *,
    version: str,
    output_dir: Path,
    manifest_base_url: str,
    module_artifacts: dict[str, BuildArtifact],
) -> Path:
    modules: dict[str, dict[str, object]] = {}
    for module in MODULE_CATALOG:
        artifact = module_artifacts[module.module_id]
        relative_artifact = artifact.zip_path.relative_to(output_dir).as_posix()
        modules[module.module_id] = {
            "title": module.title,
            "version": version,
            "artifact": artifact_reference(relative_artifact, manifest_base_url),
            "sha256": artifact.sha256,
            "size": artifact.size,
            "entry_exe": f"{module.exe_stem}/{module.exe_name}",
            "landing_path": module.route_path,
            "start_port": module.start_port,
        }
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "release_version": version,
        "modules": modules,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def assert_release_site_has_no_runtime(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    runtime_paths = [
        path
        for path in output_dir.rglob("*")
        if any(part.lower() == "runtime" for part in path.relative_to(output_dir).parts)
    ]
    if runtime_paths:
        details = "\n".join(str(path) for path in runtime_paths[:20])
        raise ReleaseBuildError(f"release_site 不能包含 runtime 数据：\n{details}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Launcher and module release zips.")
    parser.add_argument("--version", default="", help="Release version. Defaults to APP_RELEASE_VERSION or date+gitsha.")
    parser.add_argument("--manifest-base-url", default="", help="Base URL used to make manifest artifact URLs absolute.")
    parser.add_argument("--output-dir", default="release_site", help="Release output directory.")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Only zip existing dist outputs and generate manifest.")
    parser.add_argument("--only", choices=["all", "launcher", "modules"], default="all", help="Limit build scope.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    version = resolve_version(args.version or None)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    print(f"Release version: {version}")
    launcher_artifact: BuildArtifact | None = None
    module_artifacts: dict[str, BuildArtifact] = {}

    if args.only in {"all", "launcher"}:
        launcher_artifact = build_launcher(version=version, output_dir=output_dir, skip_pyinstaller=args.skip_pyinstaller)
        print(f"Launcher zip: {launcher_artifact.zip_path}")

    if args.only in {"all", "modules"}:
        for module in MODULE_CATALOG:
            artifact = build_module(module=module, version=version, output_dir=output_dir, skip_pyinstaller=args.skip_pyinstaller)
            module_artifacts[module.module_id] = artifact
            print(f"Module zip: {artifact.zip_path}")
        manifest_path = write_manifest(
            version=version,
            output_dir=output_dir,
            manifest_base_url=args.manifest_base_url,
            module_artifacts=module_artifacts,
        )
        print(f"Manifest: {manifest_path}")

    assert_release_site_has_no_runtime(output_dir)
    print("Release build finished. runtime was not copied.")


if __name__ == "__main__":
    try:
        main()
    except ReleaseBuildError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
