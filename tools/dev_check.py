from __future__ import annotations

import argparse
import subprocess
import sys
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def git_status_short() -> str:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    print("$ git status --short")
    print(completed.stdout, end="")
    return completed.stdout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run My-Autowork development checks.")
    parser.add_argument("--require-clean", action="store_true", help="Fail if git status is not clean.")
    parser.add_argument("--require-ruff", action="store_true", help="Fail if Ruff is not installed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (PROJECT_ROOT / ".git").is_dir():
        status = git_status_short()
        if args.require_clean and status.strip():
            raise SystemExit("working tree is not clean")

    root_python_files = sorted(path.name for path in PROJECT_ROOT.glob("*.py"))
    run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "app",
            *root_python_files,
            "booking_rules",
            "module_entrypoints",
            "tools",
            "tests",
        ]
    )
    run([sys.executable, "-m", "pytest", "-q"])
    if importlib.util.find_spec("ruff") is None:
        print("$ python -m ruff check app tools tests")
        print("ruff is not installed; skipping optional lint check.")
        if args.require_ruff:
            raise SystemExit("ruff is required but not installed")
        return
    run([sys.executable, "-m", "ruff", "check", "app", "tools", "tests"])


if __name__ == "__main__":
    main()
