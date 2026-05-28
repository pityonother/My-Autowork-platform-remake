from __future__ import annotations

from app.packaging.local_server import run_local_app
from launcher_web_app import app


def main() -> None:
    run_local_app(app, display_name="模块 Launcher", start_port=8000, landing_path="/")


if __name__ == "__main__":
    main()
