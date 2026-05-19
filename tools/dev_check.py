from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    if (PROJECT_ROOT / ".git").is_dir():
        run(["git", "status", "--short"])

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
            "tools",
            "tests",
        ]
    )
    run([sys.executable, "-m", "pytest", "-q"])


if __name__ == "__main__":
    main()
