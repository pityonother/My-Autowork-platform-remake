from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstalledModule:
    module_id: str
    title: str
    version: str
    entry_exe: str
    landing_path: str
    start_port: int
    installed_at: str
    artifact_sha256: str


def read_installed_modules(path: Path) -> dict[str, InstalledModule]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    modules_raw = data.get("modules", {}) if isinstance(data, dict) else {}
    result: dict[str, InstalledModule] = {}
    for module_id, raw in modules_raw.items():
        if not isinstance(raw, dict):
            continue
        try:
            result[module_id] = InstalledModule(
                module_id=str(raw.get("module_id") or module_id),
                title=str(raw.get("title", "")),
                version=str(raw.get("version", "")),
                entry_exe=str(raw.get("entry_exe", "")),
                landing_path=str(raw.get("landing_path", "")),
                start_port=int(raw.get("start_port", 0)),
                installed_at=str(raw.get("installed_at", "")),
                artifact_sha256=str(raw.get("artifact_sha256", "")),
            )
        except (TypeError, ValueError):
            continue
    return result


def write_installed_modules(path: Path, modules: dict[str, InstalledModule]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "modules": {module_id: asdict(module) for module_id, module in sorted(modules.items())},
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def upsert_installed_module(path: Path, module: InstalledModule) -> dict[str, InstalledModule]:
    modules = read_installed_modules(path)
    modules[module.module_id] = module
    write_installed_modules(path, modules)
    return modules
