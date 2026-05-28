from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Callable

from app.distribution.errors import InstallError, ModuleRunningError


@dataclass(frozen=True)
class InstallResult:
    module_id: str
    current_dir: Path
    entry_exe_path: Path
    previous_dir: Path | None


def ensure_within_directory(base_dir: Path, target: Path) -> None:
    base_resolved = base_dir.resolve()
    target_resolved = target.resolve()
    if target_resolved != base_resolved and base_resolved not in target_resolved.parents:
        raise InstallError("安装包包含不安全路径，已停止安装。")


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            pure_windows = PureWindowsPath(name)
            if name.startswith("/") or pure_windows.drive or ".." in Path(name).parts:
                raise InstallError("安装包包含不安全路径，已停止安装。")
            target = destination / name
            ensure_within_directory(destination, target)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path)


def install_module(
    *,
    module_id: str,
    zip_path: Path,
    entry_exe: str,
    modules_dir: Path,
    is_running: Callable[[str], bool] | None = None,
) -> InstallResult:
    if is_running and is_running(module_id):
        raise ModuleRunningError("请先关闭该模块后再更新。")

    module_dir = modules_dir / module_id
    current_dir = module_dir / "current"
    previous_dir = module_dir / "previous"
    staging_dir = module_dir / f".incoming-{uuid.uuid4().hex}"
    old_current_tmp = module_dir / f".previous-{uuid.uuid4().hex}"
    module_dir.mkdir(parents=True, exist_ok=True)

    try:
        safe_extract_zip(zip_path, staging_dir)
        entry_path = staging_dir / entry_exe
        ensure_within_directory(staging_dir, entry_path)
        if not entry_path.is_file():
            raise InstallError("安装包缺少入口 exe，已停止安装。")

        remove_tree(previous_dir)
        previous_for_result: Path | None = None
        if current_dir.exists():
            current_dir.rename(old_current_tmp)
            previous_for_result = previous_dir
        try:
            staging_dir.rename(current_dir)
        except Exception:
            if old_current_tmp.exists() and not current_dir.exists():
                old_current_tmp.rename(current_dir)
            raise
        if old_current_tmp.exists():
            old_current_tmp.rename(previous_dir)

        entry_exe_path = current_dir / entry_exe
        return InstallResult(
            module_id=module_id,
            current_dir=current_dir,
            entry_exe_path=entry_exe_path,
            previous_dir=previous_for_result,
        )
    except ModuleRunningError:
        raise
    except InstallError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InstallError("安装失败，已尽量保留原可用版本。", technical_detail=str(exc)) from exc
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if old_current_tmp.exists() and not current_dir.exists():
            try:
                old_current_tmp.rename(current_dir)
            except OSError:
                pass


def installed_entry_path(modules_dir: Path, module_id: str, entry_exe: str) -> Path:
    return modules_dir / module_id / "current" / entry_exe


def path_for_display(path: Path) -> str:
    return os.fspath(path)
