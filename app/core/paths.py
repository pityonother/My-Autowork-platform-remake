from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def runtime_dir() -> Path:
    override = os.environ.get("BILL_TOOL_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return app_dir() / "runtime"


# RESOURCE_DIR is where bundled read-only files live, such as templates,
# static assets, and sample workbooks. In PyInstaller this may be _MEIPASS.
RESOURCE_DIR = resource_dir()
# APP_DIR is the executable or source checkout directory. Do not use it as
# the user data directory when modules are launched by the Launcher.
APP_DIR = app_dir()
# RUNTIME_DIR is writable user data. BILL_TOOL_RUNTIME_DIR can point it at a
# module-specific data folder so upgrades do not overwrite databases/uploads.
RUNTIME_DIR = runtime_dir()
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "outputs"
STATIC_DIR = RESOURCE_DIR / "static"
TEMPLATES_DIR = RESOURCE_DIR / "templates"
