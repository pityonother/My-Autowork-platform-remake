from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.distribution.errors import LaunchError
from app.distribution.installed import InstalledModule
from app.distribution.installer import installed_entry_path


@dataclass(frozen=True)
class LaunchResult:
    module_id: str
    already_running: bool
    message: str


class ModuleProcessRegistry:
    def __init__(self, *, modules_dir: Path, module_data_dir: Path) -> None:
        self.modules_dir = modules_dir
        self.module_data_dir = module_data_dir
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def is_running(self, module_id: str) -> bool:
        process = self._processes.get(module_id)
        if process is None:
            return False
        if process.poll() is None:
            return True
        self._processes.pop(module_id, None)
        return False

    def launch(self, module: InstalledModule) -> LaunchResult:
        if self.is_running(module.module_id):
            return LaunchResult(module.module_id, True, "已启动。")

        exe_path = installed_entry_path(self.modules_dir, module.module_id, module.entry_exe)
        if not exe_path.is_file():
            raise LaunchError("找不到模块 exe，请重新安装该模块。", technical_detail=str(exe_path))

        runtime_dir = self.module_data_dir / module.module_id
        runtime_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["BILL_TOOL_RUNTIME_DIR"] = str(runtime_dir)
        try:
            process = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), env=env)
        except Exception as exc:  # noqa: BLE001
            raise LaunchError("启动模块失败，请重新安装或检查杀毒软件拦截。", technical_detail=str(exc)) from exc
        self._processes[module.module_id] = process
        return LaunchResult(module.module_id, False, "已启动。")
