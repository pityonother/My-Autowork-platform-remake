from __future__ import annotations

from app.factory import create_app
from app.modules.import_customs.routes import router
from app.packaging.local_server import run_local_app


app = create_app("香港进口清关", routers=[router])


def main() -> None:
    run_local_app(app, display_name="香港进口清关", start_port=8032, landing_path="/modules/import-customs")


if __name__ == "__main__":
    main()
