from __future__ import annotations

from app.packaging.local_server import run_local_app
from reconcile_web_app import app


def main() -> None:
    run_local_app(app, display_name="账单与清关工具", start_port=8010, landing_path="/")


if __name__ == "__main__":
    main()
