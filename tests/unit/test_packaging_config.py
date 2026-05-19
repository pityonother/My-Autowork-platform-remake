from __future__ import annotations

from pathlib import Path


def test_pyinstaller_configs_include_required_runtime_assets() -> None:
    project_root = Path(__file__).resolve().parents[2]
    required_assets = ["templates", "static", "booking_template_zh.xlsx"]
    config_files = [
        "build_exe.bat",
        "build_booking_exe.bat",
        "BillClearanceTool.spec",
        "BookingTool.spec",
    ]

    missing: list[str] = []
    for relative_path in config_files:
        text = (project_root / relative_path).read_text(encoding="utf-8")
        for asset in required_assets:
            if asset not in text:
                missing.append(f"{relative_path}:{asset}")

    assert missing == []


def test_requirements_use_direct_dependency_version_ranges() -> None:
    project_root = Path(__file__).resolve().parents[2]
    lines = [
        line.strip()
        for line in (project_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert lines
    assert all(">=" in line and "<" in line for line in lines)
